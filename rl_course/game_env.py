"""Archived v1 environment used to reproduce the original academy experiments.

Current gameplay and new training use :mod:`rl_course.driving_env`. The functions
here deliberately keep the v1 physics, reward and observation definitions intact.
"""
from __future__ import annotations

import gymnasium as gym
import numpy as np

from rl_course.environment import BASE_CONFIG, SCENARIOS

GAME_CONFIG = {**BASE_CONFIG, "simulation_frequency": 10, "policy_frequency": 5}
POLICY_KEYS = ("dqn", "ppo", "a2c", "ppo_mixed")


def make_game_env(scenario: str = "normal", duration: int = 30) -> gym.Env:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")
    return gym.make("highway-fast-v0", config={**GAME_CONFIG, **SCENARIOS[scenario], "duration": duration})


class MixedTraffic(gym.Wrapper):
    """Change only traffic density/count at each episode; keep reward and actions fixed."""
    def __init__(self, seed: int):
        super().__init__(make_game_env())
        self.scenario_rng = np.random.default_rng(seed)

    def reset(self, *, seed=None, options=None):
        if seed is not None:
            self.scenario_rng = np.random.default_rng(seed)
        scenario = str(self.scenario_rng.choice(list(SCENARIOS)))
        self.unwrapped.configure(SCENARIOS[scenario])
        observation, info = self.env.reset(seed=seed, options=options)
        return observation, {**info, "scenario": scenario}


def road_risk(env: gym.Env) -> dict:
    world = env.unwrapped
    ego = world.vehicle
    front = [v for v in world.road.vehicles if v is not ego and abs(v.position[1] - ego.position[1]) < 2.2 and v.position[0] > ego.position[0]]
    nearest = min(front, key=lambda v: v.position[0], default=None)
    if nearest is None:
        return {"gap_m": None, "ttc_s": None, "danger": False}
    gap = max(0.0, float(nearest.position[0] - ego.position[0] - (ego.LENGTH + nearest.LENGTH) / 2))
    closing = float(ego.speed - nearest.speed)
    ttc = gap / closing if closing > 0.1 else None
    return {"gap_m": round(gap, 2), "ttc_s": round(ttc, 2) if ttc is not None else None, "danger": gap < 8 or (ttc is not None and ttc < 2)}
