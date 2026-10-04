"""Guard model promotion, unchanged physics, and provenance of teaching replays."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import torch

from rl_course.driving_env_v3 import make_challenge_env
from rl_course.driving_env_v3 import ChallengeEnv
from rl_course.release_refinement import promotion_gate, validate_report
from rl_course.train_refinement import RefinementRoad
from rl_course.train_safety_refinement import following_risk, AnchoredPPO, SafetyRoad, make_policy
from rl_course.v2_metrics import sha256, write_json
from server.refinement import checked_file, evidence
from server.runtime import source_revision


class RefinementTests(unittest.TestCase):
    def test_new_model_release_changes_launcher_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = source_revision(root)
            path = root / "artifacts/experiments_v3/iteration_6/release.json"
            write_json(path, {"model": "first"})
            first = source_revision(root)
            write_json(path, {"model": "second"})
            self.assertNotEqual(before, first)
            self.assertNotEqual(first, source_revision(root))

    def test_loading_reference_does_not_replace_new_training_seed(self):
        from stable_baselines3 import PPO
        from stable_baselines3.common.vec_env import DummyVecEnv
        torch.set_num_threads(1)
        env = DummyVecEnv([lambda: SafetyRoad(191)])
        try:
            make_policy(env, 191, .5)
            actual = torch.random.get_rng_state().clone()
            PPO("MlpPolicy", env, seed=191, policy_kwargs={"net_arch": [128, 128]})
            self.assertTrue(torch.equal(actual, torch.random.get_rng_state()))
        finally:
            env.close()

    def test_following_retention_uses_visible_current_and_target_lane_gaps(self):
        observations = torch.zeros((5, 30))
        observations[:, 2:4] = 0  # middle lane
        observations[:, [6, 14, 22]] = 1  # no nearby vehicles
        observations[0, 14:17] = torch.tensor([.1, 0, 1])
        observations[1, 14:17] = torch.tensor([.4, -1, 1])  # 48m / 15m/s <3.5s
        observations[2, 6:9] = torch.tensor([.05, 0, 1])  # unrelated adjacent lane
        observations[3, 3] = -1
        observations[3, 6:9] = torch.tensor([.05, 0, 1])  # target lane counts
        observations[4, 14:17] = torch.tensor([.1, 0, 0])  # absent vehicle does not
        self.assertEqual(following_risk(observations).tolist(), [True, True, False, True, False])

    def test_reference_is_frozen_and_game_can_load_without_training_subclass(self):
        from stable_baselines3 import PPO
        from stable_baselines3.common.vec_env import DummyVecEnv
        torch.set_num_threads(1)
        env = DummyVecEnv([lambda: SafetyRoad(19)])
        try:
            options = dict(n_steps=16, batch_size=8, n_epochs=1, seed=19, device="cpu")
            model = AnchoredPPO("MlpPolicy", env, **options)
            model.reference_policy = PPO("MlpPolicy", env, **options).policy
            model.reference_policy.requires_grad_(False)
            saved = [p.detach().clone() for p in model.reference_policy.parameters()]
            model.learn(16)
            self.assertTrue(all(torch.equal(a, b) for a, b in zip(saved, model.reference_policy.parameters())))
            observation = env.reset()
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "weights.zip"
                model.save(path)
                loaded = PPO.load(path, device="cpu")
                self.assertFalse(hasattr(loaded, "reference_policy"))
                np.testing.assert_array_equal(model.predict(observation, deterministic=True)[0],
                    loaded.predict(observation, deterministic=True)[0])
        finally:
            env.close()

    def test_extra_reward_only_rewards_safe_progress_and_qualified_finish(self):
        env = RefinementRoad(19)
        env.reset(seed=100)
        try:
            env.vehicle.position[0] = env._start_x + env.training_track["target_m"]
            env._previous_x = env.vehicle.position[0] - 4
            env.time = env.config["duration"]
            base = ChallengeEnv._reward(env, 1)
            self.assertAlmostEqual(env._reward(1) - base, 6 + .015 * 4)
            env.vehicle.crashed = True
            base = ChallengeEnv._reward(env, 1)
            self.assertAlmostEqual(env._reward(1) - base, -30)
        finally:
            env.close()

    def test_training_reward_does_not_modify_driving_trajectories(self):
        for seed in range(6):
            trained = SafetyRoad(seed)
            a, _ = trained.reset(seed=12000 + seed)
            track = trained.training_track
            game = make_challenge_env(track["scenario"], track["duration"])
            try:
                b, _ = game.reset(seed=12000 + seed)
                np.testing.assert_array_equal(a, b)
                for action in [1, 3, 4, 0, 1, 2] * 10:
                    a, _, ta, xa, _ = trained.step(action)
                    b, _, tb, xb, _ = game.step(action)
                    np.testing.assert_array_equal(a, b)
                    self.assertEqual((ta, xa), (tb, xb))
                    if ta or xa:
                        break
            finally:
                trained.close()
                game.close()

    def test_more_score_cannot_hide_collisions_or_route_regression(self):
        route = {"crashes": 0, "qualification_rate": .7, "mean_score": 1000}
        before = {"overall": route, "summary": {key: dict(route) for key in ("convoy", "weave", "pressure")}}
        after = copy.deepcopy(before)
        after["overall"] = {**route, "qualification_rate": .8, "mean_score": 1100}
        self.assertTrue(promotion_gate(before, after))
        after["summary"]["weave"]["crashes"] = 1
        self.assertFalse(promotion_gate(before, after))
        after["summary"]["weave"]["crashes"] = 0
        after["summary"]["weave"]["qualification_rate"] = .6
        self.assertFalse(promotion_gate(before, after))
        self.assertFalse(promotion_gate(before, before))

    def test_evaluation_rejects_duplicate_roads_and_changed_durations(self):
        rows = [{"scenario": name, "seed": seed, "duration": duration}
                for name, duration in [("convoy", 35), ("weave", 45), ("pressure", 55)] for seed in range(10, 12)]
        report = {"episodes": rows, "model_sha256": "frozen", "env_version": "3.1", "duration": "game_routes"}
        validate_report(report, {"sha256": "frozen"}, 10, 2)
        rows[0]["duration"] = 45
        with self.assertRaises(ValueError):
            validate_report(report, {"sha256": "frozen"}, 10, 2)
        rows[0] = dict(rows[1])
        with self.assertRaises(ValueError):
            validate_report(report, {"sha256": "frozen"}, 10, 2)

    def test_model_and_report_must_agree_before_deployment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "policy.zip"
            model.write_bytes(b"model")
            spec = {"path": "policy.zip", "sha256": sha256(model)}
            report_path = root / "report.json"
            report = {"stage": "final", "env_version": "3.1", "promoted": True, "candidate_spec": spec}
            write_json(report_path, report)
            release_path = root / "artifacts/experiments_v3/iteration_5/release.json"
            release = {"stage": "final", "env_version": "3.1", "promoted": True, "model": spec,
                       "report": "report.json", "report_sha256": sha256(report_path)}
            write_json(release_path, release)
            self.assertEqual(evidence(root)[1], report)
            release["model"] = {**spec, "sha256": "0" * 64}
            write_json(release_path, release)
            with self.assertRaises(ValueError):
                evidence(root)
            write_json(release_path, {**release, "model": spec})
            model.write_bytes(b"changed model")
            with self.assertRaises(ValueError):
                evidence(root)
            with self.assertRaises(ValueError):
                checked_file(root, "../outside.json", "0" * 64)


if __name__ == "__main__":
    unittest.main()
