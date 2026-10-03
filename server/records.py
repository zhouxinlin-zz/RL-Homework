"""Persistent local run history; replay bodies are compressed in SQLite."""
from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import zlib

from server.catalog import ROOT
from rl_course.game_rules import GAME_VERSION
from rl_course.challenge_rules import GAME_VERSION as CHALLENGE_GAME_VERSION


class RecordStore:
    def __init__(self, path: Path | None = None):
        self.path = path or Path(os.environ.get("LANE_SHIFT_DATA_DIR", str(ROOT / "artifacts" / "game"))) / "records.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), track TEXT, mode TEXT, score INTEGER, stars INTEGER, summary TEXT, replay BLOB)")
            columns = {row[1] for row in db.execute("PRAGMA table_info(runs)")}
            if "version" not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN version TEXT NOT NULL DEFAULT '0.3.0'")
            if "practice" not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN practice INTEGER NOT NULL DEFAULT 0")
            db.execute("CREATE INDEX IF NOT EXISTS runs_version_track ON runs(version,track,mode)")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, summary: dict, frames: list[dict]):
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO runs(id,track,mode,score,stars,summary,replay,version,practice) VALUES(?,?,?,?,?,?,?,?,?)", (summary["session_id"], summary["track"]["id"], summary["mode"], summary["score"], summary["stars"], json.dumps(summary, ensure_ascii=False), zlib.compress(json.dumps(frames, separators=(",", ":")).encode()), summary.get("version", "0.3.0"), int(summary.get("practice", False))))

    def list(self, limit=50):
        with self.connect() as db:
            rows = db.execute("SELECT id,created,summary FROM runs ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
            best = db.execute("SELECT track,MAX(score) AS score,MAX(stars) AS stars FROM runs WHERE mode != 'ai' AND practice=0 AND version IN (?,?) GROUP BY track", (GAME_VERSION, CHALLENGE_GAME_VERSION)).fetchall()
            count = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            battles = db.execute("SELECT summary FROM runs WHERE mode='duel' AND practice=0 AND version IN (?,?)", (GAME_VERSION, CHALLENGE_GAME_VERSION)).fetchall()
        duels = {"played": 0, "wins": 0, "losses": 0, "draws": 0, "by_level": {}}
        for row in battles:
            battle = json.loads(row["summary"])
            outcome = battle.get("outcome")
            if not battle.get("done") or outcome not in ("win", "loss", "draw"):
                continue
            key = {"win": "wins", "loss": "losses", "draw": "draws"}[outcome]
            level = battle.get("ai_level") or "custom"
            totals = duels["by_level"].setdefault(level, {"played": 0, "wins": 0, "losses": 0, "draws": 0})
            for item in (duels, totals):
                item["played"] += 1
                item[key] += 1
        return {"runs": [{**json.loads(row["summary"]), "created": row["created"]} for row in rows],
                "best": [dict(row) for row in best], "total_runs": count, "version": CHALLENGE_GAME_VERSION, "duels": duels}

    def replay(self, run_id: str):
        with self.connect() as db:
            row = db.execute("SELECT summary,replay FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return {"summary": json.loads(row["summary"]), "frames": json.loads(zlib.decompress(row["replay"]))}
