"""Fine-tune or train PPO on versioned formation traffic.

Development roads select checkpoints. The separate test seeds in evaluate_v3
are never used to pick a model. Pretraining provenance is recorded explicitly.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

import gymnasium as gym
import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from rl_course.driving_env_v3 import ENV_VERSION, SCENARIOS, make_challenge_env
from rl_course.evaluate_v3 import DEVELOPMENT_START, OUT
from rl_course.v2_metrics import episode, sha256, write_json


class ChallengeCurriculum(gym.Wrapper):
    def __init__(self, seed: int):
        super().__init__(make_challenge_env("convoy", 45))
        self.scenario_rng = np.random.default_rng(seed)
        self.progress = 0.

    def set_progress(self, progress: float):
        self.progress = float(np.clip(progress, 0, 1))

    def reset(self, *, seed=None, options=None):
        if self.progress < .2:
            weights = [.65, .3, .05]
        elif self.progress < .5:
            weights = [.4, .4, .2]
        else:
            weights = [.33, .34, .33]
        scenario = str(self.scenario_rng.choice(SCENARIOS, p=weights))
        self.unwrapped.configure({"scenario": scenario})
        return self.env.reset(seed=seed, options=options)


def validate(model, seeds=range(DEVELOPMENT_START, DEVELOPMENT_START + 8)):
    rows = []
    for scenario in SCENARIOS:
        env = make_challenge_env(scenario, 45)
        try:
            rows.extend(episode(env, model=model, seed=seed) for seed in seeds)
        finally:
            env.close()
    return {"episodes": len(rows), "crashes": sum(row["crashed"] for row in rows),
            "completion_rate": float(np.mean([row["completed"] for row in rows])),
            "mean_quality": float(np.mean([row["quality"] for row in rows])),
            "mean_distance_m": float(np.mean([row["distance_m"] for row in rows])),
            "mean_overtakes": float(np.mean([row["overtakes"] for row in rows])),
            "mean_danger_seconds": float(np.mean([row["danger_seconds"] for row in rows])),
            "by_scenario": {name: {"crashes": sum(row["crashed"] for row in rows if row["scenario"] == name),
                                   "mean_distance_m": float(np.mean([row["distance_m"] for row in rows if row["scenario"] == name])),
                                   "mean_overtakes": float(np.mean([row["overtakes"] for row in rows if row["scenario"] == name]))}
                            for name in SCENARIOS}}


class Checkpoints(BaseCallback):
    def __init__(self, folder: Path, interval: int, progress_at: int, metadata: dict):
        super().__init__()
        self.folder, self.interval, self.progress_at, self.metadata = folder, interval, progress_at, metadata
        self.previous = json.loads((folder / "progress.json").read_text(encoding="utf-8")) if (folder / "progress.json").exists() else {}
        self.validations = self.previous.get("validations", [])
        self.last = max((r["timesteps"] for r in self.validations), default=0)
        self.best = max((r["mean_quality"] for r in self.validations), default=-float("inf"))
        self.started = time.perf_counter()

    def checkpoint(self):
        steps = self.model.num_timesteps
        result = validate(self.model)
        entry = {"timesteps": steps, **result}
        self.validations.append(entry)
        self.folder.joinpath("checkpoints").mkdir(exist_ok=True)
        self.model.save(str(self.folder / "checkpoints" / f"step_{steps}.zip"))
        self.model.save(str(self.folder / "latest.zip"))
        if result["mean_quality"] > self.best:
            self.best = result["mean_quality"]
            self.model.save(str(self.folder / "best.zip"))
            write_json(self.folder / "best.json", {**self.metadata, "checkpoint_steps": steps,
                                                    "validation": result})
        self.last = steps
        self.report()
        print(f"{self.metadata['run_id']} step={steps} quality={result['mean_quality']:.3f} "
              f"crashes={result['crashes']}/{result['episodes']} distance={result['mean_distance_m']:.1f} "
              f"passes={result['mean_overtakes']:.2f}", flush=True)

    def report(self):
        write_json(self.folder / "progress.json", {**self.metadata,
            "actual_timesteps": self.model.num_timesteps,
            "elapsed_session_s": round(time.perf_counter() - self.started, 1),
            "validations": self.validations})

    def _on_step(self):
        if self.num_timesteps % 10000 == 0:
            self.training_env.env_method("set_progress", min(1., self.num_timesteps / self.progress_at))
            print(f"{self.metadata['run_id']}: {self.num_timesteps} environment steps", flush=True)
        if self.num_timesteps - self.last >= self.interval:
            self.checkpoint()
        return True


def train(args):
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    folder = OUT / args.run
    if folder.exists() and not args.resume:
        raise ValueError(f"Run already exists: {folder}")
    folder.mkdir(parents=True, exist_ok=True)
    env = DummyVecEnv([lambda index=index: Monitor(ChallengeCurriculum(args.seed + index * 101))
                       for index in range(args.envs)])
    env.seed(args.seed)
    if args.resume:
        old = json.loads((folder / "config.json").read_text(encoding="utf-8"))
        for key in ("seed", "envs", "environment_source_sha256"):
            expected = args.seed if key == "seed" else args.envs if key == "envs" else sha256(Path(__file__).with_name("driving_env_v3.py"))
            if old[key] != expected:
                raise ValueError(f"Cannot resume after changing {key}")
        model = PPO.load(str(folder / "latest.zip"), env=env, device="cpu")
        metadata = {**old, "requested_timesteps": args.steps}
    else:
        if args.initialize:
            model = PPO.load(str(args.initialize), env=env, device="cpu")
            model.num_timesteps = 0
        else:
            model = PPO("MlpPolicy", env, seed=args.seed, device="cpu", verbose=0,
                        policy_kwargs={"net_arch": [128, 128]}, learning_rate=3e-4,
                        n_steps=512, batch_size=256, n_epochs=8, gamma=.99,
                        gae_lambda=.95, ent_coef=.008, clip_range=.2)
        imitation = None
        if args.demonstrations:
            from rl_course.demonstrations_v2 import warm_start
            imitation = warm_start(model, args.demonstrations, args.seed, epochs=args.imitation_epochs)
            write_json(folder / "imitation.json", imitation)
            model.save(str(folder / "actor_pretrained.zip"))
        metadata = {"run_id": args.run, "algorithm": "ppo", "seed": args.seed,
                    "env_version": ENV_VERSION, "envs": args.envs,
                    "requested_timesteps": args.steps,
                    "initialize_path": str(args.initialize) if args.initialize else None,
                    "initialize_sha256": sha256(args.initialize) if args.initialize else None,
                    "demonstrations_path": str(args.demonstrations) if args.demonstrations else None,
                    "demonstrations_sha256": sha256(args.demonstrations) if args.demonstrations else None,
                    "imitation_epochs": args.imitation_epochs if args.demonstrations else 0,
                    "imitation_transitions": imitation["transitions"] if imitation else 0,
                    "environment_source_sha256": sha256(Path(__file__).with_name("driving_env_v3.py")),
                    "training_source_sha256": sha256(Path(__file__)),
                    "validation_seed_start": DEVELOPMENT_START,
                    "validation_seed_count_per_scenario": 8,
                    "test_seed_start": 931100,
                    "selection_metric": "v2_metrics.episode quality, pooled across 3 scenarios"}
        write_json(folder / "config.json", metadata)
    callback = Checkpoints(folder, args.checkpoint_every, args.curriculum_steps, metadata)
    callback.init_callback(model)
    try:
        if not args.resume:
            callback.checkpoint()
        remaining = max(0, args.steps - model.num_timesteps)
        if remaining:
            model.learn(total_timesteps=remaining, callback=callback, reset_num_timesteps=not args.resume)
        if callback.last != model.num_timesteps:
            callback.checkpoint()
    finally:
        env.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--seed", type=int, default=47)
    parser.add_argument("--steps", type=int, default=200000)
    parser.add_argument("--envs", type=int, default=4)
    parser.add_argument("--checkpoint-every", type=int, default=50000)
    parser.add_argument("--curriculum-steps", type=int, default=120000)
    parser.add_argument("--initialize", type=Path)
    parser.add_argument("--demonstrations", type=Path)
    parser.add_argument("--imitation-epochs", type=int, default=30)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if min(args.steps, args.envs, args.checkpoint_every, args.curriculum_steps) <= 0:
        parser.error("all counts must be positive")
    if args.initialize and args.demonstrations:
        parser.error("choose either a transfer model or rule demonstrations")
    train(args)


if __name__ == "__main__":
    main()
