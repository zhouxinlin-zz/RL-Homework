"""Reproducible paired evaluation on the formation-based challenge roads."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from stable_baselines3 import PPO

from rl_course.challenge_rules import CHALLENGE_TRACKS
from rl_course.driving_env_v3 import ENV_VERSION, SCENARIOS, make_challenge_env
from rl_course.game_rules import performance
from rl_course.v2_metrics import episode, interval, sha256, write_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "experiments_v3"
DEVELOPMENT_START = 531100
TEST_START = 931100


def evaluate(policy: str, model_path: Path | None, *, episodes: int, seed_start: int,
             duration: int = 45, game_routes: bool = False) -> dict:
    torch.set_num_threads(1)
    model = PPO.load(str(model_path), device="cpu") if model_path else None
    rows = []
    for scenario in SCENARIOS:
        track = next(item for item in CHALLENGE_TRACKS if item["scenario"] == scenario)
        road_duration = track["duration"] if game_routes else duration
        env = make_challenge_env(scenario, road_duration)
        try:
            for seed in range(seed_start, seed_start + episodes):
                row = episode(env, model=model, baseline=policy if not model else None, seed=seed)
                row["policy"] = policy
                row["scenario"] = scenario
                if game_routes:
                    row.update(performance(track, done=True, crashed=not row["completed"],
                                           distance=row["distance_m"], overtakes=row["overtakes"],
                                           danger_seconds=row["danger_seconds"]))
                row["formations"] = len(env.unwrapped.formation_events)
                row["formation_placed"] = sum(event["placed"] for event in env.unwrapped.formation_events)
                row["unsafe_lane_requests"] = env.unwrapped.unsafe_lane_requests
                rows.append(row)
        finally:
            env.close()
        print(f"{policy} {scenario}: {episodes} paired seeds complete", flush=True)
    summary = {}
    for scenario in SCENARIOS:
        selected = [row for row in rows if row["scenario"] == scenario]
        crashes = sum(row["crashed"] for row in selected)
        summary[scenario] = {
            "episodes": len(selected), "crashes": crashes, "crash_rate": crashes / len(selected),
            "crash_ci95": interval(crashes, len(selected)),
            "completion_rate": float(np.mean([row["completed"] for row in selected])),
            "mean_distance_m": float(np.mean([row["distance_m"] for row in selected])),
            "mean_overtakes": float(np.mean([row["overtakes"] for row in selected])),
            "mean_danger_seconds": float(np.mean([row["danger_seconds"] for row in selected])),
            "mean_lane_changes": float(np.mean([row["lane_changes"] for row in selected])),
            "mean_quality": float(np.mean([row["quality"] for row in selected])),
            "mean_formations": float(np.mean([row["formations"] for row in selected])),
            "mean_formation_cars": float(np.mean([row["formation_placed"] for row in selected])),
            "mean_unsafe_lane_requests": float(np.mean([row["unsafe_lane_requests"] for row in selected])),
            **({"qualification_rate": float(np.mean([row["qualified"] for row in selected])),
                "mean_score": float(np.mean([row["score"] for row in selected]))}
               if game_routes else {}),
        }
    result = {"env_version": ENV_VERSION, "policy": policy, "model": str(model_path) if model_path else None,
              "model_sha256": sha256(model_path) if model_path else None,
              "seed_start": seed_start, "episodes_per_scenario": episodes,
              "duration": "game_routes" if game_routes else duration,
              "scenario_order": list(SCENARIOS), "summary": summary, "episodes": rows}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--split", choices=("development", "test"), default="development")
    parser.add_argument("--duration", type=int, default=45)
    parser.add_argument("--game-routes", action="store_true")
    args = parser.parse_args()
    if args.episodes <= 0:
        parser.error("episodes must be positive")
    start = DEVELOPMENT_START if args.split == "development" else TEST_START
    report = evaluate(args.policy, args.model, episodes=args.episodes, seed_start=start,
                      duration=args.duration, game_routes=args.game_routes)
    path = OUT / f"{args.split}_{args.policy}{'_routes' if args.game_routes else ''}.json"
    write_json(path, report)
    print(json.dumps({"path": str(path), "summary": report["summary"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
