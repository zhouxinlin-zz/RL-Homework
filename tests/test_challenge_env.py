"""Scenario mechanics that the trained policy and the duel must both face."""
import unittest

import numpy as np
from highway_env.vehicle.behavior import IDMVehicle

from rl_course.driving_env import road_risk_v2
from rl_course.driving_env_v3 import SCENARIOS, make_challenge_env


def traffic_state(env):
    return sorted((v.traffic_id, v.kind, round(float(v.position[0]), 4),
                   round(float(v.position[1]), 4), round(float(v.speed), 4))
                  for v in env.road.vehicles if v is not env.vehicle)


class ChallengeEnvironmentTests(unittest.TestCase):
    def test_each_scenario_starts_with_an_observable_slow_vehicle_and_safe_gap(self):
        for scenario in SCENARIOS:
            env = make_challenge_env(scenario)
            try:
                for seed in range(30):
                    observation, info = env.reset(seed=seed)
                    self.assertEqual(observation.shape, (30,))
                    self.assertTrue(env.observation_space.contains(observation))
                    self.assertEqual(info["env_version"], "3.1")
                    self.assertFalse(road_risk_v2(env)["danger"])
                    front = [v for v in env.road.vehicles if v is not env.vehicle
                             and v.position[0] > env.vehicle.position[0]
                             and abs(v.position[1] - 4) < 1]
                    self.assertTrue(front)
                    self.assertLess(min(v.speed for v in front), env.vehicle.speed)
                    self.assertGreaterEqual(env.formation_events[0]["placed"], 4)
            finally:
                env.close()

    def test_seed_and_action_sequence_reproduce_all_formation_traffic(self):
        for scenario in SCENARIOS:
            a, b = make_challenge_env(scenario), make_challenge_env(scenario)
            try:
                np.testing.assert_array_equal(a.reset(seed=4701)[0], b.reset(seed=4701)[0])
                self.assertEqual(traffic_state(a), traffic_state(b))
                for action in [1, 3, 0, 1, 4, 2, 1] * 30:
                    left, right = a.step(action), b.step(action)
                    np.testing.assert_array_equal(left[0], right[0])
                    self.assertEqual(left[1:], right[1:])
                    self.assertEqual(traffic_state(a), traffic_state(b))
                    if left[2] or left[3]:
                        break
            finally:
                a.close()
                b.close()

    def test_scenario_patterns_are_distinct_and_keep_replenishing(self):
        signatures = []
        for scenario in SCENARIOS:
            env = make_challenge_env(scenario)
            try:
                env.reset(seed=41)
                initial = env.formation_events.copy()
                signatures.append(tuple((v.kind, round(float(v.position[1])))
                                        for v in env.road.vehicles[1:5]))
                for _ in range(150):
                    _, _, terminated, truncated, _ = env.step(1)
                    if terminated or truncated:
                        break
                self.assertGreater(len(env.formation_events), len(initial))
                self.assertEqual(len({v.traffic_id for v in env.road.vehicles}),
                                 len(env.road.vehicles))
                self.assertTrue(all(event["placed"] > 0 for event in env.formation_events))
            finally:
                env.close()
        self.assertEqual(len(set(signatures)), 3)

    def test_unsafe_lane_request_is_exposed_to_training_reward(self):
        env = make_challenge_env("convoy")
        try:
            env.reset(seed=12)
            ego = env.vehicle
            rear = IDMVehicle(env.road, [ego.position[0] - 18, 8], speed=30)
            rear.traffic_id, rear.kind = 9999, "sedan"
            env.road.vehicles.append(rear)
            self.assertTrue(road_risk_v2(env)["right"])
            _, reward, _, _, info = env.step(2)
            self.assertTrue(np.isfinite(reward))
            self.assertEqual(info["unsafe_lane_requests"], 1)
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
