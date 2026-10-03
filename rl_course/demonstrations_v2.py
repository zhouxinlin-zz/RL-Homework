"""Optional transparent rule demonstrations for PPO actor warm-start.

The resulting actor is a neural network. Rules are never called during its
deployment or reinforcement-learning fine-tuning. Dataset collection is recorded
separately from RL environment-step budgets.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from rl_course.v2_metrics import EXPERIMENTS, rule_action, sha256, write_json


def collect(steps=60000, seed=17011):
    from rl_course.driving_env import ENV_VERSION, make_driving_env
    destination = EXPERIMENTS / "demonstrations" / f"rule_{steps}_s{seed}.npz"
    if destination.exists():
        raise ValueError(f"Dataset already exists: {destination}")
    rng = np.random.default_rng(seed)
    observations, labels, applied_actions = [], [], []
    episodes, crashes = 0, 0
    while len(labels) < steps:
        scenario = str(rng.choice(["light", "normal", "dense"], p=[.2, .4, .4]))
        env = make_driving_env(scenario, 45)
        try:
            obs, _ = env.reset(seed=seed + episodes)
            done = False
            while not done and len(labels) < steps:
                label = rule_action(obs)
                # Small action perturbations expose the teacher to recovery states.
                action = int(rng.integers(0, 5)) if rng.random() < .03 else label
                observations.append(obs.copy())
                labels.append(label)
                applied_actions.append(action)
                obs, _, terminated, truncated, _ = env.step(action)
                done = terminated or truncated
            crashes += int(env.unwrapped.vehicle.crashed)
            episodes += 1
        finally:
            env.close()
        if episodes % 50 == 0:
            print(f"Demonstrations: {len(labels)}/{steps} transitions in {episodes} episodes", flush=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(destination, observations=np.array(observations, dtype=np.float32),
                        actions=np.array(labels, dtype=np.int64),
                        executed_actions=np.array(applied_actions, dtype=np.int64))
    write_json(destination.with_suffix(".json"), {"env_version": ENV_VERSION, "seed": seed,
        "transitions": steps, "episodes": episodes, "crashes": crashes,
        "source": "rule_action: same 30-dimensional observation and five actions",
        "random_action_probability": .03, "scenarios_probability": {"light": .2, "normal": .4, "dense": .4},
        "label_counts": np.bincount(labels, minlength=5).tolist(), "sha256": sha256(destination),
        "environment_source_sha256": sha256(Path(__file__).with_name("driving_env.py"))})
    print(f"Saved {destination}", flush=True)


def warm_start(model, path: Path, seed: int, epochs=60):
    data = np.load(path)
    observations = torch.as_tensor(data["observations"], dtype=torch.float32, device=model.device)
    labels = torch.as_tensor(data["actions"], dtype=torch.long, device=model.device)
    generator = torch.Generator(device="cpu").manual_seed(seed)
    # Split whole driving episodes, so adjacent frames of the same trajectory do
    # not leak across the imitation accuracy check. Driving quality is evaluated
    # separately on fixed roads that were not used to collect demonstrations.
    remaining = data["observations"][:, 5]
    episode_ids = np.cumsum(np.r_[True, remaining[1:] > remaining[:-1] + .01]) - 1
    ids = torch.randperm(int(episode_ids.max()) + 1, generator=generator).numpy()
    cut = max(1, int(len(ids) * .9))
    validation_mask = np.isin(episode_ids, ids[cut:])
    training = torch.as_tensor(np.flatnonzero(~validation_mask), dtype=torch.long)
    validation = torch.as_tensor(np.flatnonzero(validation_mask), dtype=torch.long)
    if not len(validation):
        raise ValueError("Demonstration dataset must contain at least two episodes")
    counts = torch.bincount(labels[training], minlength=5).float()
    weights = torch.sqrt(counts.max() / counts.clamp_min(1)).clamp(max=20).to(model.device)
    optimizer = torch.optim.Adam(model.policy.parameters(), lr=5e-4)
    history = []
    for epoch in range(epochs):
        model.policy.set_training_mode(True)
        shuffled = training[torch.randperm(len(training), generator=generator)]
        losses = []
        for start in range(0, len(shuffled), 512):
            batch = shuffled[start:start+512]
            distribution = model.policy.get_distribution(observations[batch]).distribution
            loss = F.cross_entropy(distribution.logits, labels[batch], weight=weights)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.policy.parameters(), 1.)
            optimizer.step()
            losses.append(float(loss.item()))
        model.policy.set_training_mode(False)
        with torch.no_grad():
            prediction = model.policy.get_distribution(observations[validation]).distribution.logits.argmax(dim=1)
            accuracy = float((prediction == labels[validation]).float().mean())
            recalls = []
            for action in range(5):
                mask = labels[validation] == action
                recalls.append(float((prediction[mask] == action).float().mean()) if mask.any() else None)
        row = {"epoch": epoch+1, "loss": float(np.mean(losses)), "validation_accuracy": accuracy,
               "validation_recall_per_action": recalls}
        history.append(row)
        print(f"Actor imitation epoch {epoch+1}: loss={row['loss']:.3f}, action accuracy={accuracy:.2%}", flush=True)
    return {"dataset": str(path), "dataset_sha256": sha256(path), "transitions": len(labels),
            "validation_split": "10 percent held-out demonstration episodes, selected with run seed",
            "epochs": epochs, "class_weights": weights.cpu().tolist(), "history": history,
            "note": "Actor-only imitation. PPO reinforcement learning follows; no rule executes at inference."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=60000)
    parser.add_argument("--seed", type=int, default=17011)
    args = parser.parse_args()
    if args.steps <= 0:
        parser.error("steps must be positive")
    collect(args.steps, args.seed)


if __name__ == "__main__":
    main()
