import { useEffect, useRef } from "react";
import { Application, Container, Graphics } from "pixi.js";
import type { DrivingSession, Vehicle } from "./types";

const WIDTH = 1200;
const HEIGHT = 480;
const ROAD_TOP = 70;
const ROAD_BOTTOM = 410;
const LANE_HEIGHT = (ROAD_BOTTOM - ROAD_TOP) / 3;
const PPM = 7.4;

const palette = [0xdce5df, 0x9db7bf, 0xddb891, 0xb6bdcf, 0xcdaea3, 0x8fb9a9];
const blend = (a: number, b: number, fraction: number) =>
  a + (b - a) * fraction;

function drawCarGraphic(ego: boolean, id: number): Graphics {
  const color = ego ? 0x42c4d4 : palette[id % palette.length];
  const graphic = new Graphics();
  graphic.roundRect(-31, -13, 62, 26, 9).fill(color);
  graphic.roundRect(-9, -10, 27, 20, 5).fill(0x183a4a);
  graphic.rect(-21, -10, 4, 20).fill(0xe7f6f2);
  graphic.rect(27, -9, 4, 6).fill(0xfff1bf);
  graphic.rect(27, 3, 4, 6).fill(0xfff1bf);
  graphic.rect(-31, -9, 4, 6).fill(0xdf6470);
  graphic.rect(-31, 3, 4, 6).fill(0xdf6470);
  graphic.roundRect(-31, -13, 62, 26, 9).stroke({
    color: ego ? 0xf2ffff : 0xffffff,
    alpha: ego ? 0.85 : 0.32,
    width: ego ? 2 : 1,
  });
  if (ego)
    graphic.circle(0, 0, 34).stroke({ color: 0x73e1e7, alpha: 0.55, width: 2 });
  return graphic;
}

function drawRoad(graphic: Graphics, cameraX: number) {
  graphic.clear();
  graphic.rect(0, 0, WIDTH, HEIGHT).fill(0x173b44);
  const firstTree = Math.floor((cameraX - 80) / 7) * 7;
  for (let worldX = firstTree; worldX < cameraX + 180; worldX += 7) {
    const x = WIDTH * 0.32 + (worldX - cameraX) * PPM;
    const variation = Math.sin(worldX * 17.318) * 3127.44;
    const radius = 11 + Math.abs(variation % 11);
    const color = Math.floor(worldX / 7) % 3 ? 0x2b6261 : 0x39716d;
    graphic.circle(x, 33 + (variation % 8), radius).fill(color);
    graphic
      .circle(x + 15, HEIGHT - 25 + (variation % 7), radius * 0.9)
      .fill(color);
  }
  graphic
    .rect(0, ROAD_TOP - 5, WIDTH, ROAD_BOTTOM - ROAD_TOP + 10)
    .fill(0x6b7775);
  graphic.rect(0, ROAD_TOP, WIDTH, ROAD_BOTTOM - ROAD_TOP).fill(0x2d414b);
  for (let lane = 0; lane < 3; lane++) {
    graphic
      .rect(0, ROAD_TOP + lane * LANE_HEIGHT + 11, WIDTH, LANE_HEIGHT - 22)
      .fill(lane % 2 ? 0x31454e : 0x344750);
  }
  graphic.rect(0, ROAD_TOP + 9, WIDTH, 3).fill(0xd4dfd9);
  graphic.rect(0, ROAD_BOTTOM - 12, WIDTH, 3).fill(0xd4dfd9);
  graphic.rect(0, ROAD_TOP + 16, WIDTH, 2).fill(0xead7a6);
  graphic.rect(0, ROAD_BOTTOM - 19, WIDTH, 2).fill(0xead7a6);
  const offset = (((cameraX * PPM) % 112) + 112) % 112;
  for (let lane = 1; lane < 3; lane++) {
    for (let x = -112 - offset; x < WIDTH + 112; x += 112) {
      graphic
        .roundRect(x, ROAD_TOP + lane * LANE_HEIGHT - 2, 64, 4, 2)
        .fill({ color: 0xe9f1ec, alpha: 0.78 });
    }
  }
  // Thin guardrail highlights give the road depth without using the native box renderer.
  graphic.rect(0, ROAD_TOP - 7, WIDTH, 2).fill(0xb1c8c7);
  graphic.rect(0, ROAD_BOTTOM + 5, WIDTH, 2).fill(0xb1c8c7);
}

function interpolateVehicles(
  previous: DrivingSession | null,
  current: DrivingSession,
  fraction: number,
): Vehicle[] {
  if (!previous || previous.session_id !== current.session_id)
    return current.frame.vehicles;
  const old = new Map(
    previous.frame.vehicles.map((vehicle) => [vehicle.id, vehicle]),
  );
  return current.frame.vehicles.map((vehicle) => {
    const before = old.get(vehicle.id);
    return before
      ? {
          ...vehicle,
          x: blend(before.x, vehicle.x, fraction),
          y: blend(before.y, vehicle.y, fraction),
          heading: blend(before.heading, vehicle.heading, fraction),
          speed: blend(before.speed, vehicle.speed, fraction),
        }
      : vehicle;
  });
}

export default function LiveRoad({
  session,
}: {
  session: DrivingSession | null;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const currentRef = useRef<DrivingSession | null>(session);
  const previousRef = useRef<DrivingSession | null>(null);
  const changedAtRef = useRef(0);

  useEffect(() => {
    previousRef.current =
      currentRef.current?.session_id === session?.session_id
        ? currentRef.current
        : null;
    currentRef.current = session;
    changedAtRef.current = performance.now();
  }, [session]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const app = new Application();
    let disposed = false;
    let initialized = false;
    const cars = new Map<number, Graphics>();
    const road = new Graphics();
    const vehicleLayer = new Container();

    async function setup() {
      await app.init({
        width: WIDTH,
        height: HEIGHT,
        backgroundColor: 0x173b44,
        antialias: true,
        autoDensity: true,
        resolution: Math.min(window.devicePixelRatio || 1, 2),
      });
      initialized = true;
      if (disposed) {
        app.destroy(true);
        return;
      }
      app.canvas.style.width = "100%";
      app.canvas.style.height = "100%";
      host!.appendChild(app.canvas);
      app.stage.addChild(road, vehicleLayer);
      app.ticker.add(() => {
        const current = currentRef.current;
        if (!current) {
          drawRoad(road, 0);
          return;
        }
        const fraction = Math.min(
          1,
          (performance.now() - changedAtRef.current) / 650,
        );
        const vehicles = interpolateVehicles(
          previousRef.current,
          current,
          fraction,
        );
        const ego = vehicles.find(
          (vehicle) => vehicle.id === current.frame.ego_id,
        );
        if (!ego) return;
        drawRoad(road, ego.x);
        const visible = new Set<number>();
        for (const vehicle of vehicles) {
          const screenX = WIDTH * 0.32 + (vehicle.x - ego.x) * PPM;
          if (screenX < -65 || screenX > WIDTH + 65) continue;
          visible.add(vehicle.id);
          let sprite = cars.get(vehicle.id);
          if (!sprite) {
            sprite = drawCarGraphic(
              vehicle.id === current.frame.ego_id,
              vehicle.id,
            );
            cars.set(vehicle.id, sprite);
            vehicleLayer.addChild(sprite);
          }
          sprite.x = screenX;
          sprite.y = ROAD_TOP + (vehicle.y / 4 + 0.5) * LANE_HEIGHT;
          sprite.rotation = vehicle.heading;
          sprite.alpha = vehicle.crashed ? 0.55 : 1;
        }
        for (const [id, sprite] of cars) {
          if (!visible.has(id)) {
            vehicleLayer.removeChild(sprite);
            sprite.destroy();
            cars.delete(id);
          }
        }
      });
    }
    void setup();
    return () => {
      disposed = true;
      if (initialized) app.destroy(true, { children: true });
    };
  }, []);

  return (
    <div
      className="live-road"
      ref={hostRef}
      role="img"
      aria-label="实时高速公路驾驶画面"
    />
  );
}
