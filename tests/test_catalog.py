"""Deployment integrity and public API validation without external HTTP clients."""
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server import app as api
from server import catalog
from server.game import GameManager
from server.records import RecordStore
from rl_course.game_rules import ENV_VERSION


async def request(method, path, payload=None):
    """Exercise FastAPI's actual ASGI validation/response stack in process."""
    body = json.dumps(payload).encode() if payload is not None else b""
    messages = []
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
             "root_path": "", "headers": [(b"content-type", b"application/json")],
             "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 8765)}
    sent = False
    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}
    async def send(message):
        messages.append(message)
    await api.app(scope, receive, send)
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    response = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, json.loads(response) if response else None


class CountingPolicy:
    def __init__(self):
        self.calls = 0

    def predict(self, observation, deterministic=True):
        self.calls += 1
        return 1, None


class TrainingSummaryTests(unittest.TestCase):
    def test_public_training_summary_uses_only_the_frozen_report(self):
        summary = catalog.challenge_training_catalog()
        self.assertIsNotNone(summary)
        self.assertEqual(summary["levels"]["standard"]["overall"]["episodes"], 300)
        manifest = catalog.challenge_deployment()
        expert = summary["levels"]["expert"]
        selected = manifest["models"][expert["policy"]]
        self.assertEqual(expert["algorithm"], selected["algorithm"].upper())
        self.assertEqual(expert["checkpoint_sha256"], selected["sha256"])
        self.assertEqual(expert["checkpoint_steps"], selected["steps"])
        self.assertEqual(expert["training_steps"], selected["training_steps"])
        self.assertEqual(expert["run_id"], selected["run_id"])
        report = json.loads((catalog.ROOT / manifest["evaluation"]["report"]).read_text(encoding="utf-8"))
        self.assertEqual(summary["levels"]["standard"]["routes"], report["models"]["v3_standard"]["by_scenario"])
        expected = manifest.get("refinement", {}).get("expert_vs_rule", report["paired_game_outcomes"]["expert_vs_rule"]["paired"]["all"])
        self.assertEqual(summary["expert_vs_rule"], expected)

        altered = catalog.challenge_deployment()
        altered["evaluation"] = {**altered["evaluation"], "report_sha256": "0" * 64}
        with patch.object(catalog, "challenge_deployment", return_value=altered):
            self.assertIsNone(catalog.challenge_training_catalog())


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name).resolve() / "project"
        self.root.mkdir()
        self.checkpoint = self.root / "policy.zip"
        self.checkpoint.write_bytes(b"test checkpoint - loader is patched")
        self.manifest_path = self.root / "deployment.json"
        self.manifest = {"env_version": ENV_VERSION, "models": {"ppo": {
            "path": "policy.zip", "algorithm": "ppo", "steps": 12345,
            "sha256": hashlib.sha256(self.checkpoint.read_bytes()).hexdigest()}},
            "levels": {"standard": {"model": "ppo", "inference_stride": 2}}}
        self.write_manifest()
        self.root_patch = patch.object(catalog, "ROOT", self.root)
        self.path_patch = patch.object(catalog, "DEPLOYMENT", self.manifest_path)
        self.root_patch.start()
        self.path_patch.start()
        self.manager = GameManager(RecordStore(self.root / "records.sqlite"))
        self.game_patch = patch.object(api, "game", self.manager)
        self.game_patch.start()

    def tearDown(self):
        for run_id in list(self.manager.sessions):
            self.manager.close(run_id)
        self.game_patch.stop()
        self.path_patch.stop()
        self.root_patch.stop()
        self.folder.cleanup()

    def write_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def call(self, method, path, payload=None):
        return asyncio.run(request(method, path, payload))

    def test_game_request_rejects_invalid_fields_before_allocating_session(self):
        invalid = [{"mode": "race"}, {"track_id": "missing"}, {"policy": "unknown"},
                   {"seed": -1}, {"seed": 2 ** 32}, {"ai_level": "impossible"},
                   {"vehicle": "truck"}]
        for payload in invalid:
            with self.subTest(payload=payload):
                status, _ = self.call("POST", "/api/game/sessions", payload)
                self.assertEqual(status, 422)
        self.assertEqual(self.manager.sessions, {})

    def test_human_creation_accepts_seed_bounds_and_validates_actions(self):
        for seed in (0, 2 ** 32 - 1):
            status, state = self.call("POST", "/api/game/sessions", {"mode": "human", "seed": seed,
                "vehicle": "touring", "practice": True})
            self.assertEqual(status, 200)
            self.assertEqual(state["seed"], seed)
            self.assertEqual(state["vehicle"], "touring")
            self.assertTrue(state["practice"])
            status, _ = self.call("POST", f"/api/game/sessions/{state['session_id']}/step", {"action": 5})
            self.assertEqual(status, 422)
            self.assertEqual(self.manager.get(state["session_id"]).player.steps, 0)
        status, _ = self.call("POST", "/api/game/sessions", {"mode": "duel", "practice": True})
        self.assertEqual(status, 400)

    def test_challenge_api_routes_to_new_environment_and_rejects_old_policy(self):
        status, state = self.call("POST", "/api/game/sessions",
                                  {"mode": "human", "track_id": "convoy", "seed": 91})
        self.assertEqual(status, 200)
        self.assertEqual(state["env_version"], "3.1")
        self.assertEqual(state["frame"]["env_version"], "3.1")
        self.assertEqual(state["track"]["scenario"], "convoy")
        status, _ = self.call("POST", "/api/game/sessions",
                              {"mode": "duel", "track_id": "convoy", "policy": "ppo",
                               "ai_level": None, "seed": 91})
        self.assertEqual(status, 400)

    def test_ai_level_resolves_deployed_model_and_inference_frequency(self):
        policy = CountingPolicy()
        with patch("server.game.PPO.load", return_value=policy) as loader:
            status, state = self.call("POST", "/api/game/sessions", {"mode": "ai", "policy": "dqn", "ai_level": "standard", "seed": 2})
            self.assertEqual(status, 200)
            self.assertEqual(state["policy"], "ppo")
            self.assertEqual(state["ai_level"], "standard")
            self.assertEqual(state["model_steps"], 12345)
            loader.assert_called_once()
            for _ in range(4):
                status, _ = self.call("POST", f"/api/game/sessions/{state['session_id']}/step", {"action": 4})
                self.assertEqual(status, 200)
            self.assertEqual(policy.calls, 2)

    def test_model_hash_mismatch_is_rejected_before_deserialization(self):
        self.manifest["models"]["ppo"]["sha256"] = "0" * 64
        self.write_manifest()
        with patch("server.game.PPO.load") as loader:
            status, _ = self.call("POST", "/api/game/sessions", {"mode": "ai", "ai_level": "standard"})
            self.assertEqual(status, 400)
            loader.assert_not_called()
        self.assertEqual(self.manager.sessions, {})

    def test_changed_manifest_hash_invalidates_previously_cached_model(self):
        with patch("server.game.PPO.load", return_value=CountingPolicy()) as loader:
            self.manager.load_model("ppo")
            original_stamp = self.checkpoint.stat().st_mtime_ns
            self.manifest["models"]["ppo"]["sha256"] = "0" * 64
            self.write_manifest()
            self.assertEqual(self.checkpoint.stat().st_mtime_ns, original_stamp)
            with self.assertRaises(ValueError):
                self.manager.load_model("ppo")
            loader.assert_called_once()

    def test_replay_keeps_its_original_model_when_deployment_changes(self):
        from rl_course.game_rules import track_by_id
        short_track = {**track_by_id("coast"), "duration": 1, "target_m": 10}
        old_hash = self.manifest["models"]["ppo"]["sha256"]
        with patch("server.game.PPO.load", side_effect=lambda *a, **k: CountingPolicy()), patch("server.game.track_by_id", return_value=short_track):
            first = self.manager.create("ai", ai_level="standard", seed=2)
            self.checkpoint.write_bytes(b"another independently loaded checkpoint")
            new_hash = hashlib.sha256(self.checkpoint.read_bytes()).hexdigest()
            self.manifest["models"]["ppo"].update(sha256=new_hash, steps=54321, seed=47)
            self.write_manifest()
            second = self.manager.create("ai", ai_level="standard", seed=2)
            while not first["done"]:
                first = self.manager.advance(first["session_id"])
        self.assertEqual(first["model_info"]["sha256"], old_hash)
        self.assertEqual(first["model_info"]["steps"], 12345)
        self.assertEqual(first["model_info"]["inference_stride"], 2)
        self.assertEqual(second["model_info"]["sha256"], new_hash)
        self.assertEqual(second["model_info"]["seed"], 47)
        replay = self.manager.store.replay(first["session_id"])
        self.assertEqual(replay["summary"]["model_info"], first["model_info"])
        self.assertTrue(all(frame["model_info"]["sha256"] == old_hash for frame in replay["frames"]))

    def test_wrong_environment_version_disables_models_and_ai_levels(self):
        self.manifest["env_version"] = "0.3"
        self.write_manifest()
        self.assertTrue(all(not item["available"] for item in catalog.driver_catalog()))
        self.assertTrue(all(not item["available"] for item in catalog.ai_catalog()))
        status, _ = self.call("POST", "/api/game/sessions", {"mode": "duel"})
        self.assertEqual(status, 503)
        self.assertEqual(self.manager.sessions, {})

    def test_manifest_cannot_load_a_model_outside_project_root(self):
        # The file exists; rejection must come from containment rather than absence.
        (self.root.parent / "outside-policy.zip").write_bytes(b"outside model")
        self.manifest["models"]["ppo"]["path"] = "../outside-policy.zip"
        self.write_manifest()
        with self.assertRaises(FileNotFoundError):
            catalog.model_spec("ppo")


if __name__ == "__main__":
    unittest.main()
