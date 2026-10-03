"""Create presentation figures from recorded training and held-out evaluations."""
from __future__ import annotations
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from rl_course.academy import ACADEMY

COLORS = {"dqn": "#df985f", "ppo": "#70a75d", "a2c": "#4d9ac7", "ppo_mixed": "#9676bf", "random": "#a6a9ad", "cruise": "#64777d", "cautious": "#8e8672"}
LABELS = {"dqn": "DQN", "ppo": "PPO", "a2c": "A2C", "ppo_mixed": "PPO / mixed traffic", "random": "Random", "cruise": "Cruise 90 km/h", "cautious": "Cruise 72 km/h"}


def style():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#d1d9dc", "axes.labelcolor": "#374a51", "text.color": "#283e46", "xtick.color": "#627780", "ytick.color": "#627780", "figure.facecolor": "#fbfcfa", "axes.facecolor": "#fbfcfa", "grid.color": "#dce4e1", "grid.alpha": .6})


def main():
    style()
    output = ACADEMY / "figures"
    output.mkdir(parents=True, exist_ok=True)
    report = json.loads((ACADEMY / "evaluation/report.json").read_text(encoding="utf-8"))
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), layout="constrained")
    for ax, policy in zip(axes.flat, ("dqn", "ppo", "a2c", "ppo_mixed")):
        data = pd.read_csv(ACADEMY / f"{policy}_seed42/episodes.csv")
        ax.plot(data.timesteps, data["return"], color=COLORS[policy], alpha=.14, linewidth=.6)
        ax.plot(data.timesteps, data["return"].rolling(50, min_periods=1).mean(), color=COLORS[policy], linewidth=2)
        best = json.loads((ACADEMY / f"{policy}_seed42/best.json").read_text(encoding="utf-8"))
        ax.axvline(best["actual_timesteps"], linestyle="--", color="#597067", linewidth=1, label="Selected checkpoint")
        ax.set_title(LABELS[policy], loc="left", fontweight="bold")
        ax.set(xlabel="Environment steps", ylabel="Episode return")
        ax.grid(axis="y"); ax.legend(fontsize=8, frameon=False)
    fig.suptitle("Learning curves · training seed 42 · 50-episode moving average", fontsize=16, fontweight="bold")
    fig.savefig(output / "learning_curves.png", dpi=180); plt.close(fig)

    policies = [p for p in COLORS if any(row["policy"] == p for row in report["summary"])]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.4), layout="constrained")
    for ax, scenario in zip(axes, ("light", "normal", "dense")):
        rows = [next(row for row in report["summary"] if row["policy"] == p and row["scenario"] == scenario and row["duration"] == 30) for p in policies]
        values = np.array([r["crash_rate"] for r in rows]) * 100
        lower = values - np.array([r["crash_ci95"][0] for r in rows]) * 100
        upper = np.array([r["crash_ci95"][1] for r in rows]) * 100 - values
        ax.barh(np.arange(len(policies)), values, color=[COLORS[p] for p in policies], height=.62)
        ax.errorbar(values, np.arange(len(policies)), xerr=[np.maximum(0,lower), np.maximum(0,upper)], fmt="none", ecolor="#3d5359", capsize=3, linewidth=1)
        ax.set(yticks=np.arange(len(policies)), yticklabels=[LABELS[p] for p in policies], xlim=(0, 105), xlabel="Collision rate (%)")
        ax.invert_yaxis(); ax.set_title(scenario.capitalize() + " traffic", loc="left", fontweight="bold"); ax.grid(axis="x"); ax.set_axisbelow(True)
    fig.suptitle("Held-out traffic tests · seed 42 checkpoints · 95% Wilson intervals", fontsize=17, fontweight="bold")
    fig.savefig(output / "collision_comparison.png", dpi=180); plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5.5), layout="constrained")
    offsets = {"dqn": (8, 7), "ppo": (10, 8), "a2c": (22, 35), "ppo_mixed": (24, -18), "random": (-45, 14), "cruise": (10, 13), "cautious": (22, 13)}
    for row in report["summary"]:
        if row["scenario"] != "dense" or row["duration"] != 30 or row["training_seed"] not in (None, 42): continue
        policy = row["policy"]
        ax.scatter(row["mean_speed_kmh"], (1-row["crash_rate"])*100, s=230 if policy == "cautious" else 110, facecolors="none" if policy == "cautious" else COLORS[policy], edgecolors=COLORS[policy] if policy == "cautious" else "white", linewidth=1.5, zorder=3)
        ax.annotate(LABELS[policy], (row["mean_speed_kmh"], (1-row["crash_rate"])*100), xytext=offsets[policy], textcoords="offset points", fontsize=9, arrowprops={"arrowstyle": "-", "color": "#8ca09c", "lw": .6}, zorder=4)
    ax.set(xlabel="Mean speed (km/h)", ylabel="Collision-free episodes (%)", ylim=(-8, 110), title="Dense traffic · safety and driving efficiency")
    ax.margins(x=.25); ax.grid(); ax.set_axisbelow(True)
    fig.savefig(output / "safety_efficiency.png", dpi=180); plt.close(fig)

    pairs = report["paired_ppo_ablation"]
    if pairs:
        fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
        for i, row in enumerate(pairs):
            delta = row["crash_rate_delta_mixed_minus_ppo"]*100
            ci = np.array(row["paired_bootstrap_ci95"])*100
            ax.errorbar(delta, i, xerr=[[max(0,delta-ci[0])], [max(0,ci[1]-delta)]], fmt="o", color=COLORS["ppo_mixed"], capsize=5, markersize=8)
        ax.axvline(0, color="#879691", linestyle="--", linewidth=1)
        ax.set(yticks=range(len(pairs)), yticklabels=[f"seed {r['training_seed']} · {r['scenario']} / {r['duration']}s" for r in pairs], xlabel="Collision rate change: mixed PPO minus PPO (percentage points)", title="Mixed traffic training · paired 95% bootstrap intervals")
        ax.grid(axis="x"); ax.set_axisbelow(True)
        fig.savefig(output / "mixed_traffic_ablation.png", dpi=180); plt.close(fig)
    print(f"Saved four report figures to {output}")


if __name__ == "__main__": main()
