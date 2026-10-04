"""PPO refinement with a training-only reference policy on close-following states.

The reference supplies an auxiliary KL loss after each PPO update. It never
selects or overrides game actions. Saved weights load with ordinary SB3 PPO.
"""
from __future__ import annotations

import argparse
from functools import partial
from pathlib import Path

import torch
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import SubprocVecEnv

from rl_course.driving_env import road_risk_v2
from rl_course.train_refinement import RefinementRoad, Checkpoints
from rl_course.train_challenge_models import evaluate
from rl_course.v2_metrics import ROOT, sha256, write_json

OUT = ROOT / "artifacts/experiments_v3/iteration_6"
SOURCE = ROOT / "artifacts/experiments_v3/iteration_5/ppo_s91/step_114688.zip"
REFERENCE = ROOT / "artifacts/experiments_v3/deployment/v3_expert-b4f0d5f66de4.zip"
DEV_START, SELECTION_START, TEST_START = 841100, 841200, 2741100


def following_risk(observations):
    """Use the same observed bumper gaps, including the target lane while turning."""
    traffic = observations[:, 6:].reshape(-1, 3, 8)
    gap, closing = traffic[:, :, 0] * 120, -traffic[:, :, 1] * 15
    lane_risk = (traffic[:, :, 2] > .5) & ((gap < 20) | ((closing > .1) & (gap < closing * 3.5)))
    lane = (observations[:, 2] + 1).round().long().clamp(0, 2)
    target = (observations[:, 3] + 1).round().long().clamp(0, 2)
    return lane_risk.gather(1, lane[:, None]).squeeze(1) | lane_risk.gather(1, target[:, None]).squeeze(1)


class SafetyRoad(RefinementRoad):
    def _reward(self, action):
        reward = super()._reward(action)
        if not self.vehicle.crashed and self.vehicle.on_road and road_risk_v2(self)["danger"]:
            reward -= .25
        return reward


class AnchoredPPO(PPO):
    reference_policy = None
    anchor_strength = .5

    def _excluded_save_params(self):
        return super()._excluded_save_params() + ["reference_policy"]

    def train(self):
        super().train()
        if self.reference_policy is None:
            raise ValueError("A frozen reference policy is required for training.")
        losses = []
        # One additional pass over current rollout observations; no test data.
        for batch in self.rollout_buffer.get(self.batch_size):
            mask = following_risk(batch.observations)
            if not mask.any():
                continue
            observations = batch.observations[mask]
            with torch.no_grad():
                reference = self.reference_policy.get_distribution(observations).distribution
            current = self.policy.get_distribution(observations).distribution
            loss = self.anchor_strength * torch.distributions.kl_divergence(reference, current).mean()
            self.policy.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm)
            self.policy.optimizer.step()
            losses.append(float(loss.detach()))
        self.logger.record("train/reference_kl_loss", sum(losses) / max(1, len(losses)))


def environment(seed):
    return Monitor(SafetyRoad(seed))


def make_policy(env, seed, anchor_strength):
    # SB3.load restores the checkpoint's RNG seed. Load BOTH sources before
    # constructing the new learner, so its seed controls sampling and updates.
    initial = PPO.load(SOURCE, device="cpu")
    reference = PPO.load(REFERENCE, device="cpu").policy
    model = AnchoredPPO("MlpPolicy", env, seed=seed, device="cpu", learning_rate=5e-6,
        n_steps=512, batch_size=256, n_epochs=4, gamma=.99, gae_lambda=.95,
        clip_range=.05, target_kl=.01, ent_coef=.001, policy_kwargs={"net_arch": [128, 128]})
    model.policy.load_state_dict(initial.policy.state_dict())
    model.reference_policy = reference
    model.reference_policy.set_training_mode(False)
    model.reference_policy.requires_grad_(False)
    model.anchor_strength = anchor_strength
    return model


class SafetyCheckpoints(Checkpoints):
    def save(self):
        # Keep iteration_5's executable and evidence unchanged.
        import time
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--steps", type=int, default=65536)
    parser.add_argument("--anchor-strength", type=float, default=.5)
    args = parser.parse_args()
    if args.steps <= 0 or args.anchor_strength <= 0:
        parser.error("steps and anchor strength must be positive")
    folder = OUT / f"ppo_s{args.seed}"
    folder.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    env = SubprocVecEnv([partial(environment, args.seed + i * 101) for i in range(4)], start_method="spawn")
    try:
        model = make_policy(env, args.seed, args.anchor_strength)
        metadata = {"algorithm": "ppo", "seed": args.seed, "requested_steps": args.steps,
            "env_version": "3.1", "source": SOURCE.relative_to(ROOT).as_posix(), "source_sha256": sha256(SOURCE),
            "reference": REFERENCE.relative_to(ROOT).as_posix(), "reference_sha256": sha256(REFERENCE),
            "training_source_sha256": sha256(Path(__file__)),
            "base_training_source_sha256": sha256(ROOT / "rl_course/train_refinement.py"),
            "environment_source_sha256": sha256(ROOT / "rl_course/driving_env_v3.py"),
            "initialization": "iteration_5 PPO actor and critic; fresh optimizer; explicit training seed",
            "method": "PPO efficiency refinement with close-following reference KL retention",
            "reward": "iteration_5 reward; additional -0.25 per dangerous-following step while safe and on-road",
            "anchor_strength": args.anchor_strength, "anchor_epochs": 1,
            "anchor_condition": "front bumper gap <20m or positive closing TTC <3.5s in current or target lane",
            "route_probabilities": [.2, .2, .6], "durations": [35, 45, 55],
            "learning_rate": 5e-6, "clip_range": .05, "target_kl": .01,
            "n_envs": 4, "n_steps": 512, "batch_size": 256, "n_epochs": 4,
            "gamma": .99, "gae_lambda": .95, "ent_coef": .001,
            "development_start": DEV_START, "selection_start": SELECTION_START,
            "test_start": TEST_START, "test_count_per_route": 100,
            "promotion_gate": "no more crashes overall or per route; higher overall qualification and score; no route qualification regression"}
        write_json(folder / "config.json", metadata)
        callback = SafetyCheckpoints(folder, metadata)
        model.learn(total_timesteps=args.steps, callback=callback)
        if callback.last != model.num_timesteps:
            callback.save()
    finally:
        env.close()


if __name__ == "__main__":
    main()
