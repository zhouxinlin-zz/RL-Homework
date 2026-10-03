"""Behavioral checks for fair starts, complete replay persistence and finalization."""
import tempfile
import copy
import json
import sqlite3
import zlib
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest
from unittest.mock import patch

from server.game import GameManager
from server.records import RecordStore
from rl_course.game_rules import GAME_VERSION, ENV_VERSION, duel_outcome, track_by_id


class CruisePolicy:
    def predict(self, observation, deterministic=True):
        return 1, None


class ControlledManager(GameManager):
    def load_model(self, policy):
        return CruisePolicy(), 0


class GameTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.manager = ControlledManager(RecordStore(Path(self.folder.name) / "runs.sqlite"))

    def tearDown(self):
        for run_id in list(self.manager.sessions): self.manager.close(run_id)
        self.folder.cleanup()

    def test_duel_starts_equal_and_identical_actions_remain_equal(self):
        state = self.manager.create("duel", "coast", "ppo", 91234)
        self.assertEqual(state["frame"]["vehicles"], state["rival"]["frame"]["vehicles"])
        for _ in range(10):
            state = self.manager.advance(state["session_id"], 1)
            self.assertEqual(state["frame"], state["rival"]["frame"])
        self.assertAlmostEqual(state["frame"]["time_s"], 2)

    def test_challenge_duel_uses_identical_formation_roads_and_version(self):
        state = self.manager.create("duel", "pressure", "v3_expert", 7391)
        self.assertEqual(state["env_version"], "3.1")
        self.assertEqual(state["track"]["scenario"], "pressure")
        self.assertEqual(state["frame"], state["rival"]["frame"])
        self.assertGreaterEqual(len(state["frame"]["vehicles"]), 8)
        for _ in range(35):
            state = self.manager.advance(state["session_id"], 1)
            self.assertEqual(state["frame"], state["rival"]["frame"])
        session = self.manager.get(state["session_id"])
        self.assertEqual(session.player.env.formation_events,
                         session.rival.env.formation_events)

    def test_terminal_saved_once_and_replay_ends_at_final_state(self):
        state = self.manager.create("human", "coast", "ppo", 91234)
        while not state["done"]: state = self.manager.advance(state["session_id"], 1)
        repeated = self.manager.advance(state["session_id"], 3)
        self.assertEqual(state, repeated)
        self.assertEqual(self.manager.store.list()["total_runs"], 1)
        replay = self.manager.store.replay(state["session_id"])
        self.assertEqual(replay["frames"][-1], state)
        self.assertEqual(len(replay["frames"]), state["steps"] + 1)
        self.assertEqual(replay["frames"][0]["frame"]["time_s"], 0)
        self.assertEqual(replay["summary"]["score"], state["score"])
        self.manager.close(state["session_id"])
        self.assertEqual(self.manager.store.replay(state["session_id"])["summary"], state)

    def test_invalid_action_and_early_finish_do_not_advance(self):
        state = self.manager.create("duel", "coast", "ppo", 7)
        with self.assertRaises(ValueError): self.manager.advance(state["session_id"], 8)
        with self.assertRaises(ValueError): self.manager.finish_rival(state["session_id"])
        self.assertEqual(self.manager.get(state["session_id"]).player.steps, 0)

    def test_abandoned_run_not_a_completed_record(self):
        state = self.manager.create("human", "coast", "ppo", 7)
        self.manager.advance(state["session_id"], 3)
        self.manager.close(state["session_id"])
        self.assertEqual(self.manager.store.list()["total_runs"], 0)
        with self.assertRaises(KeyError): self.manager.advance(state["session_id"])

    def test_same_seed_repeat_matches_initial_traffic(self):
        a = self.manager.create("human", "rush", "ppo", 42)
        b = self.manager.create("human", "rush", "ppo", 42)
        self.assertEqual(a["frame"], b["frame"])
        self.assertNotEqual(a["session_id"], b["session_id"])

    def test_safe_completion_wins_even_against_higher_crash_score(self):
        safe = {"done": True, "crashed": False, "completed": True, "qualified": False, "score": 500}
        crash = {"done": True, "crashed": True, "completed": False, "qualified": False, "score": 5000}
        self.assertEqual(duel_outcome(safe, crash), "win")
        self.assertEqual(duel_outcome(crash, safe), "loss")
        self.assertIsNone(duel_outcome(safe, {**crash, "done": False}))

    def test_practice_and_vehicle_are_persisted_without_setting_personal_best(self):
        short_track = {**track_by_id("coast"), "duration": 1, "target_m": 10}
        with patch("server.game.track_by_id", return_value=short_track):
            state = self.manager.create("human", "coast", "ppo", 2, vehicle="suv", practice=True)
        self.assertEqual(state["vehicle"], "suv")
        self.assertTrue(state["practice"])
        self.assertEqual(state["version"], GAME_VERSION)
        self.assertEqual(state["env_version"], ENV_VERSION)
        self.assertIsNone(state["ai_level"])
        while not state["done"]:
            state = self.manager.advance(state["session_id"])
        listing = self.manager.store.list()
        self.assertEqual(listing["total_runs"], 1)
        self.assertEqual(listing["best"], [])
        replay = self.manager.store.replay(state["session_id"])
        self.assertEqual(replay["summary"]["vehicle"], "suv")
        self.assertTrue(replay["summary"]["practice"])

    def test_finish_event_is_emitted_once_and_preserved_in_final_replay(self):
        short_track = {**track_by_id("coast"), "duration": 1, "target_m": 10}
        with patch("server.game.track_by_id", return_value=short_track):
            state = self.manager.create("duel", "coast", "ppo", 2)
        while not state["done"]:
            state = self.manager.advance(state["session_id"])
        finishes = [event for event in state["events"] if event["type"] == "finish"]
        self.assertEqual(len(finishes), 2)
        self.assertEqual({event["actor"] for event in finishes}, {"player", "rival"})
        for _ in range(3):
            self.assertEqual(self.manager.advance(state["session_id"])["events"], state["events"])
            self.assertEqual(self.manager.finish_rival(state["session_id"])["events"], state["events"])
        replay = self.manager.store.replay(state["session_id"])
        self.assertEqual(replay["summary"]["events"], state["events"])
        self.assertEqual(replay["frames"][-1]["events"], state["events"])
        self.assertEqual(self.manager.store.list()["total_runs"], 1)

    def test_duel_traffic_replenishment_preserves_matching_worlds(self):
        state = self.manager.create("duel", "coast", "ppo", 37)
        session = self.manager.get(state["session_id"])
        # Remove only distant traffic equally to exercise replenishment immediately.
        for runner in (session.player, session.rival):
            runner.env.road.vehicles = [runner.env.vehicle]
        for _ in range(20):
            state = self.manager.advance(state["session_id"], 1)
            self.assertEqual(state["frame"], state["rival"]["frame"])
        self.assertTrue(session.player.env.spawn_events)
        self.assertEqual(session.player.env.spawn_events, session.rival.env.spawn_events)

    def test_concurrent_step_requests_keep_both_worlds_and_clock_in_sync(self):
        state = self.manager.create("duel", "coast", "ppo", 2)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(self.manager.advance, state["session_id"], 1) for _ in range(8)]
            snapshots = [future.result() for future in futures]
        self.assertEqual(sorted(snapshot["steps"] for snapshot in snapshots), list(range(1, 9)))
        for snapshot in snapshots:
            self.assertEqual(snapshot["frame"], snapshot["rival"]["frame"])
            self.assertAlmostEqual(snapshot["frame"]["time_s"], snapshot["steps"] / 5)
        session = self.manager.get(state["session_id"])
        self.assertEqual(len(session.frames), 9)

    def test_old_schema_records_migrate_and_replay_without_polluting_v2_best(self):
        state = self.manager.create("human", "coast", "ppo", 2)
        old = copy.deepcopy(state)
        old.update(session_id="legacy-record", score=99999, stars=3)
        old.pop("version")
        old.pop("practice")
        path = Path(self.folder.name) / "legacy.sqlite"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, created TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), track TEXT, mode TEXT, score INTEGER, stars INTEGER, summary TEXT, replay BLOB)")
            db.execute("INSERT INTO runs(id,track,mode,score,stars,summary,replay) VALUES(?,?,?,?,?,?,?)",
                       (old["session_id"], "coast", "human", old["score"], old["stars"], json.dumps(old), zlib.compress(json.dumps([old]).encode())))
        migrated = RecordStore(path)
        current = {**state, "session_id": "current-record", "score": 400, "stars": 1}
        migrated.save(current, [current])
        self.assertEqual(migrated.list()["best"], [{"track": "coast", "score": 400, "stars": 1}])
        self.assertEqual(migrated.list()["total_runs"], 2)
        self.assertEqual(migrated.replay("legacy-record"), {"summary": old, "frames": [old]})


if __name__ == "__main__": unittest.main()
