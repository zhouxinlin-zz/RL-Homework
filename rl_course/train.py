"""Train DQN or PPO on the same normal-traffic environment.

Example: python -m rl_course.train --algo dqn --steps 20000 --seed 42
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from stable_baselines3 import DQN, PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor

from rl_course.environment import BASE_CONFIG, SCENARIOS, make_env


class EpisodeLogger(BaseCallback):
    def __init__(self) -> None:
        super().__init__()
        self.episodes: list[dict[str, float | int]] = []

    def _on_step(self) -> bool:
        for info in self.locals.get("infos", []):
            episode = info.get("episode")
            if episode is not None:
                self.episodes.append(
                    {
                        "timesteps": self.num_timesteps,
                        "episode": len(self.episodes) + 1,
                        "return": float(episode["r"]),
                        "length": int(episode["l"]),
                    }
                )
        return True


def train(algo: str, steps: int, seed: int, output_dir: Path) -> Path:
    if algo not in {"dqn", "ppo"}:
        raise ValueError("algo must be dqn or ppo")
    output_dir.mkdir(parents=True, exist_ok=True)
    env = Monitor(make_env("normal"))
    env.reset(seed=seed)
    env.action_space.seed(seed)

    common = dict(env=env, seed=seed, verbose=0, device="cpu", policy_kwargs={"net_arch": [256, 256]})
    if algo == "dqn":
        model = DQN(
            "MlpPolicy",
            learning_rate=5e-4,
            buffer_size=15000,
            learning_starts=200,
            batch_size=32,
            gamma=0.8,
            train_freq=1,
            gradient_steps=1,
            target_update_interval=50,
            **common,
        )
    else:
        model = PPO(
            "MlpPolicy",
            learning_rate=3e-4,
            n_steps=512,
            batch_size=64,
            gamma=0.95,
            **common,
        )

    logger = EpisodeLogger()
    try:
        model.learn(total_timesteps=steps, callback=logger, progress_bar=False)
        model_path = output_dir / f"{algo}_seed{seed}"
        model.save(str(model_path))
    finally:
        env.close()

    with (output_dir / f"{algo}_seed{seed}_episodes.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["timesteps", "episode", "return", "length"])
        writer.writeheader()
        writer.writerows(logger.episodes)

    metadata = {
        "algorithm": algo,
        "requested_timesteps": steps,
        "actual_timesteps": model.num_timesteps,
        "seed": seed,
        "environment": "highway-fast-v0",
        "scenario": "normal",
        "base_config": BASE_CONFIG,
        "scenario_config": SCENARIOS["normal"],
        "episodes_logged": len(logger.episodes),
    }
    (output_dir / f"{algo}_seed{seed}_meta.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return model_path.with_suffix(".zip")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--algo", choices=["dqn", "ppo"], required=True)
    parser.add_argument("--steps", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("artifacts/models"))
    args = parser.parse_args()
    if args.steps <= 0:
        parser.error("--steps must be positive")
    print(f"Saved model: {train(args.algo, args.steps, args.seed, args.output)}")


if __name__ == "__main__":
    main()
