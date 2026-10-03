"""Freeze immutable policy copies for game inference, separate from training files."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil

from rl_course.v2_metrics import ROOT, EXPERIMENTS, write_json, sha256


def best_rl_checkpoint(run_id: str) -> str:
    """Select only checkpoints that actually received reinforcement updates.

    The training run's best.zip intentionally includes the imitation starting
    point. Keep that history intact and expose post-RL selection separately.
    """
    progress = json.loads((EXPERIMENTS / run_id / "progress.json").read_text(encoding="utf-8"))
    candidates = [value for value in progress["validations"] if value["timesteps"] > 0]
    if not candidates:
        raise ValueError(f"No validated RL checkpoint for {run_id}")
    best = max(candidates, key=lambda value: value["mean_quality"])
    return f"checkpoints/step_{best['timesteps']}.zip"


def freeze_model(run_id: str, alias: str, checkpoint="best.zip") -> dict:
    folder = EXPERIMENTS / run_id
    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    progress = json.loads((folder / "progress.json").read_text(encoding="utf-8"))
    source = folder / checkpoint
    if checkpoint == "best.zip":
        best = json.loads((folder / "best.json").read_text(encoding="utf-8"))
        steps, validation = best["actual_timesteps"], best["validation"]
        immutable_checkpoint = folder / "checkpoints" / f"step_{steps}.zip"
        if immutable_checkpoint.exists():
            source = immutable_checkpoint
    else:
        steps = 0 if checkpoint == "actor_pretrained.zip" else int(Path(checkpoint).stem.removeprefix("step_"))
        validation = next(v for v in progress["validations"] if v["timesteps"] == steps)
    content_hash = sha256(source)
    destination = EXPERIMENTS / "deployment" / f"{alias}-{content_hash[:12]}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.zip")
    shutil.copyfile(source, temporary)
    os.replace(temporary, destination)
    demonstrations = config.get("imitation_transitions", 0)
    historical_best = json.loads((folder / "best.json").read_text(encoding="utf-8"))
    method = "imitation-only" if demonstrations and steps == 0 else "demonstration-warmstart-ppo" if demonstrations else "pure-rl"
    history = config.get("resume_history", [])
    training_hash = config.get("environment_source_sha256")
    for resume in history:
        if steps <= resume["from_timesteps"]:
            training_hash = resume.get("previous_environment_source_sha256")
            break
    item = {"path": destination.relative_to(ROOT).as_posix(), "algorithm": config["algorithm"],
            "steps": steps, "training_steps": 0 if method == "imitation-only" else progress["actual_timesteps"],
            "source_run_training_steps": progress["actual_timesteps"],
            "seed": config["seed"], "run_id": run_id, "env_version": config["env_version"],
            "method": method, "demonstration_steps": demonstrations,
            "best_including_initialization_steps": historical_best["actual_timesteps"],
            "selection_scope": "initialization_only" if steps == 0 else "explicit_checkpoint" if checkpoint != "best.zip" else "best_including_initialization",
            "sha256": sha256(destination), "source_checkpoint": source.relative_to(ROOT).as_posix(),
            "environment_source_sha256": training_hash,
            "training_source_hash_status": "recorded_at_checkpoint_stage" if training_hash else "historical_hash_not_recorded",
            "training_source_history_complete": bool(training_hash) and all(row.get("previous_environment_source_sha256") for row in history),
            "training_resume_history": history,
            "validation": {key: value for key, value in validation.items() if key != "episodes_detail"}}
    write_json(destination.with_suffix(".json"), {**item, "config": config, "validation_detail": validation})
    return item


def development_deployment():
    models = {"ppo": freeze_model("ppo_normal_s11", "ppo"),
              "dqn": freeze_model("dqn_curriculum_s11", "dqn"),
              "a2c": freeze_model("a2c_curriculum_s11", "a2c"),
              "ppo_mixed": freeze_model("ppo_warm60_s47", "ppo_mixed")}
    manifest = {"schema_version": 1, "env_version": "2.0", "stage": "development",
                "models": models,
                "levels": {"standard": {"model": "ppo_mixed", "inference_stride": 1,
                    "label": "标准", "description": "开发中的驾驶网络，正在进行强化学习训练与难度校准。",
                    "validation": models["ppo_mixed"]["validation"]}},
                "evaluation": {"status": "development_only", "seed_start": 31100,
                    "note": "Temporary integration snapshot. No final test or calibrated difficulty claim."}}
    write_json(EXPERIMENTS / "deployment.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    if not args.development:
        parser.error("Use --development for integration snapshots; final deployment is selected from calibration results")
    result = development_deployment()
    print(f"Frozen {len(result['models'])} verified development policies", flush=True)


if __name__ == "__main__":
    main()
