"""Freeze one refinement candidate, evaluate fresh roads once, and publish evidence."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import gzip
import json
from pathlib import Path

import torch
from stable_baselines3 import PPO

from rl_course.challenge_rules import CHALLENGE_TRACKS
from rl_course.compare_v3 import compare
from rl_course.driving_env_v3 import make_challenge_env
from rl_course.train_challenge_models import evaluate
from rl_course.train_refinement import OUT, SOURCE, DEV_START, SELECTION_START, TEST_START
from rl_course.v2_metrics import ROOT, sha256, write_json, interval

TRAINING_SCRIPT = "rl_course/train_refinement.py"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rank(stats):
    return (-stats["crashes"], stats["qualification_rate"], stats["mean_score"])


def run_evaluation(task):
    alias, spec, count, seed, output = task
    if Path(output).exists():
        cached = read(Path(output))
        validate_report(cached, spec, seed, count)
        return cached
    torch.set_num_threads(1)
    model = PPO.load(ROOT / spec["path"], device="cpu") if spec else None
    report = evaluate(model, count=count, seed_start=seed, policy=alias)
    report["model_sha256"] = spec["sha256"] if spec else None
    write_json(Path(output), report)
    print(f"{alias}: {report['overall']}", flush=True)
    return report


def spec_for(folder, steps):
    config, progress = read(folder / "config.json"), read(folder / "progress.json")
    checkpoint = folder / f"step_{steps}.zip"
    return {"path": checkpoint.relative_to(ROOT).as_posix(), "sha256": sha256(checkpoint),
        "algorithm": "ppo", "env_version": "3.1", "steps": steps, "seed": config["seed"],
        "run_id": folder.name, "training_steps": progress["actual_steps"],
        "method": config.get("method", "PPO 小步微调：实际赛程与高压场景采样"), "pretrained": True,
        "method_label": "PPO → 效率微调 → 跟车风险约束" if "anchor_strength" in config else "已有 PPO → 实际赛程微调",
        "config": (folder / "config.json").relative_to(ROOT).as_posix(),
        "config_sha256": sha256(folder / "config.json")}


def select():
    if (OUT / "selection.json").exists():
        raise ValueError("Selection is frozen; start a new experiment to select again.")
    finalists = []
    for folder in sorted(OUT.glob("ppo_s*")):
        config, progress = read(folder / "config.json"), read(folder / "progress.json")
        if progress["actual_steps"] < config["requested_steps"]:
            raise ValueError(f"Training is incomplete: {folder}")
        points = [r for r in progress["validations"] if r["steps"] > 0]
        for point in sorted(points, key=rank, reverse=True)[:2]:
            finalists.append((spec_for(folder, point["steps"]), folder / f"selection_{point['steps']}.json"))
    if not finalists:
        raise ValueError("No candidates found")
    baseline = read(ROOT / "artifacts/experiments_v3/deployment.json")["models"]["v3_expert"]
    assert baseline["sha256"] == sha256(SOURCE)
    tasks = [(f"{s['run_id']}_{s['steps']}", s, 32, SELECTION_START, p) for s, p in finalists]
    tasks.append(("previous", baseline, 32, SELECTION_START, OUT / "selection_previous.json"))
    with ProcessPoolExecutor(max_workers=4) as pool:
        list(pool.map(run_evaluation, tasks))
    chosen, path = max(finalists, key=lambda item: rank(read(item[1])["overall"]))
    write_json(OUT / "selection.json", {"env_version": "3.1", "candidate": chosen, "previous": baseline,
        "selection_report": path.relative_to(ROOT).as_posix(), "selection_summary": read(path)["overall"],
        "finalists": [{"model": s, "report": p.relative_to(ROOT).as_posix(), "summary": read(p)["overall"]} for s, p in finalists],
        "development_start": DEV_START, "selection_start": SELECTION_START, "test_start": TEST_START,
        "test_count_per_route": 100, "replay_seed": SELECTION_START + 3,
        "promotion_gate": "no more crashes overall or per route; higher overall qualification and score; no route qualification regression"})


def validate_report(report, spec, start=None, count=100):
    start = TEST_START if start is None else start
    expected = {(t["scenario"], seed) for t in CHALLENGE_TRACKS for seed in range(start, start + count)}
    rows = report["episodes"]
    if (len(rows) != len(expected) or {(r["scenario"], r["seed"]) for r in rows} != expected
            or report.get("model_sha256") != (spec["sha256"] if spec else None)
            or report.get("env_version") != "3.1" or report.get("duration") != "game_routes"):
        raise ValueError("Incomplete, mismatched or duplicate test evidence")
    for track in CHALLENGE_TRACKS:
        if any(r["duration"] != track["duration"] for r in rows if r["scenario"] == track["scenario"]):
            raise ValueError("Evaluation duration differs from game")


def test():
    lock = read(OUT / "selection.json")
    tasks = []
    for alias, spec in [("previous", lock["previous"]), ("candidate", lock["candidate"]), ("rule", None)]:
        if spec and sha256(ROOT / spec["path"]) != spec["sha256"]:
            raise ValueError("Checkpoint changed after freezing")
        destination = OUT / f"test_{alias}.json"
        if destination.exists():
            validate_report(read(destination), spec)
        else:
            tasks.append((alias, spec, 100, TEST_START, destination))
    with ProcessPoolExecutor(max_workers=3) as pool:
        list(pool.map(run_evaluation, tasks))


def promotion_gate(before, after):
    a, b = before["overall"], after["overall"]
    return (b["crashes"] <= a["crashes"] and b["qualification_rate"] > a["qualification_rate"]
        and b["mean_score"] > a["mean_score"]
        and all(after["summary"][key]["crashes"] <= before["summary"][key]["crashes"]
                and after["summary"][key]["qualification_rate"] >= before["summary"][key]["qualification_rate"]
                for key in before["summary"]))


def demos(lock):
    # These three development roads are fixed before holdout testing, not picked
    # by looking for the biggest improvement. Replays never enter user records.
    from server.game import Runner, GameSession, GameManager
    torch.set_num_threads(1)
    models = {name: PPO.load(ROOT / lock[name]["path"], device="cpu") for name in ("previous", "candidate")}
    results = []
    for track in CHALLENGE_TRACKS:
        runners = []
        for name in ("previous", "candidate"):
            env = make_challenge_env(track["scenario"], track["duration"])
            obs, _ = env.reset(seed=lock["replay_seed"])
            ego = env.vehicle
            runners.append(Runner(env, obs, model=models[name], model_steps=lock[name]["steps"],
                model_info=lock[name], start_x=float(ego.position[0]), previous_lane=ego.lane_index[2]))
        try:
            session = GameSession(f"refinement-{track['id']}", "duel", track, lock["replay_seed"], "v3_expert", *runners)
            frames = [session.snapshot()]
            while not frames[-1]["done"]:
                before = frames[-1]
                for runner in runners:
                    runner.advance()
                current = session.snapshot()
                GameManager._events(session, before, current)
                current["events"] = list(session.events)
                frames.append(current)
            path = OUT / f"replay_{track['id']}.json.gz"
            content = json.dumps({"summary": frames[-1], "frames": frames,
                "comparison": {"left": "微调前 PPO", "right": "微调后 PPO", "seed": lock["replay_seed"],
                    "note": "固定开发道路回放；展示行为，不代表全部测试结果。"}}, ensure_ascii=False).encode("utf-8")
            path.write_bytes(gzip.compress(content, mtime=0))
            results.append({"id": track["id"], "name": track["name"], "seed": lock["replay_seed"],
                "duration": track["duration"], "path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)})
        finally:
            for runner in runners:
                runner.env.close()
    return results


def publish():
    if (OUT / "release.json").exists():
        raise ValueError("Release is immutable")
    lock = read(OUT / "selection.json")
    reports = {name: read(OUT / f"test_{name}.json") for name in ("previous", "candidate", "rule")}
    for name, report in reports.items():
        spec = lock.get(name)
        if spec and sha256(ROOT / spec["path"]) != spec["sha256"]:
            raise ValueError("Checkpoint changed after freezing")
        validate_report(report, spec)
    promoted = promotion_gate(reports["previous"], reports["candidate"])
    official = "candidate" if promoted else "previous"
    training_config = read(ROOT / lock["candidate"]["config"])
    has_reference = "anchor_strength" in training_config
    summaries = {}
    for name, report in reports.items():
        n = report["overall"]["episodes"]
        summaries[name] = {"overall": report["overall"], "routes": report["summary"],
            "qualification_ci95": interval(sum(r["qualified"] for r in report["episodes"]), n),
            "pressure_short": sum(r["completed"] and not r["qualified"] for r in report["episodes"] if r["scenario"] == "pressure")}
    histories = [{"run_id": folder.name, "seed": read(folder / "config.json")["seed"],
        "learning_rate": read(folder / "config.json")["learning_rate"],
        "anchor_strength": read(folder / "config.json").get("anchor_strength"),
        "actual_steps": read(folder / "progress.json")["actual_steps"],
        "points": read(folder / "progress.json")["validations"]} for folder in sorted(OUT.glob("ppo_s*"))]
    report = {"stage": "final", "env_version": "3.1", "seed_start": TEST_START, "episodes_per_route": 100,
        "selection_sha256": sha256(OUT / "selection.json"), "models": summaries,
        "promoted": promoted, "official": official, "histories": histories,
        "candidate_spec": lock["candidate"], "previous_spec": lock["previous"],
        "paired": compare(reports["candidate"], reports["previous"])["paired"],
        "expert_vs_rule": compare(reports[official], reports["rule"])["paired"]["all"],
        "total_training_steps": sum(h["actual_steps"] for h in histories),
        "upstream_refinement_steps": read(ROOT / "artifacts/experiments_v3/iteration_5/report.json")["total_training_steps"] if has_reference else 0,
        "promotion_gate": lock["promotion_gate"], "replays": demos(lock),
        "training_method": training_config,
        "sources": {p: sha256(ROOT / p) for p in (TRAINING_SCRIPT, "rl_course/release_refinement.py", "rl_course/train_refinement.py", "rl_course/driving_env.py",
            "rl_course/driving_env_v3.py", "rl_course/game_rules.py", "rl_course/challenge_rules.py")},
        "limitations": ["Single frozen candidate tested once on new roads; development configurations differ in seeds and reference-loss coefficients." if has_reference else "Single frozen candidate tested once on new roads; development training runs use different seeds, learning rates and budgets.",
            "No human benchmark; finite simulation evidence does not establish human-level or universal safety."]}
    write_json(OUT / "report.json", report)
    write_json(OUT / "release.json", {"stage": "final", "env_version": "3.1", "promoted": promoted,
        "model": lock[official], "report": (OUT / "report.json").relative_to(ROOT).as_posix(),
        "report_sha256": sha256(OUT / "report.json")})
    print(f"Refinement published. Promoted: {promoted}. {summaries}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("select", "test", "publish"))
    parser.add_argument("--iteration", type=int, choices=(5, 6), default=5)
    args = parser.parse_args()
    if args.iteration == 6:
        from rl_course import train_safety_refinement as experiment
        OUT = experiment.OUT
        DEV_START, SELECTION_START, TEST_START = experiment.DEV_START, experiment.SELECTION_START, experiment.TEST_START
        TRAINING_SCRIPT = "rl_course/train_safety_refinement.py"
    {"select": select, "test": test, "publish": publish}[args.stage]()
