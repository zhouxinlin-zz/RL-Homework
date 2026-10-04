import { expect, it } from "vitest";
import { frameBefore, frameTime, replayMarkers } from "../src/game/replay";
import type { GameSession } from "../src/game/types";

it("does not skip a frame when a one-second seek meets floating point timestamps", () => {
  const frames = [19.8, 20.00000000000004, 20.2, 20.99999999999997].map(
    (time) => ({ frame: { time_s: time } }) as GameSession,
  );
  const forward = frameBefore(frames, frameTime(frames[1]) + 1);
  expect(forward).toBe(3);
  expect(frameBefore(frames, frameTime(frames[forward]) - 1)).toBe(1);
  expect(frameBefore(frames, 19.99)).toBe(0);
});

it("uses both clocks and locates real overtake/collision events without duplicates", () => {
  const sample = (
    time: number,
    overtakes = 0,
    crashed = false,
    rivalTime = time,
  ) =>
    ({
      frame: { time_s: time },
      overtakes,
      crashed,
      rival: { frame: { time_s: rivalTime }, crashed: false },
    }) as GameSession;
  const frames = [
    sample(0),
    sample(0.2),
    sample(0.4, 1),
    sample(0.6, 1, true),
    sample(0.6, 1, true, 0.8),
    sample(0.6, 1, true, 1),
  ];
  const markers = replayMarkers(frames);
  expect(markers.filter((marker) => marker.kind === "collision")).toHaveLength(
    1,
  );
  expect(markers.filter((marker) => marker.kind === "overtake")).toHaveLength(
    1,
  );
  expect(frameTime(frames.at(-1)!)).toBe(1);
  expect(frameBefore(frames, 0.75)).toBe(3);
  expect(frameBefore(frames, -1)).toBe(0);
});
