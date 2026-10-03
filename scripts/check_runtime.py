"""Measure real local duel steps using deployed models and isolated temporary saves."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/runtime-check.json")
    args = parser.parse_args()
    if not 5 <= args.steps <= 1000:
        parser.error("steps must be between 5 and 1000")
    with tempfile.TemporaryDirectory(prefix="lane-shift-runtime-") as folder:
        os.environ["LANE_SHIFT_DATA_DIR"] = folder
        from server.catalog import ai_catalog
        from server.game import GameManager
        from server.records import RecordStore
        from rl_course.game_rules import GAME_VERSION
        manager = GameManager(RecordStore(Path(folder) / "runtime.sqlite"))
        results = []
        for level in ai_catalog():
            if not level["available"]:
                continue
            elapsed = []
            action_counts = [0] * 5
            started = time.perf_counter()
            state = manager.create("duel", "metro", seed=52030, ai_level=level["id"])
            loading_ms = (time.perf_counter() - started) * 1000
            try:
                for index in range(args.steps):
                    tick = time.perf_counter()
                    state = manager.advance(state["session_id"], 1)
                    elapsed.append((time.perf_counter() - tick) * 1000)
                    action_counts[state["rival"]["frame"]["action"]] += 1
                    if state["done"]:
                        break
                ordered = sorted(elapsed)
                p95 = ordered[min(len(ordered) - 1, int(len(ordered) * .95))]
                results.append({"level": level["id"], "steps": len(elapsed),
                                "model": state["rival"].get("model_info"),
                                "track": "metro", "road_seed": 52030,
                                "model_load_ms": round(loading_ms, 2),
                                "step_median_ms": round(statistics.median(elapsed), 2),
                                "step_p95_ms": round(p95, 2),
                                "step_max_ms": round(max(elapsed), 2),
                                "meets_200ms_tick": p95 < 200,
                                "ai_actions": action_counts,
                                "ai_distance_m": state["rival"]["distance_m"],
                                "ai_overtakes": state["rival"]["overtakes"]})
            finally:
                manager.close(state["session_id"])
        report = {"version": GAME_VERSION, "kind": "backend-step-latency", "results": results,
                  "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                  "note": "Measured in this machine's current load; includes both worlds, inference and serialization. Excludes HTTP, rendering and human input latency."}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0 if results and all(item["meets_200ms_tick"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
