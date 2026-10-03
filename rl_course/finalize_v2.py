"""Reproducible calibration, model freezing and final-report assembly.

This module never selects models using final test results. Difficulty choices
are supplied explicitly after inspecting the separate calibration report.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rl_course.deploy_v2 import best_rl_checkpoint, freeze_model
from rl_course.evaluate_v2 import compile_report, paired_comparison
from rl_course.provenance_v2 import synchronize_shard
from rl_course.v2_metrics import EXPERIMENTS, aggregate, write_json, sha256

MAIN_RUNS = {seed: f"ppo_warm60_s{seed}" for seed in (11, 23, 47)}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def interpretation(report, manifest, destination):
    """Keep readable conclusions attached to the exact frozen measurements."""
    shards = {item["id"]: read(destination / f"{item['id']}.json") for item in report["models"]}
    pooled = {}
    for name, shard in shards.items():
        pooled[name] = aggregate(shard["episodes"])
        pooled[name].pop("crash_ci95", None)
    levels = {level: value["evaluation_policy"] for level, value in manifest["levels"].items()}
    test_order = [paired_comparison(shards[levels[stronger]], shards[levels[weaker]])
                  for weaker, stronger in (("beginner", "standard"), ("standard", "expert"))]
    checkpoints = []
    for seed, run in MAIN_RUNS.items():
        progress = read(EXPERIMENTS / run / "progress.json")
        best = max(progress["validations"], key=lambda row: row["mean_quality"])
        post_rl = max((row for row in progress["validations"] if row["timesteps"] > 0), key=lambda row: row["mean_quality"])
        checkpoints.append({"seed": seed, "budget_steps": progress["actual_timesteps"],
            "best_including_initialization_steps": best["timesteps"],
            "best_including_initialization_quality": best["mean_quality"],
            "best_after_rl_updates_steps": post_rl["timesteps"],
            "best_after_rl_updates_quality": post_rl["mean_quality"],
            "last_checkpoint_quality": progress["validations"][-1]["mean_quality"],
            "pure_bc_test": pooled[f"cal_bc_s{seed}"], "post_rl_test": pooled[f"cal_rl_s{seed}"]})
    expert = pooled[levels["expert"]]
    rule = pooled["baseline_rule"]
    notes = [
        f"高手档在独立的500局测试中发生{expert['crashes']}次碰撞，合格完赛率{expert['mean_qualified']:.1%}，平均完成超车{expert['mean_overtakes']:.2f}辆。",
        f"同道路规则基线发生{rule['crashes']}次碰撞，合格完赛率{rule['mean_qualified']:.1%}，平均超车{rule['mean_overtakes']:.2f}辆；规则基线应与学习模型平等展示。",
        "三档候选先在31200至31219的开发道路上校准并锁定，891000至891099的测试道路只验证冻结结果。每个种子在五种场景中复用，500局描述性比例不等于500个独立道路种子。",
        "PPO、DQN、A2C的约20万步对照只各有一个训练种子；三种子的重复实验用于示范预训练加PPO主线，不能据此宣称算法普遍排名。",
        "奖励项与固定车流消融各只有一个训练种子。当前结果没有证明每个奖励项都会独立提升超车表现，消融的原始结果与失败案例均保留。",
        "同预算比较指相同约100万次RL环境交互预算。示范预训练另使用共享的6万条规则示范，不能把预训练的数据与计算成本视为零。",
        "主线选取经过真实PPO更新的检查点；同时公开包含初始化的最优检查点、纯BC结果与最终检查点。继续训练可能下降，不能把纯BC的step0结果称为强化学习提升。",
        "预训练诊断中，较少轮次的网络虽然动作准确率约88%，仍没有学会换道；增加训练轮次并调整类别权重后改善了驾驶。两项改变同时进行，不单独归因于类别权重。",
        "没有系统采集真人成绩，因此不声称超过人类。模型只接收同样的30维观测并输出五个动作，推理时没有规则接管、额外速度或事故保护。",
    ]
    for row in checkpoints:
        before, after = row["pure_bc_test"], row["post_rl_test"]
        notes.append(f"训练种子{row['seed']}：纯BC碰撞率{before['crash_rate']:.1%}、合格率{before['mean_qualified']:.1%}；选定的实际RL检查点碰撞率{after['crash_rate']:.1%}、合格率{after['mean_qualified']:.1%}。这是同一批道路上的测量，改善和下降都保留。")
    initial_best = [str(row["seed"]) for row in checkpoints if row["best_including_initialization_steps"] == 0]
    if initial_best:
        notes.append(f"种子{', '.join(initial_best)}在原开发选模指标上的全局最优仍是step0初始化；这些结果不计作强化学习提升，主线另列timesteps>0的最优检查点。")
    for names, comparison in zip((("标准", "入门"), ("高手", "标准")), test_order):
        notes.append(f"冻结等级独立测试：{names[0]}对{names[1]}，{comparison['game_wins']}胜、{comparison['game_draws']}平、{comparison['game_losses']}负，共{comparison['pairs']}对；胜负按安全完赛、里程合格、游戏分数依次决定。")
    return {"language": "zh-CN", "notes": notes, "pooled_descriptive_metrics": pooled,
            "main_checkpoint_selection": checkpoints, "difficulty_test_comparisons": test_order,
            "selection_protocol": "Test results do not change model selection or level ordering."}


def deployment_figures(report, manifest, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    levels = manifest["levels"]
    expert_seed = manifest["models"][levels["expert"]["model"]]["seed"]
    names = [levels[level].get("evaluation_policy", levels[level]["calibration_candidate"]) for level in ("beginner", "standard", "expert")]
    names += [f"cal_bc_s{expert_seed}", "baseline_rule", "baseline_slow"]
    labels = ["Beginner", "Standard", "Expert", f"Pure BC\nseed {expert_seed}", "Rule driver", "Slow cruise\n18 m/s"]
    colors = ["#aab8c4", "#639aa5", "#df8850", "#9e94b8", "#3d7067", "#bcc1c7"]
    fig, axes = plt.subplots(1, 3, figsize=(14, 5), constrained_layout=True)
    keys = [("crash_rate", "Collisions (%) · lower is better", 100),
            ("mean_qualified", "Qualified finishes (%) · higher is better", 100),
            ("mean_overtakes", "Completed overtakes · higher is better", 1)]
    for ax, (key, title, scale) in zip(axes, keys):
        values = [float(np.mean([row[key] for row in report["summary"] if row["policy"] == name])) * scale for name in names]
        ax.barh(range(len(names)), values, color=colors, height=.65)
        ax.set_yticks(range(len(names)), labels)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=11)
        maximum = max(values + [1])
        ax.set_xlim(0, maximum * 1.24)
        for index, value in enumerate(values):
            ax.text(value + maximum*.025, index, f"{value:.1f}{'%' if scale == 100 else ''}", va="center", fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="x", alpha=.15)
        ax.set_axisbelow(True)
    fig.suptitle("Frozen game difficulty and reference drivers · 500 test episodes each\nFive routes, 100 identical road seeds per route; pooled values are descriptive", fontsize=13)
    fig.savefig(destination / "game_difficulty_comparison.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    for ax, key, title in zip(axes, ["crash_rate", "mean_qualified"],
                             ["Collisions (%) · lower is better", "Qualified finishes (%) · higher is better"]):
        for offset, prefix, label, color in [(-.18, "cal_bc_s", "Pure BC (0 RL steps)", "#9aaeb0"),
                                            (.18, "cal_rl_s", "Selected after PPO updates", "#d58a57")]:
            values = [np.mean([row[key] for row in report["summary"] if row["policy"] == f"{prefix}{seed}"]) * 100 for seed in (11, 23, 47)]
            locations = np.arange(3) + offset
            ax.bar(locations, values, width=.34, label=label, color=color)
            for x, value in zip(locations, values):
                ax.text(x, value+1.5, f"{value:.1f}%", ha="center", fontsize=9)
        ax.set_xticks(range(3), ["Seed 11", "Seed 23", "Seed 47"])
        ax.set_title(title, fontsize=11)
        ax.set_ylim(0, 110)
        ax.grid(axis="y", alpha=.15)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(fontsize=9, loc="upper left")
    fig.suptitle("Initialization and subsequent reinforcement learning · 500 test episodes per model\nPost-RL checkpoints selected on development roads within a 1m-step budget", fontsize=12)
    fig.savefig(destination / "initialization_vs_rl.png", dpi=180)
    plt.close(fig)


def prepare_calibration():
    for run in [*MAIN_RUNS.values(), "ppo_curriculum_s11"]:
        progress = read(EXPERIMENTS / run / "progress.json")
        if progress["status"] != "complete" or progress["actual_timesteps"] < 1000000:
            raise ValueError(f"Million-step run is not complete: {run}")
    fixed = read(EXPERIMENTS / "fixed_comparisons.json")
    candidates = {
        "cal_early_ppo": freeze_model("ppo_curriculum_s11", "cal_early_ppo", "checkpoints/step_50000.zip"),
        "cal_base_ppo": dict(fixed["ablation_base_200k"]),
        "cal_a2c": dict(fixed["comparison_a2c_200k"]),
        "cal_pure_ppo": freeze_model("ppo_curriculum_s11", "cal_pure_ppo"),
    }
    for name, label in {"cal_early_ppo": "Early PPO / 50k checkpoint", "cal_base_ppo": "PPO base reward / 200k",
                        "cal_a2c": "A2C / 200k", "cal_pure_ppo": "PPO / 1m budget"}.items():
        candidates[name]["label"] = label
    candidates["cal_pure_ppo"]["group"] = "pure_ppo_reference"
    for seed, run in MAIN_RUNS.items():
        candidates[f"cal_rl_s{seed}"] = {**freeze_model(run, f"cal_rl_s{seed}", best_rl_checkpoint(run)),
            "selection_scope": "best_after_rl_updates", "group": "main_replicate", "label": f"Demo + PPO / seed {seed}"}
        candidates[f"cal_bc_s{seed}"] = {**freeze_model(run, f"cal_bc_s{seed}", "actor_pretrained.zip"),
            "group": "imitation_reference", "label": f"Pure BC / seed {seed}"}
    write_json(EXPERIMENTS / "calibration_candidates.json", candidates)
    print(f"Prepared {len(candidates)} fixed calibration candidates", flush=True)


def freeze_levels(beginner, standard, expert):
    candidates = read(EXPERIMENTS / "calibration_candidates.json")
    choices = {"beginner": beginner, "standard": standard, "expert": expert}
    lock_path = EXPERIMENTS / "selection_lock.json"
    if lock_path.exists() and read(lock_path)["choices"] != choices:
        raise ValueError("Difficulty selection is already locked; start a new experiment before changing choices")
    if len(set(choices.values())) != 3:
        raise ValueError("Difficulty levels must use distinct measured candidates")
    if candidates[expert]["steps"] <= 0:
        raise ValueError("Expert must have received real reinforcement-learning updates")
    calibration = EXPERIMENTS / "calibration"
    level_rows = {}
    for level, name in choices.items():
        shard = read(calibration / f"{name}.json")
        if shard["metadata"]["split"] != "development" or shard["metadata"]["seed_start"] != 31200:
            raise ValueError("Only the declared calibration roads may select difficulty")
        if shard["metadata"]["episodes_per_condition"] != 20 or len(shard["episodes"]) != 100:
            raise ValueError("Difficulty calibration requires 20 episodes on each of five routes")
        if shard["metadata"]["sha256"] != candidates[name]["sha256"]:
            raise ValueError("Calibration checkpoint hash differs from deployment candidate")
        level_rows[level] = shard["episodes"]
    comparisons = []
    for weaker, stronger in (("beginner", "standard"), ("standard", "expert")):
        keyed = {(r["scenario"], r["duration"], r["seed"]): r for r in level_rows[weaker]}
        values = []
        rank = lambda row: (row["completed"], row["qualified"], row["score"])
        for row in level_rows[stronger]:
            other = keyed[(row["scenario"], row["duration"], row["seed"])]
            values.append(1 if rank(row) > rank(other) else .5 if rank(row) == rank(other) else 0)
        uncertainty = paired_comparison(
            {"metadata": {"id": choices[stronger]}, "episodes": level_rows[stronger]},
            {"metadata": {"id": choices[weaker]}, "episodes": level_rows[weaker]})
        comparisons.append({"stronger": stronger, "weaker": weaker, "episodes": len(values),
                            "game_win_score": sum(values)/len(values), "draw_value": .5,
                            "wins": values.count(1), "draws": values.count(.5), "losses": values.count(0),
                            "game_win_rate": values.count(1)/len(values),
                            "game_win_score_ci95": uncertainty["game_win_score_ci95"],
                            "seed_clusters": uncertainty["seed_clusters"]})
    if any(item["game_win_score"] <= .5 for item in comparisons):
        raise ValueError("Selected difficulty ordering is not supported by calibration games")
    fixed = read(EXPERIMENTS / "fixed_comparisons.json")
    models = {"ppo": candidates["cal_pure_ppo"], "dqn": fixed["comparison_dqn_200k"],
              "a2c": fixed["comparison_a2c_200k"], "ppo_mixed": candidates[expert],
              "beginner_policy": candidates[beginner], "standard_policy": candidates[standard]}
    labels = {"beginner": "入门", "standard": "标准", "expert": "高手"}
    descriptions = {"beginner": "更从容的驾驶节奏，适合练习路线与寻找超车机会。",
                    "standard": "观察周围车辆并主动调整车道，适合日常挑战。",
                    "expert": "经过独立路况校准，兼顾安全与通行效率的驾驶网络。"}
    aliases = {"beginner": "beginner_policy", "standard": "standard_policy", "expert": "ppo_mixed"}
    levels = {level: {"model": aliases[level], "inference_stride": 1, "label": labels[level],
        "description": descriptions[level], "calibration_candidate": name,
        "validation": aggregate(level_rows[level])} for level, name in choices.items()}
    for value in levels.values():
        value["validation"].pop("crash_ci95", None)
    manifest = {"schema_version": 1, "env_version": "2.0", "stage": "calibrated",
                "models": models, "levels": levels,
                "evaluation": {"status": "pending_final_test", "calibration_seed_start": 31200,
                    "calibration_episodes_per_condition": 20, "difficulty_comparisons": comparisons,
                    "selection_note": "All choices locked before reading final test results."}}
    final_candidates = {}
    canonical = {(spec["sha256"], spec.get("inference_stride", 1)): name for name, spec in fixed.items()}
    evaluation_mapping = {}
    for name, spec in candidates.items():
        if name not in {"cal_pure_ppo", *choices.values()} and not name.startswith(("cal_rl_", "cal_bc_")):
            continue
        key = (spec["sha256"], spec.get("inference_stride", 1))
        if key not in canonical:
            canonical[key] = name
            final_candidates[name] = spec
        evaluation_mapping[name] = canonical[key]
    for level in manifest["levels"].values():
        level["evaluation_policy"] = evaluation_mapping[level["calibration_candidate"]]
    write_json(EXPERIMENTS / "deployment.json", manifest)
    write_json(EXPERIMENTS / "final_main_candidates.json", final_candidates)
    write_json(EXPERIMENTS / "selection_lock.json", {"choices": choices,
        "difficulty_comparisons": comparisons, "models": final_candidates, "evaluation_mapping": evaluation_mapping,
        "protocol": read(EXPERIMENTS / "protocol.json"), "used_test_results": False})
    print(f"Locked calibrated difficulty: {choices}", flush=True)


def merge_final():
    destination = EXPERIMENTS / "evaluation_final"
    destination.mkdir(exist_ok=True)
    (destination / "failures").mkdir(exist_ok=True)
    fixed = read(EXPERIMENTS / "fixed_comparisons.json")
    main = read(EXPERIMENTS / "final_main_candidates.json")
    sources = [(EXPERIMENTS / "evaluation_fixed_test", [*fixed, "baseline_slow", "baseline_cruise", "baseline_rule"]),
               (EXPERIMENTS / "evaluation_main_test", list(main))]
    ids = []
    for source, names in sources:
        for name in names:
            shard = read(source / f"{name}.json")
            if shard["metadata"]["episodes_per_condition"] != 100:
                raise ValueError("Final report requires 100 real episodes per condition")
            specification = fixed.get(name, main.get(name))
            if specification and shard["metadata"]["sha256"] != specification["sha256"]:
                raise ValueError(f"Evaluated model does not match the locked checkpoint: {name}")
            failures = read(source / "failures" / f"{name}.json")
            if specification:
                shard = synchronize_shard(shard, specification)
                failures = synchronize_shard(failures, specification)
            write_json(destination / f"{name}.json", shard)
            write_json(destination / "failures" / f"{name}.json", failures)
            ids.append(name)
    report = compile_report(destination, ids, "test")
    manifest = read(EXPERIMENTS / "deployment.json")
    deployment_figures(report, manifest, destination)
    report["audit_notes"] = ["Game rules were frozen throughout evaluation; older fixed-comparison shards did not yet record a game-rules source hash.",
        "The first PPO/DQN/A2C pilots began before training-source hash logging was added. Missing historical hashes are left missing; their final evaluation records the actual evaluation environment and metrics hashes.",
        "Pure-BC rows have zero RL steps. Main replicate rows select only checkpoints after actual RL updates; original best-including-initialization history is retained."]
    report["metric_definitions"] = {
        "crash_rate": "物理碰撞比例；不把单纯驶出道路混为碰撞。",
        "failure_rate": "未安全完成规定时长的比例，包含碰撞和驶出道路。",
        "mean_qualified": "安全完赛且达到该关卡目标里程的比例。",
        "mean_speed_kmh": "终止前的平均车速；提前撞车的高速表现不能单独解释为更优秀。",
        "mean_overtakes": "完成整车超越的唯一前方车辆数，不重复奖励同一辆车。",
        "mean_quality": "用于开发选模的综合指标：2×完赛+距离/(30×时长)+0.02×min(超车,15)-0.2×危险时间/时长；它不等于游戏分数。",
        "game_win_score": "按游戏同一胜负顺序（安全完赛、里程合格、分数）配对比较，胜=1、平=0.5、负=0。",
        "uncertainty": "单条件100个道路种子的碰撞率使用Wilson区间；配对差异按道路种子整组bootstrap，保留五条件的相关性。"}
    report["baseline_definitions"] = {
        "baseline_slow": {"target_speed_mps": 18, "control": "One initial SLOWER action, then IDLE; no lane changes."},
        "baseline_cruise": {"target_speed_mps": 24, "control": "IDLE throughout; no lane changes."},
        "baseline_rule": {"control": "Deterministic following and lane-changing using the same 30 observations and five actions."},
        "crawl_note": "The optional crawl controller targets 12 m/s and is unit-tested, but it is not one of the reported final baselines."}
    report["deployed_difficulty_mechanism"] = {
        "mechanism": "Distinct frozen neural-network checkpoints selected on development roads.",
        "inference_stride": {name: level["inference_stride"] for name, level in manifest["levels"].items()},
        "rule_takeover": False, "extra_speed": False, "random_mistakes": False}
    completed, interrupted = [], []
    for path in EXPERIMENTS.glob("*/progress.json"):
        progress = read(path)
        row = {"run_id": progress["run_id"], "status": progress["status"],
               "actual_timesteps": progress["actual_timesteps"], "requested_timesteps": progress["requested_timesteps"]}
        (completed if progress["status"] == "complete" else interrupted).append(row)
    report["training_budget"] = {"completed_runs": completed,
        "completed_rl_timesteps": sum(row["actual_timesteps"] for row in completed),
        "shared_demonstration_transitions": 60000, "interrupted_runs": interrupted,
        "interruption_note": "An interrupted pilot's count is its last durable progress report, not an exact count of all work before termination."}
    report["game_rules_source_sha256"] = sha256(Path(__file__).with_name("game_rules.py"))
    report["interpretation"] = interpretation(report, manifest, destination)
    write_json(destination / "report.json", report)
    if manifest["stage"] not in {"calibrated", "final"}:
        raise ValueError("Finalizing requires the locked calibrated manifest")
    for level in manifest["levels"].values():
        policy_id = level.get("evaluation_policy", level["calibration_candidate"])
        level["evaluation"] = {"policy": policy_id, "episodes": 500,
            "conditions": [row for row in report["summary"] if row["policy"] == policy_id]}
    manifest["stage"] = "final"
    manifest["evaluation"].update({"status": "complete", "report": "artifacts/experiments_v2/evaluation_final/report.json",
        "report_sha256": sha256(destination / "report.json"), "test_seed_start": 891000,
        "episodes_per_condition": 100, "total_episodes": report["total_episodes"]})
    write_json(EXPERIMENTS / "deployment.json", manifest)
    print(f"Finalized {report['total_episodes']} evaluation episodes and {len(completed)} complete training runs", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare-calibration", "freeze-levels", "merge-final"])
    parser.add_argument("--beginner")
    parser.add_argument("--standard")
    parser.add_argument("--expert")
    args = parser.parse_args()
    if args.stage == "prepare-calibration":
        prepare_calibration()
    elif args.stage == "freeze-levels":
        if not all((args.beginner, args.standard, args.expert)):
            parser.error("freeze-levels requires all three candidate IDs")
        freeze_levels(args.beginner, args.standard, args.expert)
    else:
        merge_final()


if __name__ == "__main__":
    main()
