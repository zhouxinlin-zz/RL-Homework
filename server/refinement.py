"""Verified refinement results and read-only demonstration replays."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


def checked_file(root: Path, relative: str, digest: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("训练证据文件缺失。")
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("训练证据文件校验失败。")
    return path


def evidence(root: Path) -> tuple[dict, dict] | None:
    release_path = next((root / f"artifacts/experiments_v3/iteration_{number}/release.json"
        for number in (6, 5) if (root / f"artifacts/experiments_v3/iteration_{number}/release.json").exists()), None)
    if release_path is None:
        return None
    release = json.loads(release_path.read_text(encoding="utf-8"))
    if release.get("stage") != "final" or release.get("env_version") != "3.1":
        raise ValueError("训练实验尚未完成发布校验。")
    report = json.loads(checked_file(root, release["report"], release["report_sha256"]).read_text(encoding="utf-8"))
    if (report.get("stage") != "final" or report.get("env_version") != "3.1"
            or report["promoted"] != release["promoted"]):
        raise ValueError("训练报告与发布清单不一致。")
    chosen = report["candidate_spec"] if release["promoted"] else report["previous_spec"]
    if chosen != release["model"]:
        raise ValueError("部署模型与训练报告不一致。")
    checked_file(root, chosen["path"], chosen["sha256"])
    for key in ("candidate_spec", "previous_spec"):
        spec = report.get(key, {})
        if spec.get("config"):
            checked_file(root, spec["config"], spec["config_sha256"])
    return release, report


def replay(root: Path, track: str) -> dict:
    pair = evidence(root)
    if pair is None:
        raise FileNotFoundError("训练对照回放尚未生成。")
    _, report = pair
    spec = next((r for r in report["replays"] if r["id"] == track), None)
    if spec is None:
        raise KeyError(track)
    path = checked_file(root, spec["path"], spec["sha256"])
    return json.loads(gzip.decompress(path.read_bytes()))


def public_summary(report: dict) -> dict:
    return {key: report[key] for key in ("models", "histories", "paired", "promoted", "official",
        "total_training_steps", "episodes_per_route", "seed_start")} | {
        "replays": [{key: r[key] for key in ("id", "name", "seed", "duration")} for r in report["replays"]],
        "checkpoint_steps": report["candidate_spec"]["steps"],
        "candidate_run": report["candidate_spec"]["run_id"],
        "safety_retention": "anchor_strength" in report.get("training_method", {}),
        "upstream_refinement_steps": report.get("upstream_refinement_steps", 0),
    }
