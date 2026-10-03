"""Reproducible held-out evaluations for version 2 policies and transparent baselines.

Examples:
  python -m rl_course.evaluate_v2 --runs ppo_curriculum_s11 --episodes 100
  python -m rl_course.evaluate_v2 --deployment --episodes 100 --output evaluation_final

All rows, checkpoints, random seeds, inference delays and failures are retained.
The final evaluation is not used for selecting checkpoints or difficulty levels.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import json
from pathlib import Path

import numpy as np
import torch

from rl_course.train_v2 import CLASSES
from rl_course.v2_metrics import (
    ROOT, EXPERIMENTS, CONDITIONS, TEST_SEED_START, episode, aggregate, sha256, write_json,
)


def evaluate(item, episodes, seed_start, output, split="test"):
    from rl_course.driving_env import ENV_VERSION, make_driving_env
    torch.set_num_threads(1)
    model = None
    metadata = {**item, "env_version": ENV_VERSION, "seed_start": seed_start, "split": split,
                "training_environment_source_sha256": item.get("environment_source_sha256"),
                "environment_source_sha256": sha256(Path(__file__).with_name("driving_env.py")),
                "metrics_source_sha256": sha256(Path(__file__).with_name("v2_metrics.py")),
                "game_rules_source_sha256": sha256(Path(__file__).with_name("game_rules.py")),
                "episodes_per_condition": episodes}
    if item.get("path"):
        path = ROOT / item["path"]
        model = CLASSES[item["algorithm"]].load(str(path), device="cpu")
        metadata["sha256"] = sha256(path)
    rows, failures = [], []
    for scenario, duration in CONDITIONS:
        env = make_driving_env(scenario, duration)
        saved = 0
        try:
            for i in range(episodes):
                row = episode(env, model=model, baseline=item.get("baseline"), seed=seed_start+i,
                              inference_stride=item.get("inference_stride", 1), collect_trace=True)
                trace = row.pop("trace")
                row.update({"policy": item["id"], "scenario": scenario,
                            "inference_stride": item.get("inference_stride", 1)})
                rows.append(row)
                if row["crashed"] and saved < 3:
                    failures.append({**row, "trace": trace})
                    saved += 1
            print(f"{item['id']} {scenario}/{duration}: {aggregate(rows[-episodes:])['crash_rate']:.2%} collision", flush=True)
        finally:
            env.close()
    result = {"metadata": metadata, "episodes": rows}
    write_json(output / f"{item['id']}.json", result)
    write_json(output / "failures" / f"{item['id']}.json", {"metadata": metadata, "failures": failures})
    return result


def paired_comparison(candidate_shard, reference_shard):
    keyed = {(row["scenario"], row["duration"], row["seed"]): row for row in candidate_shard["episodes"]}
    by_seed = {}
    rank = lambda row: (row["completed"], row.get("qualified", False), row.get("score", 0))
    for row in reference_shard["episodes"]:
        candidate = keyed[(row["scenario"], row["duration"], row["seed"])]
        win = 1. if rank(candidate) > rank(row) else .5 if rank(candidate) == rank(row) else 0.
        by_seed.setdefault(row["seed"], []).append([
            candidate["quality"] - row["quality"], float(candidate["crashed"]) - float(row["crashed"]), win])
    # Repeated settings for the same seed stay together, including shared road
    # prefixes for normal-45/60 and dense-45/60.
    clusters = np.array([np.mean(by_seed[seed], axis=0) for seed in sorted(by_seed)])
    samples = np.random.default_rng(1941).integers(0, len(clusters), size=(2000, len(clusters)))
    bootstrap = clusters[samples].mean(axis=1)
    means = clusters.mean(axis=0)
    game_values = [item[2] for values in by_seed.values() for item in values]
    wins = sum(value == 1 for value in game_values)
    draws = sum(value == .5 for value in game_values)
    return {"policy": candidate_shard["metadata"]["id"], "reference": reference_shard["metadata"]["id"],
            "seed_clusters": len(clusters), "pairs": len(reference_shard["episodes"]),
            "bootstrap_unit": "road seed, retaining all five conditions",
            "mean_quality_difference": float(means[0]),
            "paired_bootstrap_ci95": np.quantile(bootstrap[:, 0], [.025, .975]).tolist(),
            "crash_rate_difference": float(means[1]),
            "crash_rate_difference_ci95": np.quantile(bootstrap[:, 1], [.025, .975]).tolist(),
            "game_win_score": float(means[2]), "draw_value": .5,
            "game_wins": wins, "game_draws": draws, "game_losses": len(game_values)-wins-draws,
            "game_win_rate": wins/len(game_values),
            "game_win_score_ci95": np.quantile(bootstrap[:, 2], [.025, .975]).tolist()}


def compile_report(output: Path, ids: list[str], split: str):
    shards = [json.loads((output / f"{name}.json").read_text(encoding="utf-8")) for name in ids]
    versions = set()
    hashes = set()
    metric_hashes = set()
    seeds = set()
    counts = set()
    for shard in shards:
        metadata = shard["metadata"]
        if metadata.get("split") != split:
            raise ValueError("Evaluation split mismatch; rerun evaluation with explicit split metadata")
        if split == "test" and metadata["seed_start"] < TEST_SEED_START:
            raise ValueError("Development seeds cannot be compiled into a test report")
        versions.add(metadata["env_version"])
        hashes.add(metadata["environment_source_sha256"])
        metric_hashes.add(metadata["metrics_source_sha256"])
        seeds.add(metadata["seed_start"])
        counts.add(metadata["episodes_per_condition"])
        expected = {(scenario, duration, metadata["seed_start"]+index) for scenario, duration in CONDITIONS for index in range(metadata["episodes_per_condition"])}
        observed = {(r["scenario"], r["duration"], r["seed"]) for r in shard["episodes"]}
        if expected != observed or len(shard["episodes"]) != len(expected):
            raise ValueError("Incomplete or duplicate evaluation episodes")
    if any(len(values) != 1 for values in (versions, hashes, metric_hashes, seeds, counts)):
        raise ValueError("Cannot combine incompatible environment versions or evaluation seed sets")
    rows = [row for shard in shards for row in shard["episodes"]]
    with (output / "episodes.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summaries = []
    for shard in shards:
        for scenario, duration in CONDITIONS:
            selected = [row for row in shard["episodes"] if row["scenario"] == scenario and row["duration"] == duration]
            summaries.append({"policy": shard["metadata"]["id"], "scenario": scenario,
                              "duration": duration, **aggregate(selected)})
    paired = []
    # Report paired road variation. This does not measure all training-seed variation.
    for shard in shards:
        if shard["metadata"].get("baseline"):
            continue
        for baseline in ("slow", "rule"):
            reference = next((s for s in shards if s["metadata"].get("baseline") == baseline), None)
            if reference is None:
                continue
            paired.append(paired_comparison(shard, reference))
    report = {"schema_version": 1, "split": split, "total_episodes": len(rows),
              "conditions": CONDITIONS, "models": [s["metadata"] for s in shards],
              "summary": summaries, "paired_baseline_comparisons": paired,
              "limitations": ["No human-level performance claim: no systematic human baseline has been collected.",
                              "Collision intervals quantify road-seed variation for each checkpoint, not training uncertainty.",
                              "Rule baseline receives the same 30 observations and five actions as RL, without future traffic information.",
                              "Delayed difficulty levels predict every N ticks and send IDLE on skipped ticks; no safety override is used."]}
    replicates = [shard for shard in shards if shard["metadata"].get("group") == "main_replicate"]
    if replicates:
        initialization_pairs = []
        same_budget_pairs = []
        for shard in replicates:
            seed = shard["metadata"]["seed"]
            initial = next((s for s in shards if s["metadata"].get("group") == "imitation_reference" and s["metadata"].get("seed") == seed), None)
            if initial:
                initialization_pairs.append(paired_comparison(shard, initial))
            pure = next((s for s in shards if s["metadata"].get("group") == "pure_ppo_reference" and s["metadata"].get("seed") == seed), None)
            if pure:
                same_budget_pairs.append(paired_comparison(shard, pure))
        report["paired_initialization_comparisons"] = initialization_pairs
        report["paired_same_budget_comparisons"] = same_budget_pairs
        per_seed = [{"seed": shard["metadata"]["seed"], "policy": shard["metadata"]["id"],
                     **aggregate(shard["episodes"])} for shard in replicates]
        for summary in per_seed:
            # The five settings reuse road seeds and some trajectory prefixes;
            # only per-condition rates get binomial confidence intervals.
            summary.pop("crash_ci95", None)
        report["main_training_replicates"] = {"runs": per_seed, "seeds": len(per_seed),
            "mean_quality_across_training_seeds": float(np.mean([row["mean_quality"] for row in per_seed])),
            "quality_std_across_training_seeds": float(np.std([row["mean_quality"] for row in per_seed], ddof=1)) if len(per_seed) > 1 else None,
            "note": "Training runs share one 60k demonstration dataset. No claim of variability across demonstration datasets."}
    write_json(output / "report.json", report)
    make_figures(report, output)
    return report


def make_figures(report, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ids = [item["id"] for item in report["models"]]
    short_names = {"comparison_ppo_200k": "PPO / 200k", "comparison_dqn_200k": "DQN / 200k",
                   "comparison_a2c_200k": "A2C / 200k", "ablation_normal_200k": "PPO fixed traffic / 200k",
                   "ablation_base_200k": "PPO base reward / 200k", "baseline_slow": "Slow cruise / 18 m/s",
                   "baseline_cruise": "Cruise / 24 m/s", "baseline_rule": "Rule driver"}
    labels = {item["id"]: item.get("label", short_names.get(item["id"], item["id"].replace("_", " "))) for item in report["models"]}
    colors = plt.cm.tab20(np.linspace(0, 1, len(ids)))
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    for index, name in enumerate(ids):
        selected = [row for row in report["summary"] if row["policy"] == name]
        axes[0].plot(range(len(CONDITIONS)), [r["crash_rate"] for r in selected], "o-", color=colors[index], label=labels[name])
        axes[1].scatter(np.mean([r["mean_speed_kmh"] for r in selected]), np.mean([r["crash_rate"] for r in selected]), s=70, color=colors[index], label=labels[name])
    axes[0].set_xticks(range(len(CONDITIONS)), [f"{s}\n{d}s" for s, d in CONDITIONS])
    axes[0].set_ylabel("Collision rate")
    axes[0].set_title("Held-out traffic scenarios")
    axes[1].set_xlabel("Mean speed (km/h)")
    axes[1].set_ylabel("Collision rate")
    axes[1].set_title("Safety and efficiency")
    for ax in axes:
        ax.grid(alpha=.2)
        ax.set_ylim(-.03, 1.03)
    axes[1].legend(fontsize=7, loc="upper left", bbox_to_anchor=(1.02, 1))
    fig.savefig(output / "safety_efficiency.png", dpi=170)
    plt.close(fig)
    lookup = {(row["policy"], row["scenario"], row["duration"]): row for row in report["summary"]}
    collision = np.array([[lookup[(name, scenario, duration)]["crash_rate"] for scenario, duration in CONDITIONS] for name in ids])
    fig, ax = plt.subplots(figsize=(11, max(5, len(ids)*.46+1.8)), constrained_layout=True)
    mesh = ax.imshow(collision, cmap="Reds", vmin=0, vmax=1, aspect="auto")
    ax.set_yticks(range(len(ids)), [labels[name] for name in ids])
    ax.set_xticks(range(len(CONDITIONS)), [f"{scenario.title()} / {duration}s" for scenario, duration in CONDITIONS])
    for y, name in enumerate(ids):
        for x, (scenario, duration) in enumerate(CONDITIONS):
            row = lookup[(name, scenario, duration)]
            ax.text(x, y, f"{row['crashes']}/{row['episodes']}  ({row['crash_rate']:.0%})", ha="center", va="center", color="white" if row["crash_rate"] > .55 else "#292929", fontsize=9)
    ax.set_title("Collisions on unseen roads — lower is better", pad=16)
    fig.colorbar(mesh, ax=ax, fraction=.025, pad=.02, label="Collision rate")
    fig.savefig(output / "collision_heatmap.png", dpi=180)
    plt.close(fig)
    if all("mean_qualified" in row for row in report["summary"]):
        qualified = np.array([[lookup[(name, scenario, duration)]["mean_qualified"] for scenario, duration in CONDITIONS] for name in ids])
        fig, ax = plt.subplots(figsize=(11, max(5, len(ids)*.46+1.8)), constrained_layout=True)
        mesh = ax.imshow(qualified, cmap="YlGnBu", vmin=0, vmax=1, aspect="auto")
        ax.set_yticks(range(len(ids)), [labels[name] for name in ids])
        ax.set_xticks(range(len(CONDITIONS)), [f"{scenario.title()} / {duration}s" for scenario, duration in CONDITIONS])
        for y in range(len(ids)):
            for x in range(len(CONDITIONS)):
                ax.text(x, y, f"{qualified[y,x]:.0%}", ha="center", va="center", color="white" if qualified[y,x] > .55 else "#292929", fontsize=10)
        ax.set_title("Safe completion with the required distance — higher is better", pad=16)
        fig.colorbar(mesh, ax=ax, fraction=.025, pad=.02, label="Qualified completion rate")
        fig.savefig(output / "mission_completion.png", dpi=180)
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(12, 6), constrained_layout=True)
    curve_items = {}
    for item in report["models"]:
        run = item.get("run_id")
        curve_rank = lambda value: (value.get("training_steps", 0), value.get("steps", value.get("checkpoint_steps", 0)))
        if run and (run not in curve_items or curve_rank(item) > curve_rank(curve_items[run])):
            curve_items[run] = item
    for item in curve_items.values():
        run = item.get("run_id")
        if not run or not (EXPERIMENTS / run / "progress.json").exists():
            continue
        progress = json.loads((EXPERIMENTS / run / "progress.json").read_text(encoding="utf-8"))
        values = progress.get("validations", [])
        if item.get("training_steps") is not None:
            values = [value for value in values if value["timesteps"] <= item["training_steps"]]
        ax.plot([v["timesteps"] for v in values], [v["mean_quality"] for v in values], marker=".", label=labels[item["id"]])
    ax.set_xlabel("Environment steps")
    ax.set_ylabel("Held-out development quality (higher is better)")
    ax.set_title("Checkpoint selection used development roads only")
    ax.grid(alpha=.2)
    if ax.lines:
        ax.legend(fontsize=8)
    fig.savefig(output / "learning_curves.png", dpi=170)
    plt.close(fig)


def run_item(run):
    folder = EXPERIMENTS / run
    metadata = json.loads((folder / "best.json").read_text(encoding="utf-8"))
    progress = json.loads((folder / "progress.json").read_text(encoding="utf-8"))
    demonstrations = metadata.get("imitation_transitions", 0)
    steps = metadata["actual_timesteps"]
    method = "imitation-only" if demonstrations and steps == 0 else "demonstration-warmstart-ppo" if demonstrations else "pure-rl"
    return {"id": run, "run_id": run, "path": (folder / "best.zip").relative_to(ROOT).as_posix(),
            "algorithm": metadata["algorithm"], "seed": metadata["seed"],
            "training_steps": 0 if method == "imitation-only" else progress["actual_timesteps"],
            "source_run_training_steps": progress["actual_timesteps"], "method": method,
            "demonstration_steps": demonstrations, "selection_scope": "best_including_initialization",
            "checkpoint_steps": steps, "inference_stride": 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", nargs="*", default=[])
    parser.add_argument("--registry", help="JSON mapping candidate IDs to frozen model specs (e.g. comparison_200k.json)")
    parser.add_argument("--baselines", nargs="*", choices=["slow", "crawl", "cruise", "rule", "random"], default=["slow", "cruise", "rule"])
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed-start", type=int, default=TEST_SEED_START)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--output", default="evaluation_final")
    parser.add_argument("--split", choices=["development", "test"], default="test")
    parser.add_argument("--deployment", action="store_true")
    parser.add_argument("--compile-only", action="store_true")
    args = parser.parse_args()
    if min(args.episodes, args.workers) <= 0:
        parser.error("episodes and workers must be positive")
    if args.split == "test" and args.seed_start < TEST_SEED_START:
        parser.error("Final test seeds must start at or above 891000")
    items = [run_item(run) for run in args.runs]
    if args.registry:
        registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
        items.extend({**spec, "id": name} for name, spec in registry.items())
    if args.deployment:
        manifest = json.loads((EXPERIMENTS / "deployment.json").read_text(encoding="utf-8"))
        for level_id, level in manifest["levels"].items():
            model = manifest["models"][level["model"]]
            items.append({"id": f"level_{level_id}", **model, "inference_stride": level.get("inference_stride", 1)})
    items.extend({"id": f"baseline_{name}", "baseline": name} for name in args.baselines)
    if not items:
        parser.error("No candidates supplied")
    if len({item["id"] for item in items}) != len(items):
        parser.error("Candidate IDs must be unique")
    output = EXPERIMENTS / args.output
    if EXPERIMENTS.resolve() not in output.resolve().parents:
        parser.error("Output must be within artifacts/experiments_v2")
    output.mkdir(parents=True, exist_ok=True)
    if not args.compile_only:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(evaluate, item, args.episodes, args.seed_start, output, args.split) for item in items]
            for future in as_completed(futures):
                future.result()
    report = compile_report(output, [item["id"] for item in items], args.split)
    print(f"Saved {report['total_episodes']} {args.split} episodes to {output}", flush=True)


if __name__ == "__main__":
    main()
