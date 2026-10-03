import type { WorldFrame } from "../live/types";

/** Project received physical positions without inventing or extrapolating traffic. */
export function nearbyTraffic(frame: WorldFrame) {
  const ego = frame.vehicles.find((vehicle) => vehicle.id === frame.ego_id);
  if (!ego) return [];
  return frame.vehicles
    .filter(
      (vehicle) =>
        vehicle.x - ego.x >= -80 &&
        vehicle.x - ego.x <= 120 &&
        vehicle.y >= -2 &&
        vehicle.y <= 10,
    )
    .map((vehicle) => ({
      id: vehicle.id,
      ego: vehicle.id === ego.id,
      x: ((vehicle.y / 4 + 0.5) / 3) * 100,
      y: ((120 - (vehicle.x - ego.x)) / 200) * 180,
      length: Math.max(4, (vehicle.length / 200) * 180),
      width: Math.max(6, vehicle.width * 3),
      distance: vehicle.x - ego.x,
      speed: vehicle.speed * 3.6,
      relativeSpeed: vehicle.speed - ego.speed,
      crashed: vehicle.crashed,
    }));
}
