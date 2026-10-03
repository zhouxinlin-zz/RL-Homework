"""Select on development roads, test once on fresh roads, then publish a checked release."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path

import torch

from rl_course.compare_v3 import compare
from rl_course.train_challenge_models import CLASSES, OUT, ROOT, HOLDOUT_START, evaluate
from rl_course.v2_metrics import sha256, write_json


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rank(stats):
    return (-stats["crashes"], stats["qualification_rate"], stats["mean_score"])


def run_evaluation(task):
    alias, spec, count, seed, output = task
    torch.set_num_threads(1)
    path = ROOT / spec["path"] if spec else None
    model = CLASSES[spec["algorithm"]].load(path, device="cpu") if spec else None
    report = evaluate(model, count=count, seed_start=seed, policy=alias)
    report["model_sha256"] = sha256(path) if path else None
    write_json(Path(output), report)
    print(f"{alias}: {report['overall']}", flush=True)
    return report


def select():
    if (OUT / "selection.json").exists():
        raise ValueError("Selection is already locked. Keep this experiment immutable.")
    selected, choices, tasks = {}, {}, []
    for algorithm in CLASSES:
        candidates = []
        for folder in sorted(OUT.glob(f"{algorithm}_s*")):
            config = read(folder / "config.json")
            progress = read(folder / "progress.json")
            if progress["actual_steps"] < config["requested_steps"]:
                raise ValueError(f"Training is still running: {folder}")
            for row in progress["validations"]:
                if row["steps"] <= 0:
                    continue
                candidates.append((rank(row), folder, config, row["steps"]))
        finalists = sorted(candidates, key=lambda value: value[0], reverse=True)[:3 if algorithm == "ppo" else 2]
        if not finalists:
            raise ValueError(f"No trained {algorithm} checkpoint")
        choices[algorithm] = []
        for _, folder, config, steps in finalists:
            path = folder / f"step_{steps}.zip"
            spec = {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path),
                "algorithm": algorithm, "steps": steps, "seed": config["seed"],
                "env_version": "3.1", "run_id": folder.name,
                "training_steps": read(folder / "progress.json")["actual_steps"],
                "method": "PPO 安全与效率微调" if algorithm == "ppo" else "PPO 权重初始化后 A2C 更新" if config.get("actor_from_ppo") else f"{algorithm.upper()} 检查点继续训练" if config.get("source") else f"{algorithm.upper()} 从零训练",
                "method_label": "迁移初始化 → 效率与安全 PPO" if algorithm == "ppo" else "PPO 初始化 → A2C 微调" if config.get("actor_from_ppo") else None,
                "config": (folder / "config.json").relative_to(ROOT).as_posix(),
                "config_sha256": sha256(folder / "config.json"),
                "pretrained": bool(config.get("source") or config.get("actor_from_ppo"))}
            output = folder / f"selection_{steps}.json"
            report = read(output) if output.exists() else None
            if not report or report.get("model_sha256") != spec["sha256"] or report.get("seed_start") != 631200 or report.get("episodes_per_scenario") != 32:
                tasks.append((algorithm, spec, 32, 631200, output))
            choices[algorithm].append((spec, output))
    if tasks:
        with ProcessPoolExecutor(max_workers=min(4, len(tasks))) as pool:
            list(pool.map(run_evaluation, tasks))
    for algorithm, items in choices.items():
        spec, output = max(items, key=lambda item: rank(read(item[1])["overall"]))
        selected[f"v3_{algorithm}_candidate"] = {**spec, "selection_report": output.relative_to(ROOT).as_posix(), "selection_summary": read(output)["overall"]}
    write_json(OUT / "selection.json", {"env_version": "3.1", "models": selected,
        "expert_candidate": max(selected, key=lambda name: rank(selected[name]["selection_summary"])),
        "development_start": 631200, "test_start": HOLDOUT_START, "test_count_per_route": 100,
        "promotion_gate": "no more crashes and higher qualification and score than previous expert on fresh held-out roads"})


def tests():
    lock = read(OUT / "selection.json")
    base = read(ROOT / "artifacts/experiments_v3/deployment.json")
    models = {**base["models"], **lock["models"], "rule": None}
    tasks = []
    for alias, spec in models.items():
        if spec and sha256(ROOT / spec["path"]) != spec["sha256"]:
            raise ValueError(f"Checkpoint changed after selection: {alias}")
        path = OUT / f"test_{alias}.json"
        if path.exists():
            report = read(path)
            if report.get("model_sha256") != (spec["sha256"] if spec else None) or report.get("seed_start") != HOLDOUT_START:
                raise ValueError("Existing test file is not from this locked experiment")
            continue
        tasks.append((alias, spec, lock["test_count_per_route"], HOLDOUT_START, path))
    if tasks:
        with ProcessPoolExecutor(max_workers=min(6, len(tasks))) as pool:
            list(pool.map(run_evaluation, tasks))


def publish():
    base = read(ROOT / "artifacts/experiments_v3/deployment.json")
    lock = read(OUT / "selection.json")
    reports = {alias: read(OUT / f"test_{alias}.json") for alias in [*base["models"], *lock["models"], "rule"]}
    expected = {(scenario, seed) for scenario in ("convoy", "weave", "pressure") for seed in range(HOLDOUT_START, HOLDOUT_START + 100)}
    for alias, report in reports.items():
        spec = {**base["models"], **lock["models"]}.get(alias)
        if (len(report["episodes"]) != 300 or {(r["scenario"], r["seed"]) for r in report["episodes"]} != expected
                or report.get("model_sha256") != (spec["sha256"] if spec else None)):
            raise ValueError(f"Incomplete or incompatible final evaluation: {alias}")
    old = reports["v3_expert"]["overall"]
    candidate = lock["expert_candidate"]
    new = reports[candidate]["overall"]
    promoted = new["crashes"] <= old["crashes"] and new["qualification_rate"] > old["qualification_rate"] and new["mean_score"] > old["mean_score"]
    models = {**base["models"], "v3_ppo": lock["models"]["v3_ppo_candidate"], "v3_dqn": lock["models"]["v3_dqn_candidate"], "v3_a2c": lock["models"]["v3_a2c_candidate"]}
    current = {alias: reports[alias] for alias in base["models"]}
    current.update({"v3_ppo": reports["v3_ppo_candidate"], "v3_dqn": reports["v3_dqn_candidate"], "v3_a2c": reports["v3_a2c_candidate"], "rule": reports["rule"]})
    if promoted:
        models["v3_expert"] = lock["models"][candidate]
        current["v3_expert"] = reports[candidate]
    comparison = []
    for alias in ("v3_ppo", "v3_dqn", "v3_a2c"):
        spec = models[alias]
        comparison.append({"id": alias, "algorithm": spec["algorithm"].upper(), "method": spec.get("method"),
            "checkpoint_steps": spec["steps"], "training_steps": spec.get("training_steps", spec["steps"]),
            "pretrained": spec.get("pretrained", True), "overall": current[alias]["overall"],
            "routes": current[alias]["summary"],
            "history": read(OUT / spec["run_id"] / "progress.json")["validations"] if (OUT / spec["run_id"] / "progress.json").exists() else []})
    final = {"stage": "final", "env_version": "3.1", "seed_start": HOLDOUT_START,
        "environment_source_sha256": sha256(ROOT / "rl_course/driving_env_v3.py"),
        "rules_source_sha256": sha256(ROOT / "rl_course/challenge_rules.py"),
        "evaluation_source_sha256": sha256(ROOT / "rl_course/train_challenge_models.py"),
        "release_source_sha256": sha256(Path(__file__)),
        "selection_sha256": sha256(OUT / "selection.json"),
        "models": {name: {"summary": report["overall"], "by_scenario": report["summary"]} for name, report in current.items()},
        "paired_game_outcomes": {"standard_vs_beginner": compare(current["v3_standard"], current["v3_beginner"]),
            "expert_vs_rule": compare(current["v3_expert"], current["rule"]),
            "new_vs_previous_expert": compare(reports[candidate], reports["v3_expert"])},
        "algorithm_comparison": comparison,
        "improvement": {"promoted": promoted, "algorithm": lock["models"][candidate]["algorithm"].upper(), "before": old, "candidate": new},
        "limitations": ["No human benchmark was collected.", "Algorithms have different initialization and training budgets; this is a project comparison, not a claim of universal algorithm superiority."]}
    write_json(OUT / "report.json", final)
    write_json(OUT / "release.json", {"stage": "final", "env_version": "3.1", "models": models,
        "evaluation": {"status": "complete", "report": (OUT / "report.json").relative_to(ROOT).as_posix(),
            "report_sha256": sha256(OUT / "report.json")}})
    print(f"Published iteration. {candidate} expert promoted: {promoted}. Old: {old}; Candidate: {new}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("select", "test", "publish"))
    args = parser.parse_args()
    {"select": select, "test": tests, "publish": publish}[args.stage]()
