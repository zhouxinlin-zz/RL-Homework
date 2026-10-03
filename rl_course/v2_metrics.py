"""Shared deterministic driving evaluation. No safety controller is applied to RL."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "artifacts" / "experiments_v2"
CONDITIONS = (("light", 30), ("normal", 45), ("dense", 45), ("normal", 60), ("dense", 60))
VALIDATION_SEEDS = tuple(range(31100, 31106))
TEST_SEED_START = 891000


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rule_action(obs: np.ndarray) -> int:
    """Transparent rule baseline, using exactly the same 30 observed numbers as RL.

    It checks front/rear clearance before changing a lane and adjusts speed to the
    space ahead. It has no access to future traffic, seed, or hidden vehicle state.
    """
    x = np.asarray(obs).reshape(-1)
    speed, target = float(x[0] * 30), float(x[1] * 30)
    lane = int(np.clip(round(float(x[2] + 1)), 0, 2))
    target_lane = int(np.clip(round(float(x[3] + 1)), 0, 2))
    lanes = x[6:].reshape(3, 8)
    front = [float(v[0] * 120) if v[2] > .5 else 120.0 for v in lanes]
    back = [float(v[3] * 80) if v[5] > .5 else 80.0 for v in lanes]
    if lane != target_lane or abs(float(x[2] + 1) - lane) > .1:
        return 1
    if front[lane] < max(48, speed * 2.1):
        options = []
        for other in (lane - 1, lane + 1):
            if not 0 <= other < 3:
                continue
            rear_closing = max(0.0, float(lanes[other][4] * 15))
            front_closing = max(0.0, -float(lanes[other][1] * 15))
            if (front[other] > max(24, speed * 1.1, front_closing * 4)
                    and back[other] > max(18, rear_closing * 4)
                    and front[other] > front[lane] + 14):
                options.append(other)
        if options:
            other = max(options, key=lambda item: front[item])
            return 0 if other < lane else 2
    lead_speed = speed + float(lanes[lane][1] * 15)
    if front[lane] < max(15, speed * 1.5) and target > max(12, lead_speed - 2):
        return 4
    if front[lane] > max(38, speed * 2) and target < 29:
        return 3
    return 1


def episode(env, model=None, baseline=None, seed=31100, inference_stride=1,
            collect_trace=False) -> dict:
    obs, _ = env.reset(seed=seed)
    env.action_space.seed(seed + 1000000)
    world = env.unwrapped
    start_x = float(world.vehicle.position[0])
    speeds, trace, actions = [], [], [0] * 5
    total, steps, done = 0.0, 0, False
    while not done:
        if model is not None:
            action = int(np.asarray(model.predict(obs, deterministic=True)[0]).item()) if steps % inference_stride == 0 else 1
        elif baseline == "rule":
            action = rule_action(obs)
        elif baseline == "slow":
            action = 4 if steps == 0 else 1  # 18 m/s, one step below the 24 m/s start.
        elif baseline == "crawl":
            action = 4 if world.vehicle.target_speed > 12.1 else 1
        elif baseline == "random":
            action = int(env.action_space.sample())
        else:
            action = 1  # Constant target 24 m/s, with normal physics.
        obs, reward, terminated, truncated, info = env.step(action)
        speeds.append(float(world.vehicle.speed) * 3.6)
        actions[action] += 1
        total += float(reward)
        steps += 1
        done = terminated or truncated
        if collect_trace:
            trace.append({"time": round(float(world.time), 3), "action": action,
                          "speed": round(float(world.vehicle.speed), 3),
                          "lane": round(float(world.vehicle.position[1] / 4), 3),
                          "observation": np.asarray(obs).round(4).tolist(),
                          "crashed": bool(world.vehicle.crashed)})
    duration = float(world.config["duration"])
    crashed = bool(world.vehicle.crashed)
    distance = float(world.vehicle.position[0]) - start_x
    overtakes = int(getattr(world, "overtaken_count", len(getattr(world, "overtaken_ids", []))))
    danger = float(getattr(world, "danger_seconds", 0))
    completed = bool(world.completed)
    # Explicit quality measure for checkpoint selection; training return is never
    # used to rank candidates. Safety, progress, passing and danger are all logged.
    quality = 2.0 * completed + distance / (duration * 30) + .02 * min(overtakes, 15) - .2 * danger / duration
    row = {"seed": seed, "scenario": world.config.get("scenario", "unknown"),
           "duration": int(duration), "crashed": crashed, "completed": completed,
           "failed": not completed,
           "time_s": round(float(world.time), 4), "distance_m": distance,
           "speed_kmh": float(np.mean(speeds)), "overtakes": overtakes,
           "lane_changes": int(getattr(world, "lane_changes", 0)),
           "danger_seconds": danger, "return": total, "quality": quality,
           "actions": actions, "steps": steps}
    from rl_course.game_rules import TRACKS, performance
    track = next((track for track in TRACKS if track["scenario"] == row["scenario"] and track["duration"] == row["duration"]), None)
    if track is not None:
        row.update(performance(track, done=True, crashed=not completed, distance=distance,
                               overtakes=overtakes, danger_seconds=danger))
    if collect_trace:
        row["trace"] = trace
    return row


def interval(successes: int, n: int) -> list[float]:
    z = 1.95996398454
    p = successes / n
    center = (p + z*z/(2*n)) / (1+z*z/n)
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1+z*z/n)
    return [max(0, center-half), min(1, center+half)]


def aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    crashes = sum(row["crashed"] for row in rows)
    return {"episodes": n, "crashes": crashes, "crash_rate": crashes/n,
            "failure_rate": float(np.mean([not row["completed"] for row in rows])),
            "crash_ci95": interval(crashes, n),
            **{f"mean_{key}": float(np.mean([r[key] for r in rows])) for key in
               ("quality", "distance_m", "speed_kmh", "overtakes", "lane_changes", "danger_seconds", "return")},
            **{f"mean_{key}": float(np.mean([r[key] for r in rows if key in r])) for key in ("score", "qualified", "stars") if all(key in r for r in rows)}}


def assess(model, seeds=VALIDATION_SEEDS, conditions=None, inference_stride=1) -> dict:
    from rl_course.driving_env import make_driving_env
    rows = []
    for scenario, duration in conditions or CONDITIONS[:3]:
        env = make_driving_env(scenario, duration)
        try:
            for seed in seeds:
                row = episode(env, model=model, seed=seed, inference_stride=inference_stride)
                row["scenario"] = scenario
                rows.append(row)
        finally:
            env.close()
    return {**aggregate(rows), "episodes_detail": rows}
