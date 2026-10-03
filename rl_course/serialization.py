"""Serialize HighwayEnv state for both saved replays and live sessions."""

from __future__ import annotations

from typing import Any


def vehicle_state(vehicle: Any, vehicle_id: int) -> dict[str, float | int | bool | str]:
    return {
        "id": int(getattr(vehicle, "traffic_id", vehicle_id)),
        "x": float(vehicle.position[0]),
        "y": float(vehicle.position[1]),
        "heading": float(vehicle.heading),
        "speed": float(vehicle.speed),
        "length": float(vehicle.LENGTH),
        "width": float(vehicle.WIDTH),
        "crashed": bool(vehicle.crashed),
        "kind": str(getattr(vehicle, "kind", "sedan")),
    }


def frame(env: Any, step: int, action: int | None, reward: float) -> dict[str, Any]:
    world = env.unwrapped
    vehicles = world.road.vehicles
    ego_index = next(index for index, vehicle in enumerate(vehicles) if vehicle is world.vehicle)
    result = {
        "step": step,
        "time_s": float(world.time),
        "action": action,
        "reward": reward,
        "ego_id": int(getattr(world.vehicle, "traffic_id", ego_index)),
        "vehicles": [vehicle_state(vehicle, index) for index, vehicle in enumerate(vehicles)],
    }
    if hasattr(world, "overtaken_count"):
        version = "3.1" if type(world).__module__ == "rl_course.driving_env_v3" else "2.0"
        result.update({"env_version": version, "overtaken_count": world.overtaken_count,
                       "completed": world.completed, "target_speed": float(world.vehicle.target_speed),
                       "target_lane": int(world.vehicle.target_lane_index[2])})
    return result
