"""Verify the committed frontend by content, independent of Git checkout times."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

TEXT_EXTENSIONS = {".ts", ".tsx", ".js", ".mjs", ".css", ".json", ".html", ".svg", ".md", ".txt", ".yml", ".yaml"}
CONFIG_FILES = ("package.json", "package-lock.json", "index.html", "vite.config.ts", "tsconfig.json", "tsconfig.app.json", "tsconfig.node.json")


def fingerprint(path: Path) -> str:
    content = path.read_bytes()
    if path.suffix.lower() in TEXT_EXTENSIONS:
        content = content.replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def input_files(root: Path) -> list[Path]:
    web = root / "web"
    files = [path for folder in ("src", "public", "scripts") for path in web.joinpath(folder).rglob("*") if path.is_file()]
    files.extend(web / name for name in CONFIG_FILES if (web / name).is_file())
    return files


def snapshot(root: Path, files: list[Path]) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): fingerprint(path) for path in files}


def build_is_current(root: Path) -> bool:
    """Malformed, missing, changed or incomplete builds need regeneration."""
    manifest = root / "web/dist/build-info.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            return False
        outputs = [path for path in root.joinpath("web/dist").rglob("*") if path.is_file() and path != manifest]
        return (bool(data.get("inputs")) and bool(data.get("outputs"))
                and (root / "web/dist/index.html").is_file()
                and data["inputs"] == snapshot(root, input_files(root))
                and data["outputs"] == snapshot(root, outputs))
    except (OSError, ValueError, TypeError):
        return False
