"""Collect version 3 rule trajectories for a recorded BC plus PPO ablation."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from rl_course.driving_env_v3 import ENV_VERSION, SCENARIOS, make_challenge_env
from rl_course.evaluate_v3 import OUT
from rl_course.v2_metrics import rule_action, sha256, write_json


def collect(steps: int, seed: int) -> Path:
    path = OUT / "demonstrations" / f"rule_{steps}_s{seed}.npz"
    if path.exists():
        raise ValueError(f"Dataset already exists: {path}")
    rng = np.random.default_rng(seed)
    observations, labels, executed = [], [], []
    episodes = crashes = 0
    while len(labels) < steps:
        scenario = str(rng.choice(SCENARIOS))
        env = make_challenge_env(scenario, 45)
        try:
            obs, _ = env.reset(seed=seed + episodes)
            done = False
            while not done and len(labels) < steps:
                label = rule_action(obs)
                action = int(rng.integers(0, 5)) if rng.random() < .03 else label
                observations.append(obs.copy())
                labels.append(label)
                executed.append(action)
                obs, _, terminal, truncated, _ = env.step(action)
                done = terminal or truncated
            crashes += int(env.unwrapped.vehicle.crashed)
            episodes += 1
        finally:
            env.close()
        if episodes % 50 == 0:
            print(f"demonstrations {len(labels)}/{steps} in {episodes} episodes", flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, observations=np.asarray(observations, np.float32),
                        actions=np.asarray(labels, np.int64), executed_actions=np.asarray(executed, np.int64))
    write_json(path.with_suffix(".json"), {"env_version": ENV_VERSION,
        "transitions": steps, "episodes": episodes, "crashes": crashes,
        "seed": seed, "scenario_set": SCENARIOS,
        "random_action_probability": .03,
        "label_counts": np.bincount(labels, minlength=5).tolist(),
        "sha256": sha256(path),
        "environment_source_sha256": sha256(Path(__file__).with_name("driving_env_v3.py")),
        "teacher": "transparent 30-feature rule_action; no rule executes during neural inference"})
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=50000)
    parser.add_argument("--seed", type=int, default=17031)
    args = parser.parse_args()
    if args.steps <= 0:
        parser.error("steps must be positive")
    print(collect(args.steps, args.seed), flush=True)


if __name__ == "__main__":
    main()
