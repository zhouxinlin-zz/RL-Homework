"""Copy evaluation artifacts into the static web application.

Run after ``python -m rl_course.evaluate``.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from shutil import copyfile


def export(evaluation_dir: Path, models_dir: Path, web_data_dir: Path) -> None:
    summary = evaluation_dir / "summary.json"
    if not summary.exists():
        raise FileNotFoundError(f"Run evaluation first: {summary} is missing")
    web_data_dir.mkdir(parents=True, exist_ok=True)
    copyfile(summary, web_data_dir / "summary.json")
    replays = sorted(evaluation_dir.glob("replay_*.json"))
    for replay in replays:
        copyfile(replay, web_data_dir / replay.name)

    training: dict[str, list[dict[str, float | int]]] = {}
    for algo in ("dqn", "ppo"):
        csv_path = models_dir / f"{algo}_seed42_episodes.csv"
        if not csv_path.exists():
            continue
        with csv_path.open(newline="", encoding="utf-8") as file:
            training[algo] = [
                {
                    "timesteps": int(row["timesteps"]),
                    "episode": int(row["episode"]),
                    "return": float(row["return"]),
                    "length": int(row["length"]),
                }
                for row in csv.DictReader(file)
            ]
    (web_data_dir / "training.json").write_text(
        json.dumps(training, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Exported {len(replays)} real replays and training logs to {web_data_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, default=Path("artifacts/evaluation"))
    parser.add_argument("--models", type=Path, default=Path("artifacts/models"))
    parser.add_argument("--web-data", type=Path, default=Path("web/public/data"))
    args = parser.parse_args()
    export(args.evaluation, args.models, args.web_data)


if __name__ == "__main__":
    main()
