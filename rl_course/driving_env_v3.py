"""Scenario-based traffic for the driving challenge.

Version 3 keeps the v2 action and observation spaces so the deployed v2 policy
can be measured on the new roads before any additional training. Traffic is
generated as repeatable *formations*, not by independent lane density alone.
Every formation presents a slow lead vehicle and a different passing gap.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from highway_env.vehicle.behavior import IDMVehicle

from rl_course.driving_env import DrivingEnv, VEHICLE_KINDS, road_risk_v2

ENV_VERSION = "3.1"
SCENARIOS = ("convoy", "weave", "pressure")


@dataclass(frozen=True)
class FormationCar:
    lane: int
    offset: float
    speed: float
    kind: str
    lane_change: bool = False


# Offsets are relative to a formation anchor, initially about 65 m ahead.
# Each opening has at least one viable response: slow down, then use a side gap.
FORMATIONS: dict[str, tuple[tuple[FormationCar, ...], ...]] = {
    "convoy": (
        (FormationCar(1, 0, 16, "truck"), FormationCar(0, 24, 18, "van"),
         FormationCar(2, 21, 25, "sedan"), FormationCar(2, -108, 28, "hatch")),
        (FormationCar(1, 0, 17, "van"), FormationCar(0, 17, 16, "truck"),
         FormationCar(2, 33, 27, "suv"), FormationCar(0, -99, 28, "sedan")),
    ),
    "weave": (
        (FormationCar(1, 0, 18, "van"), FormationCar(0, 10, 26, "sedan"),
         FormationCar(2, 23, 19, "suv"), FormationCar(0, -103, 30, "hatch")),
        (FormationCar(1, 0, 19, "suv"), FormationCar(0, 23, 18, "truck"),
         FormationCar(2, 9, 27, "hatch"), FormationCar(2, -101, 30, "sedan")),
    ),
    "pressure": (
        (FormationCar(1, 0, 16, "truck"), FormationCar(0, 15, 21, "suv"),
         FormationCar(2, 17, 22, "van"), FormationCar(0, -101, 29, "hatch"),
         FormationCar(2, -107, 29, "sedan")),
        (FormationCar(1, 0, 17, "van"), FormationCar(0, 17, 21, "suv"),
         FormationCar(2, 14, 20, "truck"), FormationCar(0, -105, 29, "sedan"),
         FormationCar(2, -111, 28, "hatch")),
    ),
}
SPACING = {"convoy": 198., "weave": 190., "pressure": 180.}


class ChallengeEnv(DrivingEnv):
    @classmethod
    def default_config(cls):
        return {**super().default_config(), "scenario": "convoy"}

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
        self.unsafe_lane_requests = 0
        self._unsafe_lane_request = False
        self.spawn_events: list[dict] = []
        self.formation_events: list[dict] = []
        self._start_x = 1000.
        self._previous_x = self._start_x
        ego = self.action_type.vehicle_class(self.road, [self._start_x, 4.], speed=24)
        ego.LENGTH, ego.WIDTH = VEHICLE_KINDS["sedan"]
        ego.kind, ego.traffic_id = "sedan", 0
        self.controlled_vehicles = [ego]
        self.road.vehicles = [ego]
        self._next_formation = 0
        self._next_anchor = self._start_x + 68 + float(self.np_random.uniform(-6, 6))
        self._maintain_traffic()

    def _add_car(self, car: FormationCar, anchor: float, formation: int) -> bool:
        x = anchor + car.offset + float(self.np_random.uniform(-3.0, 3.0))
        speed = car.speed + float(self.np_random.uniform(-1.2, 1.2))
        length, width = VEHICLE_KINDS[car.kind]
        for other in self.road.vehicles:
            if abs(float(other.position[1]) - car.lane * 4.) < 2.4:
                clearance = abs(float(other.position[0]) - x) - (other.LENGTH + length) / 2
                if clearance < 13 + speed * .55:
                    return False
        vehicle = IDMVehicle(self.road, [x, car.lane * 4.], speed=speed,
                             target_speed=speed, enable_lane_change=car.lane_change)
        vehicle.LENGTH, vehicle.WIDTH = length, width
        vehicle.kind, vehicle.traffic_id = car.kind, self.next_vehicle_id
        vehicle.formation_id = formation
        vehicle.TIME_WANTED = 1.2
        vehicle.POLITENESS = .35
        vehicle.check_collisions = False
        self.next_vehicle_id += 1
        self.road.vehicles.append(vehicle)
        if x > self.vehicle.position[0] + length + 5:
            self._eligible_ids.add(vehicle.traffic_id)
        self.spawn_events.append({"time_s": float(self.time), "id": vehicle.traffic_id,
                                  "relative_x": x - float(self.vehicle.position[0]),
                                  "formation": formation})
        return True

    def _maintain_traffic(self):
        ego_x = float(self.vehicle.position[0])
        self.road.vehicles = [v for v in self.road.vehicles
                              if v is self.vehicle or -190 <= float(v.position[0]) - ego_x <= 360]
        scenario = self.config["scenario"]
        while self._next_anchor < ego_x + 300:
            index = self._next_formation
            pattern = FORMATIONS[scenario][index % len(FORMATIONS[scenario])]
            placed = sum(self._add_car(car, self._next_anchor, index) for car in pattern)
            self.formation_events.append({"index": index, "anchor_x": self._next_anchor,
                                          "placed": placed, "planned": len(pattern)})
            self._next_formation += 1
            self._next_anchor += SPACING[scenario] + float(self.np_random.uniform(-8, 8))

    def step(self, action):
        ego = self.vehicle
        lane = int(np.clip(round(float(ego.position[1]) / 4), 0, 2))
        settled = abs(float(ego.position[1]) / 4 - lane) < .1 and ego.target_lane_index[2] == lane
        risk = road_risk_v2(self) if settled and action in (0, 2) else None
        self._unsafe_lane_request = bool(risk and ((action == 0 and risk["left"])
                                                   or (action == 2 and risk["right"])))
        self.unsafe_lane_requests += int(self._unsafe_lane_request)
        return super().step(action)

    def _reward(self, action):
        reward = super()._reward(action)
        if self.config["reward_mode"] == "shaped" and self._unsafe_lane_request:
            reward -= 2.0
        if self.vehicle.crashed or not self.vehicle.on_road:
            reward -= 18.0  # Total terminal penalty: -30, including the v2 base.
        return reward

    def _info(self, obs, action=None):
        return {**super()._info(obs, action), "env_version": ENV_VERSION,
                "formation_count": len(self.formation_events),
                "unsafe_lane_requests": self.unsafe_lane_requests}


def make_challenge_env(scenario="convoy", duration=45, reward_mode="shaped") -> ChallengeEnv:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown challenge scenario: {scenario}")
    if reward_mode not in ("shaped", "base"):
        raise ValueError(f"Unknown reward mode: {reward_mode}")
    if not 1 <= duration <= 300:
        raise ValueError("Duration must be between 1 and 300 seconds")
    return ChallengeEnv(config={"scenario": scenario, "duration": duration, "reward_mode": reward_mode})
