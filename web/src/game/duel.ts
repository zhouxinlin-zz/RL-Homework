import type { GameSession, Runner } from "./types";

export const safeFinish = (runner: Runner) =>
  runner.completed ?? (runner.done && !runner.crashed);
export const reachedGoal = (runner: Runner, target: number) =>
  runner.qualified ?? (safeFinish(runner) && runner.distance_m >= target);

// Match the server's safety → distance goal → score ordering for historical records.
export function duelOutcome(
  session: GameSession,
): "win" | "loss" | "draw" | null {
  if (!session.done || !session.rival?.done) return null;
  if (session.outcome) return session.outcome;
  const rank = (runner: Runner) => [
    Number(safeFinish(runner)),
    Number(reachedGoal(runner, session.track.target_m)),
    runner.score,
  ];
  const player = rank(session),
    rival = rank(session.rival);
  for (let i = 0; i < player.length; i++) {
    if (player[i] !== rival[i]) return player[i] > rival[i] ? "win" : "loss";
  }
  return "draw";
}

export function seriesScore(rounds: GameSession[]) {
  return rounds.reduce(
    (score, round) => {
      const outcome = duelOutcome(round);
      if (outcome === "win") score.player++;
      if (outcome === "loss") score.rival++;
      if (outcome === "draw") score.draws++;
      return score;
    },
    { player: 0, rival: 0, draws: 0 },
  );
}

export function duelHighlights(session: GameSession) {
  const events = session.events ?? [];
  const pick = (actor: "player" | "rival") =>
    events.find(
      (event) => event.actor === actor && event.type === "collision",
    ) ??
    events.find((event) => event.actor === actor && event.type === "danger") ??
    events.find((event) => event.actor === actor && event.type === "overtake");
  return [pick("player"), pick("rival")]
    .filter((event): event is NonNullable<typeof event> => !!event)
    .sort((a, b) => a.time_s - b.time_s);
}
