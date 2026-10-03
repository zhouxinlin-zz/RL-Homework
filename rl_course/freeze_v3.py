"""Freeze development-selected v3 models only after paired held-out evaluation.

Selection file format:
  {"env_version":"3.1", "models": {alias: {"source": relative_path,
   "development_report": relative_path, "run_id":..., "method":...,
   "seed":..., "steps":..., "training_steps":..., "source_env_version":...}},
   "levels": {beginner|standard|expert: {"model": alias, "description":...}}}
Run this after test_<alias>_routes.json, test_rule_routes.json and
test_cruise_routes.json have been written. It never chooses checkpoints.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil

import numpy as np

from rl_course.challenge_rules import ENV_VERSION, GAME_VERSION
from rl_course.compare_v3 import compare
from rl_course.evaluate_v3 import OUT, TEST_START
from rl_course.v2_metrics import sha256, write_json

ROOT = Path(__file__).resolve().parents[1]


def checked(path_text: str) -> Path:
    path = (ROOT / path_text).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError(f"Missing or external release input: {path_text}")
    return path


def load_test(policy: str, expected_hash: str | None = None) -> dict:
    path = checked(f"artifacts/experiments_v3/test_{policy}_routes.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if (value.get("env_version") != ENV_VERSION or value.get("duration") != "game_routes"
            or value.get("seed_start") != TEST_START or value.get("policy") != policy
            or value.get("episodes_per_scenario", 0) < 100):
        raise ValueError(f"Incomplete or incompatible final test: {policy}")
    if expected_hash is not None and value.get("model_sha256") != expected_hash:
        raise ValueError(f"Tested checkpoint differs from the selected checkpoint: {policy}")
    return value


def overall(report: dict) -> dict:
    rows = report["episodes"]
    return {"episodes": len(rows), "crashes": sum(row["crashed"] for row in rows),
            "crash_rate": float(np.mean([row["crashed"] for row in rows])),
            "qualification_rate": float(np.mean([row["qualified"] for row in rows])),
            "mean_distance_m": float(np.mean([row["distance_m"] for row in rows])),
            "mean_overtakes": float(np.mean([row["overtakes"] for row in rows])),
            "mean_score": float(np.mean([row["score"] for row in rows])),
            "mean_danger_seconds": float(np.mean([row["danger_seconds"] for row in rows]))}


def freeze(selection_path: Path):
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if selection.get("env_version") != ENV_VERSION:
        raise ValueError("Selection file uses another environment version")
    models = selection.get("models", {})
    levels = selection.get("levels", {})
    if not all(levels.get(level, {}).get("model") in models
               for level in ("beginner", "standard", "expert")):
        raise ValueError("Select all three levels before final testing")
    if not models or any(not name.startswith("v3_") for name in models):
        raise ValueError("Model aliases must use the v3_ namespace")
    tests = {}
    sources = {}
    for alias, spec in models.items():
        source = checked(spec["source"])
        development = json.loads(checked(spec["development_report"]).read_text(encoding="utf-8"))
        if (development.get("env_version") != ENV_VERSION
                or development.get("duration") != "game_routes"
                or development.get("model_sha256") != sha256(source)
                or development.get("seed_start", TEST_START) >= TEST_START):
            raise ValueError(f"Missing development evidence for {alias}")
        sources[alias] = source
        tests[alias] = load_test(alias, sha256(source))
    tests["rule"] = load_test("rule")
    tests["cruise"] = load_test("cruise")
    keys = lambda report: {(row["scenario"], row["seed"]) for row in report["episodes"]}
    reference = keys(tests["rule"])
    if any(keys(report) != reference for report in tests.values()):
        raise ValueError("Every final policy must cover exactly the same test roads")
    expert = levels["expert"]["model"]
    standard = levels["standard"]["model"]
    beginner = levels["beginner"]["model"]
    paired = {"expert_vs_rule": compare(tests[expert], tests["rule"]),
              "expert_vs_standard": compare(tests[expert], tests[standard]),
              "standard_vs_beginner": compare(tests[standard], tests[beginner])}
    report = {
        "schema_version": 1, "game_version": GAME_VERSION, "env_version": ENV_VERSION,
        "stage": "final", "split": "held_out_test", "seed_start": TEST_START,
        "same_roads_for_all_policies": True,
        "checkpoint_selection": "locked using development roads before held-out test runs",
        "selection_file": selection_path.relative_to(ROOT).as_posix(),
        "selection_sha256": sha256(selection_path),
        "environment_source_sha256": sha256(ROOT / "rl_course/driving_env_v3.py"),
        "rules_source_sha256": sha256(ROOT / "rl_course/challenge_rules.py"),
        "evaluation_source_sha256": sha256(ROOT / "rl_course/evaluate_v3.py"),
        "levels": {level: spec["model"] for level, spec in levels.items()},
        "models": {name: {"metadata": models.get(name), "summary": overall(value),
                          "by_scenario": value["summary"],
                          "test_report": f"artifacts/experiments_v3/test_{name}_routes.json",
                          "test_report_sha256": sha256(OUT / f"test_{name}_routes.json")}
                   for name, value in tests.items()},
        "paired_game_outcomes": paired,
        "limitations": [
            "These intervals reflect road-seed variation for the selected checkpoints, not variation across training seeds.",
            "Human performance was not collected; the project does not claim to surpass all human drivers.",
            "Twin runs share the same initial traffic seed; traffic then responds separately to each driver's actions.",
            "The three challenges use a straight three-lane road and scripted traffic formations, not a full road network.",
        ],
    }
    output = OUT / "evaluation_final"
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "report.json"
    write_json(report_path, report)
    deployment_dir = OUT / "deployment"
    deployment_dir.mkdir(exist_ok=True)
    deployed = {}
    for alias, source in sources.items():
        digest = sha256(source)
        destination = deployment_dir / f"{alias}-{digest[:12]}.zip"
        if not destination.exists() or sha256(destination) != digest:
            temporary = destination.with_suffix(".tmp.zip")
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
        spec = models[alias]
        deployed[alias] = {"path": destination.relative_to(ROOT).as_posix(),
                           "sha256": digest, "algorithm": "ppo", "env_version": ENV_VERSION,
                           "source_env_version": spec.get("source_env_version", ENV_VERSION),
                           "run_id": spec["run_id"], "method": spec["method"],
                           "seed": spec["seed"], "steps": spec["steps"],
                           "training_steps": spec["training_steps"],
                           "development_report": spec["development_report"],
                           "test_report": f"artifacts/experiments_v3/test_{alias}_routes.json"}
    manifest = {"schema_version": 1, "stage": "final", "game_version": GAME_VERSION,
                "env_version": ENV_VERSION, "models": deployed, "levels": levels,
                "evaluation": {"status": "complete",
                               "report": report_path.relative_to(ROOT).as_posix(),
                               "report_sha256": sha256(report_path)}}
    write_json(OUT / "deployment.json", manifest)
    print(f"Frozen {len(deployed)} evaluated challenge models in {OUT / 'deployment.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=OUT / "selection_lock.json")
    args = parser.parse_args()
    freeze(args.selection.resolve())


if __name__ == "__main__":
    main()
