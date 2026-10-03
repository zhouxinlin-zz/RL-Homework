"""Make presentation-ready charts from the frozen version 3 test report."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from rl_course.evaluate_v3 import OUT


def main():
    output = OUT / "evaluation_final"
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    colors = {"v3_beginner": "#8ccaf0", "v3_standard": "#bca1f5",
              "v3_expert": "#a8df6e", "rule": "#e2ad72"}
    labels = {"v3_beginner": "Beginner PPO", "v3_standard": "Standard PPO",
              "v3_expert": "Expert PPO", "rule": "Rule baseline"}
    policies = ["v3_beginner", "v3_standard", "v3_expert", "rule"]
    roads = ["convoy", "weave", "pressure"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.7), constrained_layout=True)
    x = np.arange(len(roads))
    for index, policy in enumerate(policies):
        summary = report["models"][policy]["by_scenario"]
        offset = (index - 1.5) * .19
        axes[0].bar(x + offset, [100 * summary[road]["crash_rate"] for road in roads],
                    .18, color=colors[policy], label=labels[policy])
        axes[1].bar(x + offset, [100 * summary[road]["qualification_rate"] for road in roads],
                    .18, color=colors[policy], label=labels[policy])
    for ax, title, ylabel in zip(axes,
                                 ("Collision rate", "Safe target completion"),
                                 ("Episodes (%)", "Episodes (%)")):
        ax.set_xticks(x, [road.title() for road in roads])
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(axis="y", alpha=.18)
        ax.set_axisbelow(True)
    axes[0].legend(ncol=2, fontsize=8)
    axes[0].set_ylim(bottom=0)
    axes[1].set_ylim(0, 105)
    fig.savefig(output / "challenge_safety_and_goals.png", dpi=190)
    plt.close(fig)

    comparisons = report["paired_game_outcomes"]
    names = ("Expert vs rule", "Expert vs standard", "Standard vs beginner")
    keys = ("expert_vs_rule", "expert_vs_standard", "standard_vs_beginner")
    fig, ax = plt.subplots(figsize=(9.5, 4.2), constrained_layout=True)
    y = np.arange(len(keys))
    wins = np.array([comparisons[key]["paired"]["all"]["wins"] for key in keys])
    draws = np.array([comparisons[key]["paired"]["all"]["draws"] for key in keys])
    losses = np.array([comparisons[key]["paired"]["all"]["losses"] for key in keys])
    totals = wins + draws + losses
    ax.barh(y, wins / totals * 100, color="#a8df6e", label="First policy wins")
    ax.barh(y, draws / totals * 100, left=wins / totals * 100,
            color="#b4bec3", label="Draw")
    ax.barh(y, losses / totals * 100, left=(wins + draws) / totals * 100,
            color="#e2ad72", label="First policy loses")
    for i, (win, total) in enumerate(zip(wins, totals)):
        ax.text(2, i, f"{win}/{total} wins", va="center", fontsize=10, fontweight="bold")
    ax.set_yticks(y, names)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Paired held-out roads (%)")
    ax.legend(loc="lower right", ncol=3, fontsize=8)
    ax.set_title("Game outcomes on identical traffic seeds")
    fig.savefig(output / "paired_game_outcomes.png", dpi=190)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9.5, 4.8), constrained_layout=True)
    for run_id, label, color in (
        ("safe_transfer_s47", "Transferred PPO", "#6eae44"),
        ("safe_imitation_s23", "Imitation + PPO", "#987dd8"),
        ("scratch_s11", "PPO from scratch (v3.0)", "#82939b"),
    ):
        progress_path = OUT / run_id / "progress.json"
        if not progress_path.exists():
            continue
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        values = progress["validations"]
        ax.plot([v["timesteps"] / 1000 for v in values],
                [v["mean_quality"] for v in values], marker="o", markersize=3,
                linewidth=1.7, color=color, label=label)
    ax.set_xlabel("Additional environment steps (thousands)")
    ax.set_ylabel("Development quality")
    ax.set_title("Checkpoint performance is not monotonic")
    ax.grid(alpha=.2)
    ax.legend()
    fig.savefig(output / "learning_curves.png", dpi=190)
    plt.close(fig)
    print(f"Saved presentation charts to {output}")


if __name__ == "__main__":
    main()
