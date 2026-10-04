"""PPO refinement on actual game durations, with pressure-heavy sampling.

The game environment, observations, actions and scoring are unchanged. Only
training rewards and route sampling differ. Development roads select weights;
the independent test set is reserved for a single frozen release candidate.
"""
from __future__ import annotations

import argparse
from functools import partial
from pathlib import Path
import time

import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import SubprocVecEnv

from rl_course.challenge_rules import CHALLENGE_TRACKS
from rl_course.driving_env_v3 import ChallengeEnv
from rl_course.train_challenge_models import evaluate
from rl_course.v2_metrics import ROOT, sha256, write_json

OUT = ROOT / "artifacts/experiments_v3/iteration_5"
SOURCE = ROOT / "artifacts/experiments_v3/deployment/v3_expert-b4f0d5f66de4.zip"
DEV_START, SELECTION_START, TEST_START = 741100, 741200, 1741100


class RefinementRoad(ChallengeEnv):
    def __init__(self, seed: int):
        self.route_rng = np.random.default_rng(seed)
        self.training_track = CHALLENGE_TRACKS[0]
        super().__init__(config={"scenario": "convoy", "duration": 35})

    def reset(self, *, seed=None, options=None):
        self.training_track = CHALLENGE_TRACKS[int(self.route_rng.choice(3, p=[.2, .2, .6]))]
        self.configure({"scenario": self.training_track["scenario"], "duration": self.training_track["duration"]})
        return super().reset(seed=seed, options=options)

    def _reward(self, action):
        reward = super()._reward(action)
        if self.vehicle.crashed or not self.vehicle.on_road:
            return reward - 30.0
        progress = max(0.0, float(self.vehicle.position[0] - self._previous_x))
        reward += .015 * progress
        if self.completed and self.distance_m >= self.training_track["target_m"]:
            reward += 6.0
        return reward


def environment(seed):
    return Monitor(RefinementRoad(seed))


class Checkpoints(BaseCallback):
    def __init__(self, folder, metadata, interval=16384):
        super().__init__()
        self.folder, self.metadata, self.interval = folder, metadata, interval
        self.last = -interval
        self.history = []
        self.started = time.perf_counter()

    def save(self):
        steps = self.model.num_timesteps
        path = self.folder / f"step_{steps}.zip"
        self.model.save(path)
        report = evaluate(self.model, count=8, seed_start=DEV_START, policy=self.folder.name)
        report["model_sha256"] = sha256(path)
        write_json(self.folder / f"development_{steps}.json", report)
        self.history.append({"steps": steps, **report["overall"], "routes": report["summary"]})
        self.last = steps
        write_json(self.folder / "progress.json", {**self.metadata, "actual_steps": steps,
            "elapsed_s": round(time.perf_counter() - self.started, 1), "validations": self.history})
        print(f"{self.folder.name} {steps}: {report['overall']} pressure={report['summary']['pressure']['qualification_rate']:.3f}", flush=True)

    def _on_rollout_start(self):
        # Save after the preceding PPO update, never midway through its rollout.
        if self.model.num_timesteps - self.last >= self.interval:
            self.save()

    def _on_step(self):
        if self.num_timesteps % 8192 == 0:
            print(f"{self.folder.name}: {self.num_timesteps} interactions", flush=True)
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--steps", type=int, default=120000)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    args = parser.parse_args()
    if args.steps <= 0 or not 0 < args.learning_rate <= .001:
        parser.error("steps and learning rate must be positive; learning rate <= .001")
    folder = OUT / f"ppo_s{args.seed}"
    folder.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    env = SubprocVecEnv([partial(environment, args.seed + i * 101) for i in range(4)], start_method="spawn")
    try:
        teacher = PPO.load(SOURCE, device="cpu")
        model = PPO("MlpPolicy", env, seed=args.seed, device="cpu", learning_rate=args.learning_rate,
            n_steps=512, batch_size=256, n_epochs=4, gamma=.99, gae_lambda=.95,
            clip_range=.08, target_kl=.01, ent_coef=.001, policy_kwargs={"net_arch": [128, 128]})
        model.policy.load_state_dict(teacher.policy.state_dict())
        del teacher
        metadata = {"algorithm": "ppo", "seed": args.seed, "requested_steps": args.steps,
            "env_version": "3.1", "source": SOURCE.relative_to(ROOT).as_posix(), "source_sha256": sha256(SOURCE),
            "training_source_sha256": sha256(Path(__file__)),
            "environment_source_sha256": sha256(ROOT / "rl_course/driving_env_v3.py"),
            "initialization": "deployed PPO actor and critic; fresh optimizer; explicit training seed",
            "reward": "v3.1 + .015/metre while safe and on-road; +6 for qualified completion; collision penalty -60 total",
            "route_probabilities": [.2, .2, .6], "durations": [35, 45, 55],
            "learning_rate": args.learning_rate, "clip_range": .08, "target_kl": .01,
            "n_envs": 4, "n_steps": 512, "batch_size": 256, "n_epochs": 4,
            "gamma": .99, "gae_lambda": .95, "ent_coef": .001,
            "development_start": DEV_START, "selection_start": SELECTION_START,
            "test_start": TEST_START, "test_count_per_route": 100,
            "promotion_gate": "no more crashes overall or per route; higher overall qualification and score; no route qualification regression"}
        write_json(folder / "config.json", metadata)
        callback = Checkpoints(folder, metadata)
        model.learn(total_timesteps=args.steps, callback=callback)
        if callback.last != model.num_timesteps:
            callback.save()
    finally:
        env.close()


if __name__ == "__main__":
    main()
