"""Check the local game installation without starting a training job."""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def inspect() -> list[dict]:
    checks = [{"name": "Python >= 3.12", "ok": sys.version_info >= (3, 12), "detail": sys.version.split()[0], "required": True}]
    for module in ("torch", "gymnasium", "highway_env", "stable_baselines3", "fastapi", "uvicorn"):
        try:
            loaded = importlib.import_module(module)
            checks.append({"name": module, "ok": True, "detail": getattr(loaded, "__version__", "installed"), "required": True})
        except ImportError as error:
            checks.append({"name": module, "ok": False, "detail": str(error), "required": True})
    checks.append({"name": "Game assets", "ok": (ROOT / "web/dist/index.html").is_file(), "detail": "web/dist/index.html", "required": True})
    challenge_path = ROOT / "artifacts/experiments_v3/deployment.json"
    try:
        from server.catalog import challenge_deployment
        challenge = challenge_deployment()
        ready = challenge.get("env_version") == "3.1" and challenge.get("stage") == "final"
        checks.append({"name": "Challenge AI registry", "ok": ready,
                       "detail": str(challenge_path.relative_to(ROOT)), "required": True})
        evaluation = challenge.get("evaluation", {})
        report = (ROOT / evaluation.get("report", "")).resolve()
        report_ok = (evaluation.get("status") == "complete" and report.is_relative_to(ROOT)
                     and report.is_file()
                     and hashlib.sha256(report.read_bytes()).hexdigest() == evaluation.get("report_sha256"))
        checks.append({"name": "Challenge evaluation", "ok": report_ok,
                       "detail": "verified" if report_ok else "missing or changed final report",
                       "required": True})
        for level in ("beginner", "standard", "expert"):
            spec = challenge.get("levels", {}).get(level, {})
            checks.append({"name": f"Challenge level {level}",
                           "ok": spec.get("model") in challenge.get("models", {}),
                           "detail": spec.get("model", "missing"), "required": True})
        for name, spec in challenge.get("models", {}).items():
            path = (ROOT / spec["path"]).resolve()
            exists = path.is_relative_to(ROOT) and path.is_file()
            valid = exists and spec.get("env_version") == "3.1" and hashlib.sha256(path.read_bytes()).hexdigest() == spec.get("sha256")
            checks.append({"name": f"Challenge AI {name}", "ok": valid,
                           "detail": "verified" if valid else "model missing or checksum mismatch",
                           "required": True})
    except (OSError, ValueError, KeyError) as error:
        checks.append({"name": "Challenge AI registry", "ok": False, "detail": str(error), "required": True})
    manifest_path = ROOT / "artifacts/experiments_v2/deployment.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        checks.append({"name": "AI registry", "ok": manifest.get("env_version") == "2.0", "detail": str(manifest_path.relative_to(ROOT)), "required": False})
        for name, spec in manifest.get("models", {}).items():
            path = (ROOT / spec["path"]).resolve()
            exists = path.is_relative_to(ROOT) and path.is_file()
            valid = exists and spec.get("env_version", "2.0") == "2.0" and (not spec.get("sha256") or hashlib.sha256(path.read_bytes()).hexdigest() == spec["sha256"])
            checks.append({"name": f"AI {name}", "ok": valid, "detail": "verified" if valid else "model missing or checksum mismatch", "required": False})
    except (OSError, ValueError, KeyError) as error:
        checks.append({"name": "AI registry", "ok": False, "detail": str(error), "required": False})
    folder = Path(os.environ.get("LANE_SHIFT_DATA_DIR", str(ROOT / "artifacts/game")))
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=folder) as handle:
            handle.write(b"lane-shift-write-check")
        checks.append({"name": "Save folder", "ok": True, "detail": str(folder), "required": True})
    except OSError as error:
        checks.append({"name": "Save folder", "ok": False, "detail": str(error), "required": True})
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    checks = inspect()
    failed = [item for item in checks if item["required"] and not item["ok"]]
    if args.json:
        print(json.dumps(checks, ensure_ascii=False, indent=2))
    else:
        print("LANE SHIFT - installation check\n")
        for item in checks:
            print(f"[{'OK' if item['ok'] else 'FAIL' if item['required'] else 'NOTICE'}] {item['name']}: {item['detail']}")
        if failed:
            print("\nFor missing dependencies run Setup-Game.cmd; for missing models restore the complete project archive.")
        else:
            print("\nGame installation and model evidence verified.")
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
