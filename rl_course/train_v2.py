"""Train independent versioned driving runs, with resumable checkpoints.

Example: python -m rl_course.train_v2 --run ppo_curriculum_s11 --algorithm ppo
         --seed 11 --steps 200000 --traffic curriculum
Resuming restores network/optimizer (and DQN replay); environment episodes reset,
so a resumed run is intentionally not claimed to be bit-identical to an uninterrupted run.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import time

import torch
from stable_baselines3 import A2C, DQN, PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from rl_course.v2_metrics import EXPERIMENTS, VALIDATION_SEEDS, assess, write_json, sha256

CLASSES = {"ppo": PPO, "a2c": A2C, "dqn": DQN}


class TrainingLog(BaseCallback):
    def __init__(self, folder, metadata, interval, resumed, restored_steps=0):
        super().__init__()
        self.folder, self.metadata, self.interval = folder, metadata, interval
        previous = json.loads((folder / "progress.json").read_text(encoding="utf-8")) if resumed and (folder / "progress.json").exists() else {}
        self.validations = [item for item in previous.get("validations", []) if not resumed or item["timesteps"] <= restored_steps]
        self.best = max((item["mean_quality"] for item in self.validations), default=-float("inf"))
        self.last_checkpoint = max((item["timesteps"] for item in self.validations), default=0)
        self.last_save = restored_steps
        self.last_report = restored_steps
        self.episodes = previous.get("episodes", 0)
        # A power loss can leave CSV/progress newer than the last atomic model
        # checkpoint. Preserve that abandoned segment separately, then append
        # only after the actual restored network step count.
        episode_path = folder / "episodes.csv"
        if resumed and episode_path.exists():
            with episode_path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                fieldnames = reader.fieldnames
                rows = list(reader)
            retained = [row for row in rows if int(row["timesteps"]) <= restored_steps]
            discarded = [row for row in rows if int(row["timesteps"]) > restored_steps]
            if discarded:
                archive = folder / f"abandoned_after_{restored_steps}_{time.time_ns()}.csv"
                for destination, contents in ((archive, discarded), (episode_path.with_suffix(".tmp"), retained)):
                    with destination.open("w", encoding="utf-8", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(contents)
                os.replace(episode_path.with_suffix(".tmp"), episode_path)
            self.episodes = len(retained)
        self.prior_elapsed = previous.get("elapsed_s", 0)
        self.started = time.perf_counter()
        self.file = (folder / "episodes.csv").open("a" if resumed else "w", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.file, fieldnames=["timesteps", "episode", "return", "length", "completed", "distance_m", "overtakes", "danger_seconds"])
        if not resumed:
            self.writer.writeheader()

    def report(self, status="training"):
        self.file.flush()
        write_json(self.folder / "progress.json", {**self.metadata, "status": status,
                   "actual_timesteps": self.model.num_timesteps, "episodes": self.episodes,
                   "elapsed_s": round(self.prior_elapsed + time.perf_counter() - self.started, 1),
                   "validations": self.validations})

    def save_latest(self):
        self.model.save(str(self.folder / "latest.tmp.zip"))
        os.replace(self.folder / "latest.tmp.zip", self.folder / "latest.zip")
        if self.metadata["algorithm"] == "dqn":
            self.model.save_replay_buffer(str(self.folder / "replay.tmp.pkl"))
            os.replace(self.folder / "replay.tmp.pkl", self.folder / "replay.pkl")
        self.last_save = self.model.num_timesteps

    def checkpoint(self):
        self.save_latest()
        result = assess(self.model)
        entry = {"timesteps": self.model.num_timesteps, **result}
        self.validations.append(entry)
        if result["mean_quality"] > self.best:
            self.best = result["mean_quality"]
            self.model.save(str(self.folder / "best.tmp.zip"))
            os.replace(self.folder / "best.tmp.zip", self.folder / "best.zip")
            write_json(self.folder / "best.json", {**self.metadata, "actual_timesteps": self.model.num_timesteps, "validation": result})
        checkpoint_dir = self.folder / "checkpoints"
        checkpoint_dir.mkdir(exist_ok=True)
        self.model.save(str(checkpoint_dir / f"step_{self.model.num_timesteps}"))
        self.last_checkpoint = self.model.num_timesteps
        self.report()
        print(f"{self.metadata['run_id']} {self.model.num_timesteps}: quality={result['mean_quality']:.3f} crash={result['crash_rate']:.3f} speed={result['mean_speed_kmh']:.1f} passes={result['mean_overtakes']:.1f}", flush=True)

    def _on_step(self):
        for info in self.locals.get("infos", []):
            item = info.get("episode")
            if item:
                self.episodes += 1
                self.writer.writerow({"timesteps": self.num_timesteps, "episode": self.episodes,
                                     "return": item["r"], "length": item["l"],
                                     "overtakes": info.get("overtaken_count", ""),
                                     **{key: info.get(key, "") for key in ("completed", "distance_m", "danger_seconds")}})
        if self.num_timesteps - self.last_report >= 10000:
            self.report()
            elapsed = time.perf_counter() - self.started
            print(f"{self.metadata['run_id']}: {self.num_timesteps} steps; {elapsed:.0f}s this session", flush=True)
            self.last_report = self.num_timesteps
            if self.metadata["traffic"] == "curriculum":
                self.training_env.env_method("set_progress", min(1.0, self.num_timesteps / 200000))
        if self.num_timesteps - self.last_save >= 25000:
            self.save_latest()
        if self.num_timesteps - self.last_checkpoint >= self.interval:
            self.checkpoint()
        return True


def train(args):
    from rl_course.driving_env import ENV_VERSION, TRAFFIC, TARGET_SPEEDS, CurriculumTraffic, make_driving_env
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    folder = EXPERIMENTS / args.run
    if folder.exists() and not args.resume:
        raise ValueError(f"Run exists: {folder}; use --resume or a new --run ID")
    folder.mkdir(parents=True, exist_ok=True)
    resumed = args.resume and (folder / "latest.zip").exists()
    if args.resume and not resumed:
        raise ValueError("--resume requires latest.zip")

    def factory(index):
        def create():
            env = CurriculumTraffic(seed=args.seed + index * 101, duration=45, reward_mode=args.reward) if args.traffic == "curriculum" else make_driving_env(args.traffic, 45, args.reward)
            return Monitor(env)
        return create

    env = DummyVecEnv([factory(index) for index in range(args.envs)])
    env.seed(args.seed)
    if resumed:
        old = json.loads((folder / "config.json").read_text(encoding="utf-8"))
        for key, value in (("algorithm", args.algorithm), ("seed", args.seed), ("traffic", args.traffic), ("reward", args.reward), ("env_version", ENV_VERSION), ("envs", args.envs)):
            if old.get(key) != value:
                raise ValueError(f"Cannot resume with changed {key}")
        if old.get("environment_source_sha256") and old["environment_source_sha256"] != sha256(Path(__file__).with_name("driving_env.py")):
            raise ValueError("Environment source changed since this run; use a new run ID")
        model = CLASSES[args.algorithm].load(str(folder / "latest.zip"), env=env, device="cpu")
        if args.algorithm == "dqn":
            if not (folder / "replay.pkl").exists():
                raise ValueError("DQN resume requires replay.pkl; refusing an unreported partial resume")
            model.load_replay_buffer(str(folder / "replay.pkl"))
    else:
        common = {"env": env, "seed": args.seed, "device": "cpu", "verbose": 0,
                  "policy_kwargs": {"net_arch": [128, 128]}, "gamma": .99}
        if args.algorithm == "ppo":
            model = PPO("MlpPolicy", learning_rate=3e-4, n_steps=512, batch_size=256,
                        n_epochs=8, gae_lambda=.95, ent_coef=.008, clip_range=.2, **common)
        elif args.algorithm == "a2c":
            model = A2C("MlpPolicy", learning_rate=5e-4, n_steps=32, gae_lambda=.95,
                        ent_coef=.01, normalize_advantage=True, **common)
        else:
            common["gamma"] = .98
            model = DQN("MlpPolicy", learning_rate=3e-4, buffer_size=100000,
                        learning_starts=5000, batch_size=128, train_freq=4, gradient_steps=1,
                        target_update_interval=2000, exploration_fraction=.3,
                        exploration_final_eps=.04, **common)
    imitation = None
    if args.demonstrations and not resumed:
        if args.algorithm != "ppo":
            raise ValueError("Imitation warm-start currently supports PPO only")
        from rl_course.demonstrations_v2 import warm_start
        imitation = warm_start(model, Path(args.demonstrations), args.seed)
        write_json(folder / "imitation.json", imitation)
        model.save(str(folder / "actor_pretrained.zip"))
    elif (folder / "imitation.json").exists():
        imitation = json.loads((folder / "imitation.json").read_text(encoding="utf-8"))
    metadata = {"run_id": args.run, "algorithm": args.algorithm, "seed": args.seed,
                "traffic": args.traffic, "reward": args.reward, "env_version": ENV_VERSION,
                "requested_timesteps": args.steps, "envs": args.envs,
                "environment_source_sha256": sha256(Path(__file__).with_name("driving_env.py")),
                "metrics_source_sha256": sha256(Path(__file__).with_name("v2_metrics.py")),
                "resume_history": [*old.get("resume_history", []),
                    {"from_timesteps": model.num_timesteps, "previous_requested_timesteps": old["requested_timesteps"],
                     "new_requested_timesteps": args.steps, "previous_environment_source_sha256": old.get("environment_source_sha256")}]
                    if resumed else [],
                "imitation_transitions": imitation["transitions"] if imitation else 0,
                "imitation_dataset_sha256": imitation["dataset_sha256"] if imitation else None,
                "environment_configuration": {"traffic": TRAFFIC, "target_speeds": TARGET_SPEEDS,
                    "simulation_frequency": 15, "policy_frequency": 5, "duration": 45,
                    "rewards": {"progress_per_m": .025, "pass": .4 if args.reward == "shaped" else 0,
                                "collision": -12, "completion": 3, "danger_per_step": -.12 if args.reward == "shaped" else 0,
                                "lane_change": -.02 if args.reward == "shaped" else 0,
                                "quick_reverse_extra": -.12 if args.reward == "shaped" else 0}},
                "validation_seeds": list(VALIDATION_SEEDS),
                "selection_metric": "2*completion+distance/(30*duration)+.02*min(overtakes,15)-.2*danger/duration",
                "resume_semantics": "network and optimizer restored; DQN replay restored; episode and RNG streams restart",
                "hyperparameters": {k: getattr(model, k, None) for k in ("learning_rate", "gamma", "n_steps", "batch_size", "n_epochs", "ent_coef", "gae_lambda", "buffer_size", "learning_starts", "target_update_interval", "exploration_fraction")}}
    write_json(folder / "config.json", metadata)
    if args.traffic == "curriculum":
        env.env_method("set_progress", min(1.0, model.num_timesteps / 200000))
    logger = TrainingLog(folder, metadata, args.checkpoint_every, resumed, model.num_timesteps)
    logger.init_callback(model)
    try:
        if imitation and not resumed:
            # Preserve and measure the actor-only starting point for a genuine
            # warm-start ablation; subsequent RL must earn any claimed gain.
            logger.checkpoint()
        remaining = max(0, args.steps - model.num_timesteps)
        if remaining:
            model.learn(total_timesteps=remaining, callback=logger, reset_num_timesteps=not resumed)
        if logger.last_checkpoint != model.num_timesteps:
            logger.checkpoint()
        logger.report("complete")
    except BaseException:
        logger.save_latest()
        logger.report("interrupted")
        raise
    finally:
        logger.file.close()
        env.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--algorithm", choices=list(CLASSES), default="ppo")
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--steps", type=int, default=200000)
    parser.add_argument("--traffic", choices=["curriculum", "light", "normal", "dense"], default="curriculum")
    parser.add_argument("--reward", choices=["shaped", "base"], default="shaped")
    parser.add_argument("--envs", type=int, default=4)
    parser.add_argument("--checkpoint-every", type=int, default=50000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--demonstrations", help="Optional .npz rule demonstration dataset for actor warm-start; budget is logged separately")
    args = parser.parse_args()
    if min(args.steps, args.envs, args.checkpoint_every) <= 0:
        parser.error("steps, envs, checkpoint-every must be positive")
    if not args.run.replace("_", "").replace("-", "").isalnum():
        parser.error("run IDs may contain letters, numbers, underscore and hyphen")
    train(args)


if __name__ == "__main__":
    main()
