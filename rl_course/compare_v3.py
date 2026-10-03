"""Pair two challenge policies on identical roads using the game scoring rule."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rl_course.challenge_rules import CHALLENGE_TRACKS
from rl_course.game_rules import duel_outcome, performance


def compare(left: dict, right: dict) -> dict:
    if left["env_version"] != right["env_version"]:
        raise ValueError("Cannot compare results from different road versions")
    if left["duration"] != right["duration"] or left["duration"] != "game_routes":
        raise ValueError("Both evaluations must use the game route durations")
    keys = lambda report: {(row["scenario"], row["seed"]): row for row in report["episodes"]}
    a, b = keys(left), keys(right)
    if len(a) != len(left["episodes"]) or len(b) != len(right["episodes"]) or a.keys() != b.keys():
        raise ValueError("Paired evaluation requires the same unique scenario and seed keys")
    result = {}
    for track in CHALLENGE_TRACKS:
        name = track["scenario"]
        outcomes = []
        for key in sorted(a):
            if key[0] != name:
                continue
            runs = []
            for row in (a[key], b[key]):
                game = performance(track, done=True, crashed=not row["completed"],
                                   distance=row["distance_m"], overtakes=row["overtakes"],
                                   danger_seconds=row["danger_seconds"])
                runs.append({"done": True, "crashed": row["crashed"], **game})
            outcomes.append(duel_outcome(*runs))
        result[name] = {"pairs": len(outcomes),
                        "wins": outcomes.count("win"), "losses": outcomes.count("loss"),
                        "draws": outcomes.count("draw")}
    result["all"] = {key: sum(item[key] for name, item in result.items() if name != "all")
                     for key in ("pairs", "wins", "losses", "draws")}
    return {"left": left["policy"], "right": right["policy"], "env_version": left["env_version"],
            "paired": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    args = parser.parse_args()
    a = json.loads(args.left.read_text(encoding="utf-8"))
    b = json.loads(args.right.read_text(encoding="utf-8"))
    print(json.dumps(compare(a, b), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
