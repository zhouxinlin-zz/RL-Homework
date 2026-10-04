"""Identify the source actually loaded by a long-running local game server."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_revision(root=ROOT):
    digest = hashlib.sha256()
    paths = [*root.joinpath("server").glob("*.py"), *root.joinpath("rl_course").glob("*.py")]
    for relative in ("artifacts/experiments_v3/deployment.json", "artifacts/experiments_v3/iteration_4/release.json",
                     "artifacts/experiments_v3/iteration_5/release.json", "artifacts/experiments_v3/iteration_6/release.json"):
        if root.joinpath(relative).exists():
            paths.append(root / relative)
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:20]


# Capture at import time: rereading updated files per request would hide stale code.
LOADED_REVISION = source_revision()
