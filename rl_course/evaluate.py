"""Evaluate saved models across traffic densities and export real trajectories."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
from stable_baselines3 import DQN, PPO

from rl_course.environment import SCENARIOS, action_names, make_env
from rl_course.serialization import frame


def run_episode(model: Any, scenario: str, seed: int, capture: bool) -> tuple[dict[str, Any], dict[str, Any] | None]:
    env = make_env(scenario)
    try:
        obs, _ = env.reset(seed=seed)
        env.action_space.seed(seed + 10_000)
        names = action_names(env)
        frames = [frame(env, 0, None, 0.0)] if capture else []
        rewards: list[float] = []
        speeds: list[float] = []
        done = False
        while not done:
            if model is None:
                action = int(env.action_space.sample())
            else:
                predicted, _ = model.predict(obs, deterministic=True)
                action = int(np.asarray(predicted).item())
            obs, reward, terminated, truncated, _ = env.step(action)
            rewards.append(float(reward))
            speeds.append(float(env.unwrapped.vehicle.speed) * 3.6)
            done = bool(terminated or truncated)
            if capture:
                frames.append(frame(env, len(rewards), action, float(reward)))

        result = {
            "scenario": scenario,
            "seed": seed,
            "return": float(sum(rewards)),
            "steps": len(rewards),
            "survival_seconds": float(env.unwrapped.time),
            "mean_speed_kmh": float(np.mean(speeds)) if speeds else 0.0,
            "crashed": bool(env.unwrapped.vehicle.crashed),
        }
        replay = (
            {
                "scenario": scenario,
                "seed": seed,
                "summary": result,
                "actions": names,
                "lanes_count": int(env.unwrapped.config["lanes_count"]),
                "frames": frames,
            }
            if capture
            else None
        )
        return result, replay
    finally:
        env.close()


def evaluate(models_dir: Path, output_dir: Path, episodes: int, seed_start: int = 1000) -> None:
    if episodes <= 0:
        raise ValueError("episodes must be positive")
    model_specs = {"random": None, "dqn": DQN, "ppo": PPO}
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for name, model_type in model_specs.items():
        path = models_dir / f"{name}_seed42.zip"
        if model_type is not None and not path.exists():
            print(f"Skipping {name}: {path} not found")
            continue
        model = model_type.load(str(path), device="cpu") if model_type is not None else None
        for scenario in SCENARIOS:
            for offset in range(episodes):
                seed = seed_start + offset
                result, replay = run_episode(model, scenario, seed, capture=offset == 0)
                result["policy"] = name
                rows.append(result)
                if replay is not None:
                    replay["policy"] = name
                    (output_dir / f"replay_{name}_{scenario}.json").write_text(
                        json.dumps(replay, ensure_ascii=False), encoding="utf-8"
                    )
            print(f"Evaluated {name} / {scenario}: {episodes} episodes")

    with (output_dir / "episodes.csv").open("w", newline="", encoding="utf-8") as file:
        fields = ["policy", "scenario", "seed", "return", "steps", "survival_seconds", "mean_speed_kmh", "crashed"]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    summary: list[dict[str, Any]] = []
    for policy in model_specs:
        for scenario in SCENARIOS:
            subset = [row for row in rows if row["policy"] == policy and row["scenario"] == scenario]
            if not subset:
                continue
            summary.append(
                {
                    "policy": policy,
                    "scenario": scenario,
                    "episodes": len(subset),
                    "crash_rate": float(np.mean([row["crashed"] for row in subset])),
                    "mean_return": float(np.mean([row["return"] for row in subset])),
                    "mean_speed_kmh": float(np.mean([row["mean_speed_kmh"] for row in subset])),
                    "mean_survival_seconds": float(np.mean([row["survival_seconds"] for row in subset])),
                }
            )
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(rows)} episode results to {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, default=Path("artifacts/models"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/evaluation"))
    parser.add_argument("--episodes", type=int, default=30)
    parser.add_argument("--seed-start", type=int, default=1000)
    args = parser.parse_args()
    evaluate(args.models, args.output, args.episodes, args.seed_start)


if __name__ == "__main__":
    main()
