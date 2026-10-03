"""Train and compare actual PPO, A2C and DQN policies on the same v3.1 roads.

Only the training reward changes; observations, vehicle physics and game scoring
are shared with the released environment. Development seeds select checkpoints.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import time

import numpy as np
import torch
from stable_baselines3 import PPO, A2C, DQN
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from rl_course.challenge_rules import CHALLENGE_TRACKS
from rl_course.driving_env_v3 import ChallengeEnv, make_challenge_env
from rl_course.game_rules import performance
from rl_course.v2_metrics import episode, sha256, write_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/experiments_v3/iteration_4"
CLASSES = {"ppo": PPO, "a2c": A2C, "dqn": DQN}
DEV_START = 631100
HOLDOUT_START = 1631100


class TrainingRoad(ChallengeEnv):
    def __init__(self, seed):
        self.route_rng = np.random.default_rng(seed)
        super().__init__(config={"scenario": "weave", "duration": 45})

    def reset(self, *, seed=None, options=None):
        track = CHALLENGE_TRACKS[int(self.route_rng.choice(3, p=[.2, .4, .4]))]
        self.configure({"scenario": track["scenario"], "duration": track["duration"]})
        return super().reset(seed=seed, options=options)

    def _reward(self, action):
        reward = super()._reward(action)
        if self.vehicle.crashed or not self.vehicle.on_road:
            return reward - 30.0  # -60 total terminal penalty.
        progress = max(0.0, float(self.vehicle.position[0] - self._previous_x))
        return reward + .035 * progress + .2 * self._new_overtakes


def evaluate(model, count=12, seed_start=DEV_START, policy="candidate"):
    rows = []
    for track in CHALLENGE_TRACKS:
        env = make_challenge_env(track["scenario"], track["duration"])
        try:
            for seed in range(seed_start, seed_start + count):
                row = episode(env, model=model, baseline=policy if model is None else None, seed=seed)
                row.update(performance(track, done=True, crashed=not row["completed"],
                    distance=row["distance_m"], overtakes=row["overtakes"], danger_seconds=row["danger_seconds"]))
                rows.append(row)
        finally:
            env.close()
    def summarize(selected):
        return {"episodes": len(selected), "crashes": sum(r["crashed"] for r in selected),
            "qualification_rate": float(np.mean([r["qualified"] for r in selected])),
            "mean_score": float(np.mean([r["score"] for r in selected])),
            "mean_distance_m": float(np.mean([r["distance_m"] for r in selected])),
            "mean_overtakes": float(np.mean([r["overtakes"] for r in selected]))}
    return {"policy": policy, "seed_start": seed_start, "env_version": "3.1",
        "duration": "game_routes", "episodes_per_scenario": count,
        "overall": summarize(rows), "summary": {t["scenario"]: summarize([r for r in rows if r["scenario"] == t["scenario"]]) for t in CHALLENGE_TRACKS},
        "episodes": rows}


class Checkpoints(BaseCallback):
    def __init__(self, folder, metadata, interval):
        super().__init__()
        self.folder, self.metadata, self.interval = folder, metadata, interval
        self.last, self.history, self.best = -1, [], None
        self.started = time.perf_counter()

    def save(self):
        steps = self.model.num_timesteps
        path = self.folder / f"step_{steps}.zip"
        self.model.save(path)
        report = evaluate(self.model, policy=self.metadata["algorithm"])
        report["model_sha256"] = sha256(path)
        write_json(self.folder / f"development_{steps}.json", report)
        stats = report["overall"]
        # Safety comes first; efficiency is compared among equally safe candidates.
        rank = (-stats["crashes"], stats["qualification_rate"], stats["mean_score"])
        if self.best is None or rank > self.best:
            self.best = rank
            write_json(self.folder / "selected.json", {"path": str(path.relative_to(ROOT)),
                "sha256": sha256(path), "steps": steps, "development": stats})
        self.history.append({"steps": steps, **stats})
        self.last = steps
        write_json(self.folder / "progress.json", {**self.metadata, "actual_steps": steps,
            "elapsed_s": round(time.perf_counter() - self.started, 1), "validations": self.history})
        print(f"{self.metadata['algorithm']} step={steps}: {stats}", flush=True)

    def _on_step(self):
        if self.num_timesteps - self.last >= self.interval:
            self.save()
        elif self.num_timesteps % 10000 == 0:
            print(f"{self.metadata['algorithm']}: {self.num_timesteps} steps", flush=True)
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--algorithm", choices=CLASSES, required=True)
    parser.add_argument("--steps", type=int, default=150000)
    parser.add_argument("--seed", type=int, default=74)
    parser.add_argument("--initialize", type=Path)
    parser.add_argument("--interval", type=int, default=25000)
    args = parser.parse_args()
    folder = OUT / f"{args.algorithm}_s{args.seed}"
    folder.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    env = DummyVecEnv([lambda i=i: Monitor(TrainingRoad(args.seed + i * 101)) for i in range(4)])
    env.seed(args.seed)
    if args.initialize:
        model = CLASSES[args.algorithm].load(args.initialize, env=env, device="cpu")
        model.num_timesteps = 0
        if args.algorithm == "ppo":
            from stable_baselines3.common.utils import FloatSchedule
            model.learning_rate = 5e-5
            model.lr_schedule = FloatSchedule(5e-5)
            model.ent_coef = .002
    else:
        shared = dict(env=env, seed=args.seed, device="cpu", verbose=0, policy_kwargs={"net_arch": [128, 128]}, gamma=.99)
        if args.algorithm == "ppo":
            model = PPO("MlpPolicy", learning_rate=2e-4, n_steps=512, batch_size=256, n_epochs=8, ent_coef=.005, **shared)
        elif args.algorithm == "a2c":
            model = A2C("MlpPolicy", learning_rate=3e-4, n_steps=32, gae_lambda=.95, ent_coef=.01, normalize_advantage=True, **shared)
        else:
            model = DQN("MlpPolicy", learning_rate=2e-4, buffer_size=100000, learning_starts=4000,
                batch_size=128, train_freq=4, gradient_steps=1, target_update_interval=2000,
                exploration_fraction=.4, exploration_final_eps=.03, **shared)
    metadata = {"algorithm": args.algorithm, "seed": args.seed, "env_version": "3.1", "requested_steps": args.steps,
        "source": str(args.initialize) if args.initialize else None,
        "source_sha256": sha256(args.initialize) if args.initialize else None,
        "training_source_sha256": sha256(Path(__file__)),
        "environment_source_sha256": sha256(ROOT / "rl_course/driving_env_v3.py"),
        "reward": "original v3.1 + .035/metre + .2/overtake; total collision penalty -60",
        "development_start": DEV_START, "fresh_holdout_start": HOLDOUT_START,
        "selection": "fewest development crashes, then qualification, then score"}
    write_json(folder / "config.json", metadata)
    callback = Checkpoints(folder, metadata, args.interval)
    callback.init_callback(model)
    try:
        callback.save()
        model.learn(total_timesteps=args.steps, callback=callback)
        if callback.last != model.num_timesteps:
            callback.save()
    finally:
        env.close()


if __name__ == "__main__":
    main()
