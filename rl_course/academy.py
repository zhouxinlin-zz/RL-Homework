"""Train four real policies with checkpoints, held-out validation and repeatable jobs.

python -m rl_course.academy --steps 80000 --seeds 42 --workers 4
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import json
import os
from pathlib import Path
import time

import numpy as np
import torch
from stable_baselines3 import A2C, DQN, PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor

from rl_course.game_env import GAME_CONFIG, MixedTraffic, POLICY_KEYS, make_game_env

ROOT = Path(__file__).resolve().parents[1]
ACADEMY = ROOT / "artifacts" / "academy"
CLASSES = {"dqn": DQN, "ppo": PPO, "a2c": A2C, "ppo_mixed": PPO}
VALIDATION_SEEDS = (5101, 5102, 5103)


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def assess(model, seeds=VALIDATION_SEEDS) -> dict:
    results = []
    for scenario in ("light", "normal", "dense"):
        env = make_game_env(scenario)
        try:
            for seed in seeds:
                obs, _ = env.reset(seed=seed)
                done, total, speeds = False, 0.0, []
                while not done:
                    action, _ = model.predict(obs, deterministic=True)
                    obs, reward, terminated, truncated, _ = env.step(int(action))
                    total += float(reward)
                    speeds.append(float(env.unwrapped.vehicle.speed) * 3.6)
                    done = terminated or truncated
                results.append({"scenario": scenario, "seed": seed, "return": total, "crashed": bool(env.unwrapped.vehicle.crashed), "speed_kmh": float(np.mean(speeds)), "time_s": float(env.unwrapped.time)})
        finally:
            env.close()
    return {"mean_return": float(np.mean([r["return"] for r in results])), "crash_rate": float(np.mean([r["crashed"] for r in results])), "episodes": results}


class TrainingLog(BaseCallback):
    def __init__(self, folder: Path, metadata: dict, checkpoint_every: int):
        super().__init__()
        self.folder, self.metadata, self.interval = folder, metadata, checkpoint_every
        self.started = time.perf_counter()
        self.last_report = 0
        self.last_checkpoint = 0
        self.best = -float("inf")
        self.validations = []
        self.episode_file = (folder / "episodes.csv").open("w", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.episode_file, fieldnames=["timesteps", "episode", "return", "length"])
        self.writer.writeheader()
        self.episodes = 0

    def report(self, status="training"):
        self.episode_file.flush()
        write_json(self.folder / "progress.json", {**self.metadata, "status": status, "actual_timesteps": self.num_timesteps, "episodes": self.episodes, "elapsed_s": round(time.perf_counter() - self.started, 1), "validations": self.validations})

    def checkpoint(self):
        self.model.save(str(self.folder / "latest"))
        result = assess(self.model)
        self.validations.append({"timesteps": self.num_timesteps, **result})
        if result["mean_return"] > self.best:
            self.best = result["mean_return"]
            temp = self.folder / "candidate.zip"
            self.model.save(str(temp))
            os.replace(temp, self.folder / "best.zip")
            write_json(self.folder / "best.json", {**self.metadata, "actual_timesteps": self.num_timesteps, "validation": result})
        self.last_checkpoint = self.num_timesteps
        self.report()
        print(f"{self.metadata['policy']} seed={self.metadata['seed']} steps={self.num_timesteps} val_return={result['mean_return']:.1f} crash={result['crash_rate']:.2f}", flush=True)

    def _on_step(self):
        for info in self.locals.get("infos", []):
            episode = info.get("episode")
            if episode:
                self.episodes += 1
                self.writer.writerow({"timesteps": self.num_timesteps, "episode": self.episodes, "return": episode["r"], "length": episode["l"]})
        if self.num_timesteps - self.last_report >= 1000:
            self.report()
            self.last_report = self.num_timesteps
        if self.num_timesteps - self.last_checkpoint >= self.interval:
            self.checkpoint()
        return True


def train_one(policy: str, seed: int, steps: int, checkpoint_every: int = 20000) -> dict:
    torch.set_num_threads(1)
    folder = ACADEMY / f"{policy}_seed{seed}"
    folder.mkdir(parents=True, exist_ok=True)
    prior = folder / "progress.json"
    if prior.exists():
        existing = json.loads(prior.read_text(encoding="utf-8"))
        if existing.get("status") == "complete" and existing.get("actual_timesteps", 0) >= steps:
            return existing
    env = Monitor(MixedTraffic(seed) if policy == "ppo_mixed" else make_game_env())
    common = dict(env=env, seed=seed, device="cpu", verbose=0, policy_kwargs={"net_arch": [128, 128]}, gamma=0.99)
    if policy == "dqn":
        common["gamma"] = 0.95
        model = DQN("MlpPolicy", learning_rate=5e-4, buffer_size=60000, learning_starts=1000, batch_size=64, train_freq=1, gradient_steps=1, target_update_interval=250, exploration_fraction=0.35, exploration_final_eps=0.05, **common)
    elif policy == "a2c":
        model = A2C("MlpPolicy", learning_rate=7e-4, n_steps=32, gae_lambda=0.95, ent_coef=0.01, normalize_advantage=True, **common)
    else:
        model = PPO("MlpPolicy", learning_rate=3e-4, n_steps=1024, batch_size=64, n_epochs=10, gae_lambda=0.95, ent_coef=0.01, **common)
    metadata = {"policy": policy, "algorithm": "ppo" if policy == "ppo_mixed" else policy, "seed": seed, "requested_timesteps": steps, "training_scenarios": ["light", "normal", "dense"] if policy == "ppo_mixed" else ["normal"], "config": GAME_CONFIG, "validation_seeds": list(VALIDATION_SEEDS), "hyperparameters": {key: getattr(model, key, None) for key in ("learning_rate", "gamma", "n_steps", "batch_size", "n_epochs", "ent_coef", "gae_lambda", "buffer_size", "learning_starts", "target_update_interval", "exploration_fraction")}}
    write_json(folder / "config.json", metadata)
    logger = TrainingLog(folder, metadata, checkpoint_every)
    try:
        model.learn(total_timesteps=steps, callback=logger)
        if logger.last_checkpoint != model.num_timesteps:
            logger.checkpoint()
        logger.report("complete")
    except BaseException:
        logger.report("interrupted")
        raise
    finally:
        logger.episode_file.close()
        env.close()
    return json.loads((folder / "progress.json").read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=80000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42])
    parser.add_argument("--policies", choices=POLICY_KEYS, nargs="+", default=list(POLICY_KEYS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--checkpoint-every", type=int, default=20000)
    args = parser.parse_args()
    if min(args.steps, args.workers, args.checkpoint_every) <= 0:
        parser.error("steps, workers and checkpoint-every must be positive")
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = [pool.submit(train_one, policy, seed, args.steps, args.checkpoint_every) for seed in args.seeds for policy in args.policies]
        for job in as_completed(jobs):
            result = job.result()
            print(f"Completed {result['policy']} seed={result['seed']}: {result['actual_timesteps']} steps", flush=True)


if __name__ == "__main__":
    main()
