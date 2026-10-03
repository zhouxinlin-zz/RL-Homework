"""Launch the built game in its own browser app window with one command."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

from rl_course.challenge_rules import GAME_VERSION
from server.runtime import source_revision

ROOT = Path(__file__).resolve().parents[1]


def running_version(url):
    try:
        with urllib.request.urlopen(url + "/api/game/catalog", timeout=1) as response:
            return json.load(response).get("version")
    except (OSError, ValueError, urllib.error.URLError):
        return None


def healthy(url):
    try:
        with urllib.request.urlopen(url + "/api/health", timeout=1) as response:
            data = json.load(response)
        return data.get("version") == GAME_VERSION and data.get("loaded_revision") == source_revision()
    except (OSError, ValueError, urllib.error.URLError):
        return False


def frontend_needs_build(root=ROOT):
    index = root / "web/dist/index.html"
    if not index.exists():
        return True
    inputs = [*root.joinpath("web/src").rglob("*"), *root.joinpath("web/public").rglob("*")]
    inputs.extend(root.joinpath("web", name) for name in ("package.json", "package-lock.json", "index.html", "vite.config.ts", "tsconfig.app.json"))
    return any(path.is_file() and path.stat().st_mtime_ns > index.stat().st_mtime_ns for path in inputs)


def port_available(port):
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def choose_port(preferred):
    for port in [preferred, *range(preferred + 2, min(preferred + 22, 65536))]:
        url = f"http://127.0.0.1:{port}"
        if port_available(port) or healthy(url):
            return port
        print(f"Port {port} has an older or different service; starting the current game on another port.", flush=True)
    raise SystemExit("No local game port is available. Use Start-Game.cmd --port 8800.")


def open_window(url):
    candidates = [Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe", Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Microsoft/Edge/Application/msedge.exe"]
    edge = next((path for path in candidates if path.exists()), None)
    if edge:
        subprocess.Popen([str(edge), f"--app={url}", "--window-size=1440,900"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-window", action="store_true")
    parser.add_argument("--build", action="store_true", help="Rebuild after editing the frontend")
    args = parser.parse_args()
    os.chdir(ROOT)
    try:
        import fastapi, uvicorn, highway_env, stable_baselines3  # noqa: F401
    except ImportError as error:
        raise SystemExit(f"Missing game dependency: {error}. Run Setup-Game.cmd first.") from error
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if args.build or frontend_needs_build():
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if not npm:
            raise SystemExit("Node.js is required for the first build. See README.md.")
        if not (ROOT / "web/node_modules").exists():
            subprocess.run([npm, "ci"], cwd=ROOT / "web", check=True)
        subprocess.run([npm, "run", "build"], cwd=ROOT / "web", check=True)
    args.port = choose_port(args.port)
    url = f"http://127.0.0.1:{args.port}"
    if healthy(url):
        print(f"Game is already running: {url}")
        if not args.no_window: open_window(url)
        return
    child = subprocess.Popen([sys.executable, "-m", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", str(args.port)], cwd=ROOT)
    try:
        for _ in range(100):
            if child.poll() is not None: raise SystemExit("Game server stopped. See the message above.")
            if healthy(url): break
            time.sleep(.2)
        else: raise SystemExit("Game server did not start in time.")
        print(f"LANE SHIFT is ready: {url}\nKeep this terminal open. Press Ctrl+C to stop.", flush=True)
        if not args.no_window: open_window(url)
        child.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if child.poll() is None:
            child.terminate()
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: child.kill()


if __name__ == "__main__": main()
