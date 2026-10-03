"""Plot the recorded rare-action failure and combined warm-start revision."""
from __future__ import annotations

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from rl_course.v2_metrics import EXPERIMENTS, write_json


def main():
    runs = ["ppo_warm_s11", "ppo_warm60_s11"]
    labels = ["15 epochs\nweight cap 5", "60 epochs\nweight cap 20"]
    colors = ["#9ba6b1", "#277a75"]
    records = []
    for name in runs:
        folder = EXPERIMENTS / name
        imitation = json.loads((folder / "imitation.json").read_text(encoding="utf-8"))
        progress = json.loads((folder / "progress.json").read_text(encoding="utf-8"))
        driving = next(value for value in progress["validations"] if value["timesteps"] == 0)
        records.append({"run": name, "imitation": imitation["history"][-1],
                        "class_weights": imitation["class_weights"], "driving": driving})
    fig, axes = plt.subplots(2, 2, figsize=(10, 8), constrained_layout=True)
    for index, record in enumerate(records):
        value = record["imitation"]["validation_accuracy"] * 100
        axes[0, 0].bar(index, value, color=colors[index], width=.58)
        axes[0, 0].text(index, value+2, f"{value:.1f}%", ha="center")
    axes[0, 0].set_title("Overall action accuracy")
    axes[0, 0].set_ylim(0, 108)
    width = .3
    for index, record in enumerate(records):
        recalls = np.array(record["imitation"]["validation_recall_per_action"])[[0, 2]] * 100
        x = np.array([0, 1]) + (index-.5)*width
        axes[0, 1].bar(x, recalls, width=width, color=colors[index], label=labels[index].replace("\n", ", "))
        for location, value in zip(x, recalls):
            axes[0, 1].text(location, value+2, f"{value:.0f}%", ha="center", fontsize=9)
    axes[0, 1].set_xticks([0, 1], ["Left change", "Right change"])
    axes[0, 1].set_title("Recall of rare lane-change actions")
    axes[0, 1].set_ylim(0, 108)
    axes[0, 1].legend(fontsize=8, loc="upper left")
    for index, record in enumerate(records):
        driving = record["driving"]
        value = driving["crash_rate"] * 100
        axes[1, 0].bar(index, value, color=colors[index], width=.58)
        axes[1, 0].text(index, value+2, f"{driving['crashes']}/{driving['episodes']} crashes", ha="center", fontsize=9)
        passes = driving["mean_overtakes"]
        axes[1, 1].bar(index, passes, color=colors[index], width=.58)
        axes[1, 1].text(index, passes+.1, f"{passes:.2f}", ha="center")
    axes[1, 0].set_title("Driving collisions on development roads")
    axes[1, 0].set_ylim(0, 60)
    axes[1, 0].set_ylabel("Collision rate (%) · 6 seeds × 3 traffic settings")
    axes[1, 1].set_title("Mean completed overtakes")
    axes[1, 1].set_ylim(0, 4.5)
    for ax in (axes[0, 0], axes[1, 0], axes[1, 1]):
        ax.set_xticks([0, 1], labels)
    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=.15)
        ax.set_axisbelow(True)
    fig.suptitle("A high action accuracy can hide a failure to change lanes\nSame seed and data; epoch count and class weights changed together", fontsize=14)
    destination = EXPERIMENTS / "analysis_figures"
    destination.mkdir(exist_ok=True)
    fig.savefig(destination / "imitation_diagnostic.png", dpi=180)
    plt.close(fig)
    write_json(destination / "imitation_diagnostic.json", {"records": records,
        "interpretation": "多数示范帧为保持动作，整体准确率约88%仍可能完全不会换道。增加预训练轮数与稀有动作权重后，换道召回和真实驾驶表现一起改善。两项改动同时进行，不能把改进单独归因于类别权重。图中是开发集18局，不代替最终独立测试。"})
    print(destination / "imitation_diagnostic.png", flush=True)


if __name__ == "__main__":
    main()
