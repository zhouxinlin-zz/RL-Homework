"""Export classroom figures from the frozen iteration report, never synthetic data."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(__file__).resolve().parents[1] / "artifacts/experiments_v3/iteration_4"
COLORS = {"PPO": "#548f30", "DQN": "#cf793e", "A2C": "#3d89bd"}


def main():
    report = json.loads((OUT / "report.json").read_text(encoding="utf-8"))
    items = report["algorithm_comparison"]
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.facecolor": "#fafbf9"})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
    labels = [item["algorithm"] for item in items] + ["Rule"]
    stats = [item["overall"] for item in items] + [report["models"]["rule"]["summary"]]
    colors = [COLORS[label] for label in labels[:-1]] + ["#929c9a"]
    for ax, title, values in (
        (axes[0], "Safe target completion (%)", [100 * s["qualification_rate"] for s in stats]),
        (axes[1], "Collisions / 300 roads", [s["crashes"] for s in stats]),
    ):
        bars = ax.bar(labels, values, color=colors, width=.55)
        ax.bar_label(bars, labels=[f"{v:.1f}" if ax is axes[0] else str(v) for v in values], padding=5)
        ax.set_title(title, loc="left", pad=20)
        ax.set_ylim(0, max(105 if ax is axes[0] else max(values) * 1.25, 1))
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=.18)
    fig.suptitle("Held-out evaluation · same 300 roads for every policy", fontsize=15)
    fig.supxlabel("Initialization and training budgets differ; this compares project checkpoints.", fontsize=9)
    fig.savefig(OUT / "algorithm_comparison.png", dpi=190)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.7), layout="constrained")
    for item in items:
        history = item["history"]
        x = np.array([point["steps"] for point in history]) / 1000
        y = np.array([point["qualification_rate"] for point in history]) * 100
        label = item["algorithm"]
        ax.plot(x, y, marker="o", markersize=4, linewidth=1.8, color=COLORS[label], label=label)
        selected = next(p for p in history if p["steps"] == item["checkpoint_steps"])
        ax.scatter([selected["steps"] / 1000], [100 * selected["qualification_rate"]],
                   marker="D", s=70, facecolor="white", edgecolor=COLORS[label], zorder=5)
    ax.set(title="Development performance during this round of training",
           xlabel="Additional environment steps (thousands)", ylabel="Safe target completion (%)", ylim=(0, 103))
    ax.grid(alpha=.18)
    ax.legend(loc="lower right")
    fig.supxlabel("36 development roads per point · diamonds mark selected checkpoints · not final test results", fontsize=9)
    fig.savefig(OUT / "learning_curves.png", dpi=190)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4), layout="constrained")
    pairs = report["paired_game_outcomes"]
    keys = ["new_vs_previous_expert", "expert_vs_rule", "standard_vs_beginner"]
    names = ["Candidate vs previous expert", "Deployed expert vs rule", "Standard vs beginner"]
    left = np.zeros(3)
    for field, label, color in [("wins", "First policy wins", "#87b868"),
                                ("draws", "Draw", "#bfc9c6"), ("losses", "First policy loses", "#df9c6e")]:
        values = np.array([pairs[key]["paired"]["all"][field] for key in keys])
        ax.barh(names, values, left=left, color=color, label=label)
        for index, value in enumerate(values):
            if value > 7:
                ax.text(left[index] + value / 2, index, str(value), ha="center", va="center")
        left += values
    ax.invert_yaxis()
    ax.set(xlim=(0, 300), xlabel="Paired roads", title="Head-to-head outcomes with identical starting traffic")
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.2), ncol=3, fontsize=9)
    fig.savefig(OUT / "paired_game_outcomes.png", dpi=190)
    plt.close(fig)
    print(f"Exported three figures to {OUT}")


if __name__ == "__main__":
    main()
