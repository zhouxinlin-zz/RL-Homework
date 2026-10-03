import { expect, it } from "vitest";
import { frameBefore, frameTime, replayMarkers } from "../src/game/replay";
import type { GameSession } from "../src/game/types";

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
