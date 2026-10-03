"""Figures and cross-checks derived from the archived experiment records."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import statistics


def pressure_breakdown(experiment: Path, filename: str, expected: dict) -> dict:
    record = json.loads((experiment / filename).read_text(encoding="utf-8"))
    episodes = [item for item in record["episodes"] if item["scenario"] == "pressure"]
    assert len(episodes) == expected["episodes"] == 100
    assert {item["seed"] for item in episodes} == set(range(1631100, 1631200))
    qualified = sum(item["qualified"] for item in episodes)
    crashed = sum(item["crashed"] for item in episodes)
    short = [item for item in episodes if item["completed"] and not item["crashed"] and not item["qualified"]]
    assert qualified == round(expected["qualification_rate"] * 100)
    assert crashed == expected["crashes"]
    assert qualified + crashed + len(short) == len(episodes), "An unclassified failure needs review."
    return {
        "qualified": qualified, "crashed": crashed, "short": len(short),
        "median_shortfall": statistics.median(1270 - item["distance_m"] for item in short),
    }


def training_figure(progress: dict, destination: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MultipleLocator

    samples = progress["validations"]
    x = [item["timesteps"] / 10000 for item in samples]
    assert x == sorted(set(x)), "The validation history must be ordered and unique."
    assert all(item["episodes"] == 24 for item in samples)
    chosen = next(i for i, item in enumerate(samples) if item["timesteps"] == 175000)
    plt.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "Noto Sans CJK SC", "DejaVu Sans"],
        "axes.unicode_minus": False, "font.size": 20,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#aaa", "axes.labelcolor": "#333",
        "xtick.color": "#555", "ytick.color": "#555",
        "figure.facecolor": "#fafaf8", "axes.facecolor": "#fafaf8",
    })
    fig, axes = plt.subplots(2, 1, figsize=(14, 6), sharex=True)
    fig.subplots_adjust(left=.12, right=.97, top=.88, bottom=.13, hspace=.27)
    for ax, key, label, limit in zip(
        axes, ("mean_distance_m", "mean_danger_seconds"),
        ("里程 / 米", "危险时间 / 秒"), ((0, 1400), (0, 4)),
    ):
        y = [item[key] for item in samples]
        ax.plot(x, y, color="#666", linewidth=2, marker="o", markersize=4,
                label="各检查点开发评估")
        ax.axvline(x[chosen], color="#002fa7", linestyle="--", linewidth=1.5)
        ax.scatter([x[chosen]], [y[chosen]], color="#002fa7", s=75, zorder=4,
                   label="正式部署点 17.5 万步")
        ax.set_ylabel(label)
        ax.set_ylim(*limit)
        ax.set_xlim(-1, 52)
        ax.grid(axis="y", color="#ddd", linewidth=.7)
        ax.set_axisbelow(True)
        ax.annotate(f"{y[chosen]:.0f}", (x[chosen], y[chosen]), xytext=(8, 10),
                    textcoords="offset points", color="#002fa7", fontsize=20)
    axes[0].yaxis.set_major_locator(MultipleLocator(500))
    axes[1].yaxis.set_major_locator(MultipleLocator(1))
    axes[1].xaxis.set_major_locator(MultipleLocator(10))
    axes[1].set_xlabel("本次安全微调的环境交互步数 / 万步")
    axes[0].legend(loc="lower left", bbox_to_anchor=(0, 1.04), ncols=2,
                   frameon=False, fontsize=18, borderaxespad=0)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=150, metadata={"Software": "Matplotlib"})
    plt.close(fig)


def evidence_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
