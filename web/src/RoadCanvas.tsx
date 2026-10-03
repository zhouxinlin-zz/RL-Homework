import { useEffect, useRef } from "react";
import type { Frame, Replay, Vehicle } from "./App";

const W = 1200,
  H = 430,
  TOP = 58,
  BOTTOM = 372;
const mix = (a: number, b: number, t: number) => a + (b - a) * t;

function car(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  angle: number,
  color: string,
  ego: boolean,
  crashed: boolean,
) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  if (ego) {
    ctx.shadowColor = crashed ? "#ff7567" : "#51d8dd";
    ctx.shadowBlur = 22;
  }
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.roundRect(-29, -12, 58, 24, 8);
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.fillStyle = "#173543";
  ctx.beginPath();
  ctx.roundRect(-7, -9, 23, 18, 4);
  ctx.fill();
  ctx.fillStyle = "rgba(255,255,255,.58)";
  ctx.fillRect(-19, -10, 3, 20);
  ctx.fillStyle = "#fff4c9";
  ctx.fillRect(25, -8, 4, 5);
  ctx.fillRect(25, 3, 4, 5);
  ctx.fillStyle = "#e76369";
  ctx.fillRect(-29, -8, 3, 5);
  ctx.fillRect(-29, 3, 3, 5);
  ctx.strokeStyle = ego ? "#efffff" : "rgba(255,255,255,.3)";
  ctx.lineWidth = ego ? 2 : 1;
  ctx.beginPath();
  ctx.roundRect(-29, -12, 58, 24, 8);
  ctx.stroke();
  if (crashed) {
    ctx.strokeStyle = "#ff7567";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(0, 0, 27, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
}

function interpolate(a: Frame, b: Frame, t: number): Vehicle[] {
  const next = new Map(b.vehicles.map((v) => [v.id, v]));
  return a.vehicles.map((v) => {
    const n = next.get(v.id);
    return n
      ? {
          ...v,
          x: mix(v.x, n.x, t),
          y: mix(v.y, n.y, t),
          heading: mix(v.heading, n.heading, t),
          speed: mix(v.speed, n.speed, t),
          crashed: t > 0.8 ? n.crashed : v.crashed,
        }
      : v;
  });
}

function draw(ctx: CanvasRenderingContext2D, replay: Replay, playhead: number) {
  const index = Math.min(Math.floor(playhead), replay.frames.length - 1);
  const frame = replay.frames[index],
    next = replay.frames[Math.min(index + 1, replay.frames.length - 1)];
  const vehicles = interpolate(frame, next, playhead - index);
  const ego = vehicles.find((v) => v.id === frame.ego_id);
  if (!ego) return;
  const x = (value: number) => W * 0.31 + (value - ego.x) * 7.2;
  const laneHeight = (BOTTOM - TOP) / 3;
  const y = (value: number) => TOP + (value / 4 + 0.5) * laneHeight;

  const grass = ctx.createLinearGradient(0, 0, 0, H);
  grass.addColorStop(0, "#1a3a42");
  grass.addColorStop(1, "#102c38");
  ctx.fillStyle = grass;
  ctx.fillRect(0, 0, W, H);
  for (
    let worldX = Math.floor((ego.x - 70) / 6) * 6;
    worldX < ego.x + 170;
    worldX += 6
  ) {
    const px = x(worldX),
      v = Math.sin(worldX * 12.9898) * 43758.5453,
      r = 8 + Math.abs(v % 11);
    ctx.fillStyle = Math.floor(worldX / 6) % 3 ? "#2a5255" : "#376467";
    ctx.beginPath();
    ctx.arc(px, 32 + (v % 12), r, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(px + 14, H - 20 + (v % 12), r, 0, Math.PI * 2);
    ctx.fill();
  }
  const asphalt = ctx.createLinearGradient(0, TOP, 0, BOTTOM);
  asphalt.addColorStop(0, "#273942");
  asphalt.addColorStop(0.5, "#35454e");
  asphalt.addColorStop(1, "#263941");
  ctx.fillStyle = asphalt;
  ctx.fillRect(0, TOP, W, BOTTOM - TOP);
  ctx.fillStyle = "#dce2d7";
  ctx.fillRect(0, TOP + 7, W, 3);
  ctx.fillRect(0, BOTTOM - 10, W, 3);
  ctx.fillStyle = "#e4d4a4";
  ctx.fillRect(0, TOP + 14, W, 2);
  ctx.fillRect(0, BOTTOM - 17, W, 2);
  const offset = (((ego.x * 7.2) % 105) + 105) % 105;
  ctx.fillStyle = "rgba(240,245,241,.78)";
  for (let lane = 1; lane < 3; lane++)
    for (let px = -105 - offset; px < W + 105; px += 105)
      ctx.fillRect(px, TOP + lane * laneHeight - 2, 60, 4);
  const colors = [
    "#d8e4dc",
    "#acc0c3",
    "#e0bb91",
    "#a9bccd",
    "#cab3ab",
    "#91b4a8",
  ];
  vehicles
    .filter((v) => v.id !== frame.ego_id)
    .forEach((v) => {
      const px = x(v.x);
      if (px > -50 && px < W + 50)
        car(
          ctx,
          px,
          y(v.y),
          v.heading,
          colors[v.id % colors.length],
          false,
          v.crashed,
        );
    });
  car(ctx, x(ego.x), y(ego.y), ego.heading, "#43bed0", true, ego.crashed);
  ctx.fillStyle = "rgba(11,34,44,.78)";
  ctx.beginPath();
  ctx.roundRect(22, H - 51, 187, 29, 7);
  ctx.fill();
  ctx.fillStyle = "#dbeaec";
  ctx.font = "600 12px sans-serif";
  ctx.fillText(`SEED ${replay.seed}  /  STEP ${frame.step}`, 35, H - 31);
}

export default function RoadCanvas({
  replay,
  playhead,
}: {
  replay: Replay;
  playhead: number;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (ctx) draw(ctx, replay, playhead);
  }, [replay, playhead]);
  return (
    <canvas
      ref={ref}
      width={W}
      height={H}
      className="road-canvas"
      role="img"
      aria-label="高速公路驾驶真实轨迹回放"
    />
  );
}
