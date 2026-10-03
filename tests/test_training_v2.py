"""Short checks of evaluation behavior; these tests never train a model."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gymnasium as gym
import numpy as np

from rl_course.driving_env import make_driving_env
from rl_course.evaluate_v2 import compile_report
from rl_course.game_rules import ENV_VERSION, performance, track_by_id
from rl_course.v2_metrics import CONDITIONS, TEST_SEED_START, episode, rule_action
from server.game import Runner


class AlternatingPolicy:
    def __init__(self):
        self.calls = 0

    def predict(self, observation, deterministic=True):
        action = 2 if self.calls % 2 == 0 else 0
        self.calls += 1
        return action, None


class OffroadStart(gym.Wrapper):
    def reset(self, **kwargs):
        _, info = self.env.reset(**kwargs)
        self.unwrapped.vehicle.position[1] = 20
        return self.unwrapped.observation_type.observe(), info


class EvaluationBehaviorTests(unittest.TestCase):
    def test_rule_baseline_responds_to_rear_traffic_using_observation_only(self):
        obs = np.zeros(30, dtype=np.float32)
        obs[:6] = [.8, .8, 0, 0, 0, 1]
        lanes = obs[6:].reshape(3, 8)
        lanes[:] = [1, 0, 0, 1, 0, 0, 0, 0]
        lanes[1, :3] = [20 / 120, -5 / 15, 1]
        lanes[0] = [80 / 120, 0, 1, 30 / 80, 3 / 15, 1, 0, 0]
        lanes[2, :3] = [10 / 120, 0, 1]
        self.assertEqual(rule_action(obs.copy()), 0)
        lanes[0, 3:6] = [5 / 80, 8 / 15, 1]
        self.assertEqual(rule_action(obs.copy()), 4)

    def test_delayed_inference_sends_idle_and_matches_live_runner(self):
        evaluation_env = make_driving_env("light", duration=1.6)
        game_env = make_driving_env("light", duration=1.6)
        eval_policy, live_policy = AlternatingPolicy(), AlternatingPolicy()
        try:
            result = episode(evaluation_env, model=eval_policy, seed=402,
                             inference_stride=3, collect_trace=True)
            observation, _ = game_env.reset(seed=402)
            runner = Runner(env=game_env, obs=observation, model=live_policy, inference_stride=3,
                            start_x=float(game_env.vehicle.position[0]), previous_lane=1)
            actions = []
            while not runner.done:
                runner.advance(4)
                actions.append(runner.action)
            expected = [2, 1, 1, 0, 1, 1, 2, 1]
            self.assertEqual(actions, expected)
            self.assertEqual([row["action"] for row in result["trace"]], expected)
            self.assertEqual((eval_policy.calls, live_policy.calls), (3, 3))
            np.testing.assert_allclose(evaluation_env.vehicle.position, game_env.vehicle.position)
            self.assertAlmostEqual(result["time_s"], game_env.time)
        finally:
            evaluation_env.close()
            game_env.close()

    def test_crawl_baseline_reaches_lowest_target_speed(self):
        env = make_driving_env("light", duration=5)
        try:
            result = episode(env, baseline="crawl", seed=402, collect_trace=True)
            self.assertEqual(env.vehicle.target_speed, 12)
            self.assertLess(env.vehicle.speed, 12.1)
            self.assertGreater(result["actions"][4], 2)
            self.assertEqual(result["trace"][-1]["action"], 1)
        finally:
            env.close()

    def test_offroad_failure_is_not_a_collision_and_uses_game_failure_score(self):
        env = OffroadStart(make_driving_env("light", duration=30))
        try:
            result = episode(env, baseline="cruise", seed=402)
            self.assertTrue(result["failed"])
            self.assertFalse(result["completed"])
            self.assertFalse(result["crashed"])
            expected = performance(track_by_id("coast"), done=True, crashed=True,
                                   distance=result["distance_m"], overtakes=result["overtakes"],
                                   danger_seconds=result["danger_seconds"])
            self.assertEqual(result["score"], expected["score"])
            self.assertEqual(result["stars"], 0)
        finally:
            env.close()


class EvaluationProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.output = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def shard(self, split="test", seed_start=TEST_SEED_START):
        rows = [{"scenario": scenario, "duration": duration, "seed": seed_start,
                 "crashed": False, "completed": True, "quality": 2.5, "distance_m": 700,
                 "speed_kmh": 80, "overtakes": 1, "lane_changes": 1,
                 "danger_seconds": 0, "return": 15} for scenario, duration in CONDITIONS]
        return {"metadata": {"id": "candidate", "env_version": ENV_VERSION, "split": split,
                             "seed_start": seed_start, "episodes_per_condition": 1,
                             "environment_source_sha256": "a" * 64, "metrics_source_sha256": "b" * 64},
                "episodes": rows}

    def save(self, shard):
        (self.output / "candidate.json").write_text(json.dumps(shard), encoding="utf-8")

    def test_complete_test_shard_compiles_but_development_cannot_be_relabelled(self):
        self.save(self.shard())
        with patch("rl_course.evaluate_v2.make_figures"):
            report = compile_report(self.output, ["candidate"], "test")
        self.assertEqual(report["total_episodes"], 5)
        self.assertEqual(report["split"], "test")
        for split, seed in (("development", TEST_SEED_START), ("test", 31100)):
            with self.subTest(split=split, seed=seed):
                self.save(self.shard(split, seed))
                with self.assertRaises(ValueError):
                    compile_report(self.output, ["candidate"], "test")

    def test_missing_or_duplicate_roads_are_rejected(self):
        for duplicate in (False, True):
            shard = self.shard()
            if duplicate:
                shard["episodes"][1] = copy.deepcopy(shard["episodes"][0])
            else:
                shard["episodes"].pop()
            self.save(shard)
            with self.assertRaises(ValueError):
                compile_report(self.output, ["candidate"], "test")


if __name__ == "__main__":
    unittest.main()
