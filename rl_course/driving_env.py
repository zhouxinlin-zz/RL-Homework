"""Version 2 highway simulation shared by the game, training and evaluation.

The agent controls its vehicle directly through five meta actions. No safety
controller changes its decisions. Background traffic uses HighwayEnv's IDM/MOBIL.
"""
from __future__ import annotations

import math
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces
from highway_env.envs.highway_env import HighwayEnvFast
from highway_env.envs.common.action import action_factory
from highway_env.envs.common.observation import ObservationType
from highway_env.road.road import Road, RoadNetwork
from highway_env.vehicle.behavior import IDMVehicle

ENV_VERSION = "2.0"
TARGET_SPEEDS = [12, 18, 24, 30]
TRAFFIC = {
    "light": {"spacing": 100., "speed": (19., 28.), "lane_change": .3, "headway": 1.6},
    "normal": {"spacing": 76., "speed": (17., 29.), "lane_change": .55, "headway": 1.4},
    "dense": {"spacing": 58., "speed": (15., 28.), "lane_change": .7, "headway": 1.25},
}
VEHICLE_KINDS = {
    "sedan": (4.7, 1.85), "hatch": (4.05, 1.78), "suv": (4.95, 2.0),
    "van": (5.8, 2.05), "truck": (8.0, 2.35),
}


class StraightTrafficRoad(Road):
    """Equivalent neighbour lookup specialized to this straight three-lane road."""
    def neighbour_vehicles(self, vehicle, lane_index=None):
        lane_index = lane_index or vehicle.lane_index
        center = lane_index[2] * 4.
        front = rear = None
        front_x, rear_x = float("inf"), -float("inf")
        x = vehicle.position[0]
        for other in self.vehicles:
            if other is vehicle or abs(other.position[1] - center) > 3.:
                continue
            ox = other.position[0]
            if x <= ox < front_x:
                front, front_x = other, ox
            elif rear_x < ox < x:
                rear, rear_x = other, ox
        return front, rear


def lane_neighbours(world, lane: int):
    """Account for vehicles straddling lanes during a lane change."""
    ego = world.vehicle
    front = rear = None
    front_x, rear_x = math.inf, -math.inf
    for other in world.road.vehicles:
        if other is ego or abs(float(other.position[1]) - lane * 4.) > 2.0 + other.WIDTH / 2:
            continue
        x = float(other.position[0])
        if ego.position[0] <= x < front_x:
            front, front_x = other, x
        elif rear_x < x < ego.position[0]:
            rear, rear_x = other, x
    return front, rear


def road_risk_v2(env: gym.Env) -> dict[str, Any]:
    world = env.unwrapped
    ego = world.vehicle
    lane = int(np.clip(round(float(ego.position[1]) / 4), 0, 2))
    def adjacent_occupied(candidate):
        if not 0 <= candidate <= 2:
            return False
        ahead, behind = lane_neighbours(world, candidate)
        if ahead is not None:
            gap = float(ahead.position[0] - ego.position[0] - (ego.LENGTH + ahead.LENGTH) / 2)
            closing = float(ego.speed - ahead.speed)
            if gap < max(10., ego.speed * .65) or (closing > .1 and gap / closing < 2.5):
                return True
        if behind is not None:
            gap = float(ego.position[0] - behind.position[0] - (ego.LENGTH + behind.LENGTH) / 2)
            closing = float(behind.speed - ego.speed)
            if gap < max(10., behind.speed * .45) or (closing > .1 and gap / closing < 2.5):
                return True
        return False

    sides = {"left": adjacent_occupied(lane - 1), "right": adjacent_occupied(lane + 1)}
    front, _ = lane_neighbours(world, lane)
    if front is None:
        return {"gap_m": None, "ttc_s": None, "danger": False, **sides}
    gap = max(0., float(front.position[0] - ego.position[0] - (ego.LENGTH + front.LENGTH) / 2))
    closing = float(ego.speed - front.speed)
    ttc = gap / closing if closing > .1 else None
    return {"gap_m": round(gap, 2), "ttc_s": round(ttc, 2) if ttc is not None else None,
            "danger": bool(gap < max(5., ego.speed * .35) or (ttc is not None and ttc < 2.)), **sides}


class LaneObservation(ObservationType):
    """30 bounded features: ego state plus front/back traffic in every lane."""
    def space(self):
        return spaces.Box(-1., 1., shape=(30,), dtype=np.float32)

    def observe(self):
        world = self.env
        if world.road is None:
            return np.zeros(30, dtype=np.float32)
        ego = world.vehicle
        values = [ego.speed / 30, ego.target_speed / 30, ego.position[1] / 4 - 1,
                  ego.target_lane_index[2] - 1, ego.heading / .5,
                  max(0., 1 - world.time / world.config["duration"])]
        for lane in range(3):
            front, rear = lane_neighbours(world, lane)
            fg = max(0., front.position[0] - ego.position[0] - (ego.LENGTH + front.LENGTH) / 2) if front else 120.
            rg = max(0., ego.position[0] - rear.position[0] - (ego.LENGTH + rear.LENGTH) / 2) if rear else 80.
            fp, rp = front is not None and fg <= 120, rear is not None and rg <= 80
            values.extend([min(fg / 120, 1), (front.speed - ego.speed) / 15 if fp else 0, float(fp),
                           min(rg / 80, 1), (rear.speed - ego.speed) / 15 if rp else 0, float(rp),
                           front.velocity[1] / 5 if fp else 0, rear.velocity[1] / 5 if rp else 0])
        return np.clip(values, -1, 1).astype(np.float32)


class DrivingEnv(HighwayEnvFast):
    @classmethod
    def default_config(cls):
        return {**super().default_config(), "simulation_frequency": 15, "policy_frequency": 5,
                "lanes_count": 3, "duration": 45, "scenario": "normal", "reward_mode": "shaped",
                "offroad_terminal": True, "action": {"type": "DiscreteMetaAction", "target_speeds": TARGET_SPEEDS}}

    def define_spaces(self):
        self.action_type = action_factory(self, self.config["action"])
        self.action_space = self.action_type.space()
        self.observation_type = LaneObservation(self)
        self.observation_space = self.observation_type.space()

    def _create_road(self):
        self.road = StraightTrafficRoad(network=RoadNetwork.straight_road_network(3, length=100000, speed_limit=32),
                                       np_random=self.np_random, record_history=False)

    def _create_vehicles(self):
        self.next_vehicle_id = 1
        self.overtaken_ids: set[int] = set()
        self._eligible_ids: set[int] = set()
        self.lane_changes = 0
        self.danger_seconds = 0.
        self._last_change_time = -100.
        self._last_change_direction = 0
        self._step_lane_cost = 0.
        self._new_overtakes = 0
        self.spawn_events: list[dict] = []
        self._start_x = 1000.
        self._previous_x = self._start_x
        ego = self.action_type.vehicle_class(self.road, [self._start_x, 4.], speed=24)
        ego.LENGTH, ego.WIDTH = VEHICLE_KINDS["sedan"]
        ego.kind, ego.traffic_id = "sedan", 0
        self.controlled_vehicles = [ego]
        self.road.vehicles = [ego]
        settings = TRAFFIC[self.config["scenario"]]
        spacing = settings["spacing"]
        for lane in range(3):
            offset = self.np_random.uniform(0., spacing * .75)
            x = self._start_x - 150 + offset
            while x < self._start_x + 240:
                # Every lane has a generous starting buffer, preventing unavoidable starts.
                if abs(x - self._start_x) >= 34:
                    self._spawn(lane, x, initial=True)
                x += spacing * self.np_random.uniform(.85, 1.15)

    @property
    def distance_m(self):
        return max(0., float(self.vehicle.position[0] - self._start_x))

    @property
    def overtaken_count(self):
        return len(self.overtaken_ids)

    @property
    def completed(self):
        return bool(self.time >= self.config["duration"] - 1e-7 and not self.vehicle.crashed and self.vehicle.on_road)

    def _spawn(self, lane, x, *, initial=False):
        settings = TRAFFIC[self.config["scenario"]]
        kind = str(self.np_random.choice(list(VEHICLE_KINDS), p=[.3, .23, .22, .15, .1]))
        speed = float(self.np_random.uniform(*settings["speed"]))
        if kind in ("van", "truck"):
            speed = max(15., speed - 2)
        # An initial front car must leave at least three seconds before contact.
        relative_x = float(x - self.vehicle.position[0])
        if initial and relative_x > 0 and relative_x < 60:
            speed = max(speed, 24 - (relative_x - 10) / 3)
        length, width = VEHICLE_KINDS[kind]
        for other in self.road.vehicles:
            if abs(other.position[1] - lane * 4.) < 3.1:
                gap = abs(other.position[0] - x) - (length + other.LENGTH) / 2
                if gap < 16 + speed * .65:
                    return False
        vehicle = IDMVehicle(self.road, [x, lane * 4.], speed=speed, target_speed=speed,
                             enable_lane_change=bool(self.np_random.random() < settings["lane_change"]))
        vehicle.LENGTH, vehicle.WIDTH = length, width
        vehicle.kind, vehicle.traffic_id = kind, self.next_vehicle_id
        self.next_vehicle_id += 1
        vehicle.TIME_WANTED = settings["headway"] + float(self.np_random.uniform(-.15, .15))
        vehicle.POLITENESS = .35
        vehicle.LANE_CHANGE_DELAY = float(self.np_random.uniform(1.5, 3.5))
        vehicle.LANE_CHANGE_MIN_ACC_GAIN = .35
        vehicle.timer = float(self.np_random.uniform(0, vehicle.LANE_CHANGE_DELAY))
        vehicle.check_collisions = False
        vehicle.randomize_behavior()
        self.road.vehicles.append(vehicle)
        if relative_x > length + 5:
            self._eligible_ids.add(vehicle.traffic_id)
        if not initial:
            self.spawn_events.append({"time_s": self.time, "id": vehicle.traffic_id, "relative_x": relative_x})
        return True

    def _maintain_traffic(self):
        ego_x = float(self.vehicle.position[0])
        self.road.vehicles = [v for v in self.road.vehicles if v is self.vehicle or -190 <= v.position[0] - ego_x <= 300]
        spacing = TRAFFIC[self.config["scenario"]]["spacing"]
        for lane in range(3):
            positions = [float(v.position[0] - ego_x) for v in self.road.vehicles if v is not self.vehicle and abs(v.position[1] - lane * 4.) < 2.1]
            front = max(positions, default=0.)
            rear = min(positions, default=0.)
            if front < 230 - spacing:
                self._spawn(lane, ego_x + max(180., front + spacing))
            if rear > -150 + spacing:
                self._spawn(lane, ego_x - max(125., -rear + spacing))

    def step(self, action):
        if not self.action_space.contains(action):
            raise ValueError(f"Invalid driving action: {action}")
        self._previous_x = float(self.vehicle.position[0])
        self._previous_target_lane = self.vehicle.target_lane_index[2]
        self._step_lane_cost = 0.
        self._new_overtakes = 0
        return super().step(action)

    def _simulate(self, action=None):
        super()._simulate(action)
        lane_delta = self.vehicle.target_lane_index[2] - self._previous_target_lane
        if lane_delta:
            direction = int(np.sign(lane_delta))
            self.lane_changes += 1
            self._step_lane_cost = .02
            if direction != self._last_change_direction and self.time - self._last_change_time < 2:
                self._step_lane_cost += .12
            self._last_change_time, self._last_change_direction = self.time, direction
        if not self.vehicle.crashed:
            for vehicle in self.road.vehicles:
                if vehicle is self.vehicle:
                    continue
                vid = vehicle.traffic_id
                clearance = (vehicle.LENGTH + self.vehicle.LENGTH) / 2 + 4
                if (vid in self._eligible_ids and vid not in self.overtaken_ids
                        and self.vehicle.position[0] - vehicle.position[0] > clearance):
                    self.overtaken_ids.add(vid)
                    self._new_overtakes += 1
        self._maintain_traffic()
        if road_risk_v2(self)["danger"]:
            self.danger_seconds += 1 / self.config["policy_frequency"]

    def _reward(self, action):
        progress = max(0., float(self.vehicle.position[0] - self._previous_x))
        reward = .025 * progress
        if self.config["reward_mode"] == "shaped":
            reward += .4 * self._new_overtakes - self._step_lane_cost
            risk = road_risk_v2(self)
            if risk["danger"]:
                reward -= .12
        if self.vehicle.crashed or not self.vehicle.on_road:
            reward -= 12.
        elif self.completed:
            reward += 3.
        return float(reward)

    def _is_truncated(self):
        return self.time >= self.config["duration"] - 1e-7

    def _info(self, obs, action=None):
        return {"speed": float(self.vehicle.speed), "crashed": bool(self.vehicle.crashed), "action": action,
                "env_version": ENV_VERSION, "scenario": self.config["scenario"], "distance_m": self.distance_m,
                "overtaken_count": self.overtaken_count, "lane_changes": self.lane_changes,
                "danger_seconds": self.danger_seconds, "completed": self.completed}


def make_driving_env(scenario="normal", duration=45, reward_mode="shaped") -> DrivingEnv:
    if scenario not in TRAFFIC:
        raise ValueError(f"Unknown scenario: {scenario}")
    if reward_mode not in ("shaped", "base"):
        raise ValueError(f"Unknown reward mode: {reward_mode}")
    if not 1 <= duration <= 300:
        raise ValueError("Duration must be between 1 and 300 seconds")
    return DrivingEnv(config={"scenario": scenario, "duration": duration, "reward_mode": reward_mode})


class CurriculumTraffic(gym.Wrapper):
    """Episode-level traffic curriculum; progression is explicit and reproducible."""
    def __init__(self, seed=42, duration=45, reward_mode="shaped"):
        super().__init__(make_driving_env("light", duration, reward_mode))
        self.scenario_rng = np.random.default_rng(seed)
        self.progress = 0.

    def set_progress(self, progress):
        self.progress = float(np.clip(progress, 0., 1.))

    def reset(self, *, seed=None, options=None):
        if seed is not None:
            self.scenario_rng = np.random.default_rng(seed)
        if self.progress < .15:
            probabilities = [.8, .2, 0.]
        elif self.progress < .4:
            probabilities = [.35, .5, .15]
        else:
            probabilities = [.2, .4, .4]
        scenario = str(self.scenario_rng.choice(list(TRAFFIC), p=probabilities))
        self.unwrapped.configure({"scenario": scenario})
        return self.env.reset(seed=seed, options=options)
