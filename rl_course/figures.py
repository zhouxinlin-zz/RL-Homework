"""Create reusable figures from real evaluation and training output."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


COLORS = {"random": "#94a6ad", "dqn": "#2c9ab1", "ppo": "#e49b6c"}
SCENARIOS = ["light", "normal", "dense"]
POLICIES = ["random", "dqn", "ppo"]


def plot_comparison(rows: list[dict], target: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 3.8), layout="constrained")
    metrics = [
        ("crash_rate", "Collision rate", "%", 100),
        ("mean_speed_kmh", "Average speed", "km/h", 1),
        ("mean_survival_seconds", "Survival time", "s", 1),
    ]
    x = np.arange(len(SCENARIOS))
    width = 0.23
    for axis, (metric, title, unit, scale) in zip(axes, metrics):
        for index, policy in enumerate(POLICIES):
            values = [
                next((row[metric] * scale for row in rows if row["policy"] == policy and row["scenario"] == scenario), 0)
                for scenario in SCENARIOS
            ]
            axis.bar(x + (index - 1) * width, values, width, label=policy.upper(), color=COLORS[policy])
        axis.set_xticks(x, [name.title() for name in SCENARIOS])
        axis.set_title(title, fontsize=12, fontweight="bold", pad=12)
        axis.set_ylabel(unit)
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#e6ecee")
        axis.set_axisbelow(True)
    axes[0].set_ylim(0, 105)
    axes[2].set_ylim(0, 32)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.06), frameon=False)
    fig.savefig(target, dpi=180, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def plot_training(models_dir: Path, target: Path) -> None:
    fig, axis = plt.subplots(figsize=(9.6, 3.8), layout="constrained")
    has_data = False
    for policy in ("dqn", "ppo"):
        path = models_dir / f"{policy}_seed42_episodes.csv"
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as file:
            rows = list(csv.DictReader(file))
        if not rows:
            continue
        has_data = True
        steps = np.array([int(row["timesteps"]) for row in rows])
        returns = np.array([float(row["return"]) for row in rows])
        window = max(5, min(30, len(returns) // 12))
        smooth = np.array([returns[max(0, i - window + 1):i + 1].mean() for i in range(len(returns))])
        axis.plot(steps, smooth, label=policy.upper(), color=COLORS[policy], linewidth=2.2)
    if not has_data:
        plt.close(fig)
        return
    axis.set_title("Training episode return", fontsize=13, fontweight="bold", pad=12)
    axis.set_xlabel("Environment steps")
    axis.set_ylabel("Smoothed return")
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(color="#e6ecee")
    axis.legend(frameon=False)
    fig.savefig(target, dpi=180, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, default=Path("artifacts/evaluation"))
    parser.add_argument("--models", type=Path, default=Path("artifacts/models"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/figures"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = json.loads((args.evaluation / "summary.json").read_text(encoding="utf-8"))
    plot_comparison(rows, args.output / "scenario_comparison.png")
    plot_training(args.models, args.output / "training_returns.png")
    print(f"Saved figures to {args.output}")


if __name__ == "__main__":
    main()
