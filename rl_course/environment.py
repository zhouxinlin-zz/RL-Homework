"""One shared environment definition for training and evaluation."""

from __future__ import annotations

import gymnasium as gym
import highway_env  # noqa: F401 - imports register HighwayEnv environments


SCENARIOS: dict[str, dict[str, float | int]] = {
    "light": {"vehicles_count": 12, "vehicles_density": 0.75},
    "normal": {"vehicles_count": 20, "vehicles_density": 1.0},
    "dense": {"vehicles_count": 35, "vehicles_density": 1.35},
}

BASE_CONFIG: dict[str, object] = {
    "lanes_count": 3,
    "duration": 30,
    "observation": {"type": "Kinematics", "vehicles_count": 5},
    "action": {"type": "DiscreteMetaAction"},
}


def make_env(scenario: str = "normal") -> gym.Env:
    """Create a HighwayEnv instance with a fixed observation/action interface."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario {scenario!r}; choose {list(SCENARIOS)}")
    config = {**BASE_CONFIG, **SCENARIOS[scenario]}
    return gym.make("highway-fast-v0", config=config)


def action_names(env: gym.Env) -> dict[int, str]:
    return {value: name for name, value in env.unwrapped.action_type.actions_indexes.items()}
