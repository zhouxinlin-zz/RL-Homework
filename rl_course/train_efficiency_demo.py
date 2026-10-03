"""Test whether a stronger progress incentive improves the classroom duel.

This is an experimental reward variant. Observation, action, physics and
formation traffic remain identical to the deployed 3.1 challenge roads.
Checkpoints must be compared on development roads before use in the game.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import time

import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from rl_course.driving_env_v3 import ChallengeEnv, ENV_VERSION
from rl_course.evaluate_v3 import OUT
from rl_course.v2_metrics import sha256, write_json


class EfficiencyEnv(ChallengeEnv):
    def _reward(self, action):
        reward = super()._reward(action)
        if self.config["reward_mode"] == "shaped" and not self.vehicle.crashed:
            progress = max(0.0, float(self.vehicle.position[0] - self._previous_x))
            reward += 0.045 * progress + 0.3 * self._new_overtakes
        return reward


def make_env():
    return EfficiencyEnv(config={"scenario": "weave", "duration": 45,
                                 "reward_mode": "shaped"})


class SaveSteps(BaseCallback):
    def __init__(self, folder: Path, every: int):
        super().__init__()
        self.folder = folder
        self.every = every

    def _on_step(self):
        if self.num_timesteps % self.every == 0:
            steps = self.num_timesteps
            self.model.save(str(self.folder / f"step_{steps}.zip"))
            print(f"efficiency demo: {steps} steps saved", flush=True)
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="demo_efficiency_s62")
    parser.add_argument("--steps", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=62)
    parser.add_argument("--source", type=Path,
                        default=OUT / "safe_imitation_s23/checkpoints/step_200000.zip")
    args = parser.parse_args()
    if args.steps <= 0 or args.steps % 4:
        parser.error("steps must be positive and divisible by 4")
    folder = OUT / args.run
    if folder.exists():
        parser.error(f"run already exists: {folder}")
    folder.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    env = DummyVecEnv([lambda: Monitor(make_env()) for _ in range(4)])
    env.seed(args.seed)
    model = PPO.load(str(args.source), env=env, device="cpu")
    model.num_timesteps = 0
    metadata = {"run_id": args.run, "seed": args.seed,
                "source": str(args.source), "source_sha256": sha256(args.source),
                "environment_version": ENV_VERSION, "scenario": "weave",
                "reward_change": "additional 0.045 per metre and 0.3 per new overtake; original -30 collision and unsafe lane penalties retained",
                "reward_source_sha256": sha256(Path(__file__)),
                "requested_timesteps": args.steps, "parallel_envs": 4,
                "checkpoint_interval": 25000,
                "selection_split": "development seeds 531100-531179",
                "fresh_holdout_start_if_selected": 1331100}
    write_json(folder / "config.json", metadata)
    model.save(str(folder / "step_0.zip"))
    started = time.perf_counter()
    try:
        model.learn(total_timesteps=args.steps, callback=SaveSteps(folder, 25000),
                    reset_num_timesteps=True)
        if not (folder / f"step_{model.num_timesteps}.zip").exists():
            model.save(str(folder / f"step_{model.num_timesteps}.zip"))
        write_json(folder / "progress.json", {**metadata,
                   "actual_timesteps": model.num_timesteps,
                   "elapsed_s": round(time.perf_counter() - started, 1)})
    finally:
        env.close()


if __name__ == "__main__":
    main()
