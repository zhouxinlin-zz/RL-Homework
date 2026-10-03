"""Evaluate held-out roads, save every episode and report binomial uncertainty.

Train/validation/test seeds are disjoint. Evaluation never chooses the checkpoint.
python -m rl_course.benchmark --episodes 30 --workers 4
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import torch

from rl_course.academy import ACADEMY, CLASSES, write_json
from rl_course.game_env import POLICY_KEYS, make_game_env, road_risk

TEST_SEED_START = 71000
CONDITIONS = (("light", 30), ("normal", 30), ("dense", 30), ("normal", 60))
OUT = ACADEMY / "evaluation"


def interval(crashes: int, n: int) -> list[float]:
    """Wilson 95% confidence interval for a binomial proportion."""
    z = 1.95996398454
    fraction = crashes / n
    center = (fraction + z*z/(2*n)) / (1+z*z/n)
    half = z * math.sqrt(fraction*(1-fraction)/n + z*z/(4*n*n)) / (1+z*z/n)
    return [max(0, center-half), min(1, center+half)]


def evaluate_policy(policy: str, training_seed: int, episodes: int) -> dict:
    torch.set_num_threads(1)
    model = None
    metadata = {"policy": policy, "training_seed": None, "checkpoint_steps": 0, "training_steps": 0}
    if policy in POLICY_KEYS:
        folder = ACADEMY / f"{policy}_seed{training_seed}"
        model_file = folder / "best.zip"
        model = CLASSES[policy].load(str(model_file), device="cpu")
        best = json.loads((folder / "best.json").read_text(encoding="utf-8"))
        progress = json.loads((folder / "progress.json").read_text(encoding="utf-8"))
        metadata.update({"training_seed": training_seed, "checkpoint_steps": best["actual_timesteps"], "training_steps": progress["actual_timesteps"], "model_sha256": hashlib.sha256(model_file.read_bytes()).hexdigest(), "config": best["config"], "hyperparameters": best["hyperparameters"]})
    rows = []
    for scenario, duration in CONDITIONS:
        env = make_game_env(scenario, duration)
        try:
            for i in range(episodes):
                test_seed = TEST_SEED_START + i
                obs, _ = env.reset(seed=test_seed)
                env.action_space.seed(test_seed + 100000)
                start_x = float(env.unwrapped.vehicle.position[0])
                last_lane = env.unwrapped.vehicle.lane_index[2]
                lane_changes, danger_steps = 0, 0
                done, reward_sum, speeds, steps = False, 0.0, [], 0
                while not done:
                    if model is not None:
                        predicted, _ = model.predict(obs, deterministic=True)
                        action = int(np.asarray(predicted).item())
                    else:
                        action = int(env.action_space.sample()) if policy == "random" else 4 if policy == "cautious" and steps == 0 else 1
                    obs, reward, terminated, truncated, _ = env.step(action)
                    reward_sum += float(reward)
                    speeds.append(float(env.unwrapped.vehicle.speed) * 3.6)
                    lane = env.unwrapped.vehicle.lane_index[2]
                    lane_changes += int(lane != last_lane)
                    last_lane = lane
                    danger_steps += int(road_risk(env)["danger"])
                    steps += 1
                    done = terminated or truncated
                rows.append({"policy": policy, "training_seed": metadata["training_seed"], "scenario": scenario, "duration": duration, "test_seed": test_seed, "return": reward_sum, "steps": steps, "crashed": bool(env.unwrapped.vehicle.crashed), "time_s": float(env.unwrapped.time), "distance_m": float(env.unwrapped.vehicle.position[0])-start_x, "speed_kmh": float(np.mean(speeds)), "lane_changes": lane_changes, "danger_seconds": danger_steps/5})
            print(f"Evaluated {policy} seed={training_seed} {scenario}/{duration}s ({episodes} episodes)", flush=True)
        finally:
            env.close()
    OUT.mkdir(parents=True, exist_ok=True)
    shard = {"metadata": metadata, "episodes": rows}
    write_json(OUT / f"{policy}_seed{training_seed}.json", shard)
    return shard


def compile_report(policies, seeds):
    shards = []
    for policy in policies:
        for seed in (seeds if policy in POLICY_KEYS else [seeds[0]]):
            path = OUT / f"{policy}_seed{seed}.json"
            if path.exists():
                shards.append(json.loads(path.read_text(encoding="utf-8")))
    rows = [row for shard in shards for row in shard["episodes"]]
    if not rows:
        raise ValueError("No evaluation data to compile")
    with (OUT / "episodes.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    summaries = []
    for shard in shards:
        for scenario, duration in CONDITIONS:
            selected = [r for r in shard["episodes"] if r["scenario"] == scenario and r["duration"] == duration]
            crashes = sum(r["crashed"] for r in selected)
            summaries.append({"policy": shard["metadata"]["policy"], "training_seed": shard["metadata"]["training_seed"], "scenario": scenario, "duration": duration, "episodes": len(selected), "crashes": crashes, "crash_rate": crashes/len(selected), "crash_ci95": interval(crashes,len(selected)), **{f"mean_{key}": float(np.mean([r[key] for r in selected])) for key in ("return", "time_s", "distance_m", "speed_kmh", "lane_changes", "danger_seconds")}})
    paired = []
    # Paired bootstrap: compare PPO and mixed PPO on identical held-out road seeds.
    for seed in seeds:
        for scenario, duration in CONDITIONS:
            base = {r["test_seed"]: r for r in rows if r["policy"] == "ppo" and r["training_seed"] == seed and r["scenario"] == scenario and r["duration"] == duration}
            mixed = {r["test_seed"]: r for r in rows if r["policy"] == "ppo_mixed" and r["training_seed"] == seed and r["scenario"] == scenario and r["duration"] == duration}
            shared = sorted(base.keys() & mixed.keys())
            if not shared: continue
            delta = np.array([int(mixed[k]["crashed"]) - int(base[k]["crashed"]) for k in shared], dtype=float)
            bootstrap = np.random.default_rng(42).choice(delta, size=(2000, len(delta)), replace=True).mean(axis=1)
            paired.append({"training_seed": seed, "scenario": scenario, "duration": duration, "pairs": len(shared), "crash_rate_delta_mixed_minus_ppo": float(delta.mean()), "paired_bootstrap_ci95": np.quantile(bootstrap, [.025, .975]).tolist()})
    report = {"test_seed_start": TEST_SEED_START, "total_episodes": len(rows), "models": [s["metadata"] for s in shards], "summary": summaries, "paired_ppo_ablation": paired, "limitations": ["Confidence intervals describe road-seed variation for the tested checkpoints, not variation across all possible training runs.", "Checkpoint selection used validation seeds 5101-5103; test seeds start at 71000.", "Night/coast/city visuals do not change the observation or physics.", "DQN hyperparameters were tuned after failed validation; the failed run is preserved separately."]}
    write_json(OUT / "report.json", report)
    print(f"Saved {len(rows)} real test episodes to {OUT}", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=30)
    parser.add_argument("--seeds", nargs="+", type=int, default=[42])
    parser.add_argument("--policies", nargs="+", choices=[*POLICY_KEYS, "random", "cruise", "cautious"], default=[*POLICY_KEYS, "random", "cruise", "cautious"])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--compile-only", action="store_true")
    args = parser.parse_args()
    if args.episodes <= 0 or args.workers <= 0: parser.error("episodes and workers must be positive")
    if not args.compile_only:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            jobs = [pool.submit(evaluate_policy, p, s, args.episodes) for p in args.policies for s in (args.seeds if p in POLICY_KEYS else [args.seeds[0]])]
            for job in as_completed(jobs): job.result()
    compile_report(args.policies, args.seeds)


if __name__ == "__main__": main()
