"""Behavioral checks for the shared v2 training/game simulation."""
import unittest

import numpy as np
from highway_env.vehicle.behavior import IDMVehicle

from rl_course.driving_env import CurriculumTraffic, make_driving_env, road_risk_v2
from rl_course.serialization import frame


class DrivingEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.env = make_driving_env()

    def tearDown(self):
        self.env.close()

    def test_reset_and_ongoing_traffic_are_reproducible(self):
        other = make_driving_env()
        try:
            a, _ = self.env.reset(seed=137)
            b, _ = other.reset(seed=137)
            np.testing.assert_array_equal(a, b)
            for action in [1, 3, 0, 1, 1, 2, 4, 1] * 12:
                ra, rb = self.env.step(action), other.step(action)
                np.testing.assert_array_equal(ra[0], rb[0])
                self.assertEqual(ra[1:], rb[1:])
                self.assertEqual(frame(self.env, 0, action, 0), frame(other, 0, action, 0))
                if ra[2] or ra[3]:
                    break
        finally:
            other.close()

    def test_replenishment_is_outside_playable_view_and_ids_are_stable(self):
        self.env.reset(seed=37)
        retained = self.env.road.vehicles[1]
        expected_id = retained.traffic_id
        self.env.road.vehicles = [self.env.vehicle, retained]
        self.env.step(1)
        self.assertTrue(self.env.spawn_events)
        for event in self.env.spawn_events:
            dx = event["relative_x"]
            self.assertTrue(dx >= 180 or dx <= -125)
        ids = [v["id"] for v in frame(self.env, 1, 1, 0)["vehicles"]]
        self.assertIn(expected_id, ids)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(frame(self.env, 1, 1, 0)["ego_id"], 0)

    def test_observation_reports_rear_car_and_closing_speed(self):
        self.env.reset(seed=12)
        ego = self.env.vehicle
        rear = IDMVehicle(self.env.road, [ego.position[0] - 24, 4], speed=30)
        rear.traffic_id, rear.kind = 999, "sedan"
        self.env.road.vehicles = [ego, rear]
        observation = self.env.observation_type.observe()
        self.assertEqual(observation.shape, (30,))
        self.assertEqual(observation[19], 1)
        self.assertGreater(observation[18], 0)
        self.assertLess(observation[17], 1)
        self.assertEqual(observation[16], 0)

    def test_initial_headway_and_finite_rewards(self):
        for seed in range(20):
            obs, _ = self.env.reset(seed=seed)
            risk = road_risk_v2(self.env)
            self.assertFalse(risk["danger"])
            if risk["ttc_s"] is not None:
                self.assertGreaterEqual(risk["ttc_s"], 2.9)
            for action in [1, 3, 0, 1, 2, 4] * 4:
                obs, reward, terminated, truncated, _ = self.env.step(action)
                self.assertTrue(self.env.observation_space.contains(obs))
                self.assertTrue(np.isfinite(reward))
                if terminated or truncated:
                    break

    def test_passing_same_vehicle_twice_cannot_farm_overtakes(self):
        self.env.reset(seed=4)
        ego, other = self.env.vehicle, self.env.road.vehicles[1]
        self.env.road.vehicles = [ego, other]
        self.env._eligible_ids.add(other.traffic_id)
        other.position[:] = [ego.position[0] - 30, 0]
        self.env.step(1)
        self.assertEqual(self.env.overtaken_count, 1)
        other.position[:] = [ego.position[0] + 40, 0]
        self.env.step(1)
        other.position[:] = [ego.position[0] - 30, 0]
        self.env.step(1)
        self.assertEqual(self.env.overtaken_count, 1)
        self.assertEqual(self.env._new_overtakes, 0)

    def test_duration_completion_and_invalid_action(self):
        env = make_driving_env(duration=1)
        try:
            env.reset(seed=2)
            for _ in range(5):
                _, _, terminated, truncated, info = env.step(1)
            self.assertFalse(terminated)
            self.assertTrue(truncated)
            self.assertTrue(info["completed"])
            with self.assertRaises(ValueError):
                env.step(9)
        finally:
            env.close()

    def test_curriculum_can_be_seeded_and_sets_traffic(self):
        env = CurriculumTraffic(seed=7)
        try:
            env.set_progress(1)
            obs, info = env.reset(seed=70)
            obs2, info2 = env.reset(seed=70)
            np.testing.assert_array_equal(obs, obs2)
            self.assertEqual(info["scenario"], info2["scenario"])
            self.assertEqual(info["env_version"], "2.0")
        finally:
            env.close()

    def test_offroad_termination_is_not_completion(self):
        self.env.reset(seed=2)
        self.env.vehicle.position[1] = 20
        _, _, terminated, _, info = self.env.step(1)
        self.assertTrue(terminated)
        self.assertFalse(info["completed"])

    def test_side_warning_detects_fast_rear_car_and_road_edge_is_false(self):
        self.env.reset(seed=12)
        ego = self.env.vehicle
        rear = IDMVehicle(self.env.road, [ego.position[0] - 18, 0], speed=30)
        rear.traffic_id, rear.kind = 999, "sedan"
        self.env.road.vehicles = [ego, rear]
        risk = road_risk_v2(self.env)
        self.assertTrue(risk["left"])
        self.assertFalse(risk["right"])
        ego.position[1] = 0
        self.assertFalse(road_risk_v2(self.env)["left"])


if __name__ == "__main__":
    unittest.main()
