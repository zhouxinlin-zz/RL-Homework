"""Repair descriptive provenance without changing policies or episode results."""
from __future__ import annotations

import json
from rl_course.v2_metrics import EXPERIMENTS, ROOT, sha256, write_json


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_spec(item):
    item = dict(item)
    if item.get("run_id") != "ppo_curriculum_s11":
        return item
    config = read(EXPERIMENTS / item["run_id"] / "config.json")
    history = config.get("resume_history", [])
    steps = item.get("steps", item.get("checkpoint_steps", 0))
    training_hash = config.get("environment_source_sha256")
    for resume in history:
        if steps <= resume["from_timesteps"]:
            training_hash = resume.get("previous_environment_source_sha256")
            break
    item["environment_source_sha256"] = training_hash
    item["training_source_hash_status"] = "recorded_at_checkpoint_stage" if training_hash else "historical_hash_not_recorded"
    item["training_source_history_complete"] = bool(training_hash) and all(row.get("previous_environment_source_sha256") for row in history)
    item["training_resume_history"] = history
    source = EXPERIMENTS / item["run_id"] / "checkpoints" / f"step_{steps}.zip"
    if source.exists() and sha256(source) == item["sha256"]:
        immutable_path = source.relative_to(ROOT).as_posix()
        if item.get("source_checkpoint") != immutable_path:
            item["source_path_at_freeze"] = item.get("source_checkpoint")
            item["source_checkpoint"] = immutable_path
    return item


def synchronize_shard(shard, specification):
    """Runtime environment hash stays intact; only training history is amended."""
    metadata = shard["metadata"]
    if metadata.get("run_id") != "ppo_curriculum_s11":
        return shard
    keys = ("source_checkpoint", "source_path_at_freeze", "training_source_hash_status",
            "training_source_history_complete", "training_resume_history")
    updates = {key: specification[key] for key in keys if key in specification}
    updates["training_environment_source_sha256"] = specification.get("environment_source_sha256")
    changes = {key: {"previous": metadata.get(key), "corrected": value}
               for key, value in updates.items() if key not in metadata or metadata[key] != value}
    if changes:
        metadata.setdefault("provenance_amendments", []).append({
            "reason": "Historical pilot hash was not logged; later resume metadata must not be attributed to an earlier checkpoint. Mutable best.zip source paths are resolved to matching immutable checkpoints.",
            "changes": changes, "episode_results_changed": False})
        metadata.update(updates)
    return shard


def main():
    registries = ["comparison_200k.json", "fixed_comparisons.json", "calibration_candidates.json",
                  "calibration_fixed_candidates.json", "final_main_candidates.json"]
    all_specs = {}
    for name in registries:
        path = EXPERIMENTS / name
        if not path.exists():
            continue
        registry = {key: normalize_spec(value) for key, value in read(path).items()}
        write_json(path, registry)
        all_specs.update(registry)
    for name in ("deployment.json", "selection_lock.json"):
        path = EXPERIMENTS / name
        data = read(path)
        data["models"] = {key: normalize_spec(value) for key, value in data["models"].items()}
        data["provenance_note"] = "Training-source history annotations were corrected after level selection; model weights, hashes, steps and level choices did not change."
        write_json(path, data)
    for spec in all_specs.values():
        sidecar = (ROOT / spec["path"]).with_suffix(".json")
        if sidecar.exists() and spec.get("run_id") == "ppo_curriculum_s11":
            data = read(sidecar)
            data.update(spec)
            write_json(sidecar, data)
    for directory in ("calibration", "evaluation_fixed_test", "evaluation_main_test"):
        for name, spec in all_specs.items():
            path = EXPERIMENTS / directory / f"{name}.json"
            if path.exists():
                write_json(path, synchronize_shard(read(path), spec))
            failure = path.parent / "failures" / path.name
            if failure.exists():
                write_json(failure, synchronize_shard(read(failure), spec))
    print("Provenance annotations synchronized; model and episode data unchanged")


if __name__ == "__main__":
    main()
