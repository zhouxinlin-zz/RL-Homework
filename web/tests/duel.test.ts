import { expect, it } from "vitest";
import { duelHighlights, duelOutcome, seriesScore } from "../src/game/duel";
import type { GameSession } from "../src/game/types";

const run = (score: number, crashed: boolean, distance_m: number) => ({
  done: true,
  score,
  crashed,
  distance_m,
});
it("never ranks a high-scoring crash above safe completion or a missed goal above a reached goal", () => {
  const session = {
    ...run(2000, true, 1500),
    track: { target_m: 1000 },
    rival: run(1200, false, 900),
  } as GameSession;
  expect(duelOutcome(session)).toBe("loss");
  expect(
    duelOutcome({
      ...session,
      ...run(2000, false, 900),
      rival: run(1800, false, 1100),
    } as GameSession),
  ).toBe("loss");
  expect(duelOutcome({ ...session, done: false })).toBeNull();
});
it("uses the saved game verdict and counts tied stages without inventing a tie breaker", () => {
  const base = {
    ...run(2000, false, 1500),
    track: { target_m: 1000 },
    rival: run(2000, false, 1500),
  } as GameSession;
  expect(duelOutcome(base)).toBe("draw");
  expect(
    seriesScore([
      { ...base, outcome: "win" },
      { ...base, outcome: "loss" },
      base,
    ]),
  ).toEqual({ player: 1, rival: 1, draws: 1 });
});
it("picks actual critical events for both drivers and prefers a collision over earlier warnings", () => {
  const events: NonNullable<GameSession["events"]> = [
    { actor: "player", type: "danger", time_s: 10 },
    { actor: "rival", type: "overtake", time_s: 12 },
    { actor: "player", type: "collision", time_s: 20 },
  ];
  expect(
    duelHighlights({ events } as GameSession).map((event) => [
      event.actor,
      event.time_s,
    ]),
  ).toEqual([
    ["rival", 12],
    ["player", 20],
  ]);
  expect(duelHighlights({} as GameSession)).toEqual([]);
});
