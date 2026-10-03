"""Package source, the built game and reproducible model artifacts for a course hand-in."""
from pathlib import Path
from importlib.metadata import distribution
import hashlib
import json
import os
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ("rl_course", "server", "scripts", "tests", "web/src", "web/public", "web/dist", "web/tests", "web/e2e", "web/audio-e2e", "artifacts/experiments_v2", "artifacts/experiments_v3")
FILES = ("README.md", "PROJECT_PLAN.md", "requirements.txt", "Start-Game.cmd", "Setup-Game.cmd", "Check-Game.cmd", ".gitignore", "web/package.json", "web/package-lock.json", "web/index.html", "web/vite.config.ts", "web/vitest.config.ts", "web/playwright.config.ts", "web/playwright.audio.config.ts", "web/tsconfig.json", "web/tsconfig.app.json", "web/tsconfig.node.json", "web/README.md", "artifacts/runtime-check.json", "artifacts/audio-tests/signal-report.json", "artifacts/preview/v3/01-main-menu.png", "artifacts/preview/v3/02-challenge-routes.png", "artifacts/preview/v3/05-live-duel.png", "artifacts/preview/v3/07-results.png")


def check_release_assets():
    """Do not replace a deliverable with incomplete or still-training policies."""
    from rl_course.game_rules import ENV_VERSION
    if not (ROOT / "web/dist/index.html").is_file():
        raise ValueError("Build the game before packaging: cd web && npm run build")
    manifest = json.loads((ROOT / "artifacts/experiments_v2/deployment.json").read_text(encoding="utf-8"))
    if manifest.get("stage") != "final" or manifest.get("env_version") != ENV_VERSION:
        raise ValueError("Finish model evaluation and freeze the final deployment before packaging")
    evaluation = manifest.get("evaluation", {})
    report = (ROOT / evaluation.get("report", "")).resolve()
    if evaluation.get("status") != "complete" or not report.is_relative_to(ROOT) or not report.is_file():
        raise ValueError("The deployment must reference a completed evaluation report")
    if hashlib.sha256(report.read_bytes()).hexdigest() != evaluation.get("report_sha256"):
        raise ValueError("The evaluation report differs from the frozen deployment")
    for level in ("beginner", "standard", "expert"):
        if manifest.get("levels", {}).get(level, {}).get("model") not in manifest.get("models", {}):
            raise ValueError(f"Missing calibrated AI level: {level}")
    for name, spec in manifest["models"].items():
        path = (ROOT / spec["path"]).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError(f"Missing game model: {name}")
        if spec.get("env_version") != ENV_VERSION or hashlib.sha256(path.read_bytes()).hexdigest() != spec.get("sha256"):
            raise ValueError(f"Game model version or checksum mismatch: {name}")
    from rl_course.challenge_rules import ENV_VERSION as CHALLENGE_ENV_VERSION
    challenge = json.loads((ROOT / "artifacts/experiments_v3/deployment.json").read_text(encoding="utf-8"))
    if challenge.get("stage") != "final" or challenge.get("env_version") != CHALLENGE_ENV_VERSION:
        raise ValueError("Finish the formation-road model selection and freeze a final v3 deployment")
    report_spec = challenge.get("evaluation", {})
    report_path = (ROOT / report_spec.get("report", "")).resolve()
    if (report_spec.get("status") != "complete" or not report_path.is_relative_to(ROOT)
            or not report_path.is_file()
            or hashlib.sha256(report_path.read_bytes()).hexdigest() != report_spec.get("report_sha256")):
        raise ValueError("The v3 deployment must reference its completed, unchanged test report")
    for level in ("beginner", "standard", "expert"):
        if challenge.get("levels", {}).get(level, {}).get("model") not in challenge.get("models", {}):
            raise ValueError(f"Missing evaluated v3 AI level: {level}")
    for name, spec in challenge["models"].items():
        path = (ROOT / spec["path"]).resolve()
        if (not path.is_relative_to(ROOT) or not path.is_file()
                or spec.get("env_version") != CHALLENGE_ENV_VERSION
                or hashlib.sha256(path.read_bytes()).hexdigest() != spec.get("sha256")):
            raise ValueError(f"Challenge model version or checksum mismatch: {name}")


def runtime_licenses():
    pending = list(json.loads((ROOT / 'web/package.json').read_text(encoding='utf-8'))['dependencies'])
    seen = set()
    while pending:
        name = pending.pop()
        if name in seen: continue
        seen.add(name)
        folder = ROOT / 'web/node_modules' / name
        manifest = folder / 'package.json'
        if not manifest.exists(): continue
        package = json.loads(manifest.read_text(encoding='utf-8'))
        pending.extend(package.get('dependencies', {}))
        for file in folder.iterdir():
            if file.is_file() and file.name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING')):
                yield file, f'THIRD_PARTY_LICENSES/{name}/{file.name}'
    for name in ('highway-env', 'stable-baselines3'):
        package = distribution(name)
        for file in package.files or []:
            if file.name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING')):
                yield Path(package.locate_file(file)), f'THIRD_PARTY_LICENSES/{name}/{file.name}'


def main():
    check_release_assets()
    output = ROOT / "artifacts/delivery/LaneShift-course.zip"
    temporary = output.with_suffix(".tmp.zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    paths = {ROOT / name for name in FILES}
    for name in DIRECTORIES:
        paths.update((ROOT / name).rglob("*"))
    selection = json.loads((ROOT / "artifacts/experiments_v3/selection_lock.json").read_text(encoding="utf-8"))
    selected_sources = {(ROOT / spec["source"]).resolve() for spec in selection["models"].values()}
    demonstrations = {(ROOT / "artifacts/experiments_v3/demonstrations/rule_50000_s17031.npz").resolve()}
    if any(not path.is_relative_to(ROOT) or not path.is_file() for path in selected_sources | demonstrations):
        raise ValueError("Selected training evidence is missing")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(paths):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".tmp"}: continue
            if ("checkpoints" in path.parts or path.suffix in {".pkl", ".npz"}) and path not in selected_sources | demonstrations: continue
            if path.name == "latest.zip" or ".tmp." in path.name: continue
            if not path.resolve().is_relative_to(ROOT): raise ValueError(f"Path leaves the project: {path}")
            archive.write(path, path.relative_to(ROOT))
        for path, name in runtime_licenses():
            archive.write(path, name)
        count = len(archive.namelist())
    with zipfile.ZipFile(temporary) as archive:
        corrupted = archive.testzip()
        if corrupted:
            raise ValueError(f"Package verification failed: {corrupted}")
    os.replace(temporary, output)
    print(f"Packaged {count} files: {output} ({output.stat().st_size / 1024**2:.1f} MB)")


if __name__ == "__main__": main()
