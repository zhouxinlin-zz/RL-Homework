"""Player-versus-AI statistics must cover eligible history, not the visible page."""
from pathlib import Path
import tempfile
import unittest

from rl_course.game_rules import GAME_VERSION
from server.records import RecordStore


class DuelRecordTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = RecordStore(Path(self.folder.name) / "records.sqlite")
        self.next_id = 0

    def tearDown(self):
        self.folder.cleanup()

    def save(self, **changes):
        self.next_id += 1
        summary = {"session_id": f"run-{self.next_id}", "track": {"id": "coast"},
                   "mode": "duel", "version": GAME_VERSION, "practice": False,
                   "done": True, "score": 500, "stars": 1, "ai_level": "standard", "outcome": "win",
                   **changes}
        self.store.save(summary, [summary])
        return summary

    def test_aggregate_covers_all_records_independent_of_visible_page(self):
        self.save(ai_level="beginner", outcome="win")
        self.save(ai_level="beginner", outcome="loss")
        self.save(ai_level="expert", outcome="draw")
        self.save(ai_level=None, outcome="win")
        missing_level = self.save(ai_level="", outcome="loss")
        # Duplicate saves remain idempotent for both history and statistics.
        self.store.save(missing_level, [missing_level])
        listing = self.store.list(limit=1)
        self.assertEqual(len(listing["runs"]), 1)
        self.assertEqual(listing["total_runs"], 5)
        self.assertEqual(listing["duels"], {
            "played": 5, "wins": 2, "losses": 2, "draws": 1,
            "by_level": {
                "beginner": {"played": 2, "wins": 1, "losses": 1, "draws": 0},
                "expert": {"played": 1, "wins": 0, "losses": 0, "draws": 1},
                "custom": {"played": 2, "wins": 1, "losses": 1, "draws": 0},
            },
        })

    def test_old_practice_observer_and_invalid_results_are_excluded(self):
        self.save(version="0.3.0", score=9000, stars=3)
        self.save(practice=True, score=8000, stars=3)
        self.save(mode="ai", score=7000, stars=3)
        self.save(mode="human", score=650, stars=2)
        self.save(outcome=None, score=10)
        self.save(outcome="unfinished", score=20)
        self.save(ai_level="expert", outcome="loss", score=600)
        listing = self.store.list(limit=1)
        self.assertEqual(listing["duels"], {"played": 1, "wins": 0, "losses": 1, "draws": 0,
            "by_level": {"expert": {"played": 1, "wins": 0, "losses": 1, "draws": 0}}})
        self.assertEqual(listing["best"], [{"track": "coast", "score": 650, "stars": 2}])
        self.assertEqual(listing["total_runs"], 7)

    def test_unfinished_snapshot_with_outcome_does_not_count_as_played(self):
        # Imported or interrupted records may contain inconsistent legacy fields.
        self.save(done=False, outcome="win")
        self.assertEqual(self.store.list()["duels"]["played"], 0)

    def test_empty_history_has_zero_statistics(self):
        self.assertEqual(self.store.list()["duels"], {
            "played": 0, "wins": 0, "losses": 0, "draws": 0, "by_level": {}})


if __name__ == "__main__":
    unittest.main()
