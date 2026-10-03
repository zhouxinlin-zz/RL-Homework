import type { GameSession } from "./types";

export const frameTime = (frame: GameSession) =>
  Math.max(frame.frame.time_s, frame.rival?.frame.time_s ?? 0);

export type ReplayMarker = {
  index: number;
  time: number;
  label: string;
  kind: "overtake" | "collision" | "finish";
};
export function replayMarkers(frames: GameSession[]): ReplayMarker[] {
  const result: ReplayMarker[] = [];
  for (let i = 1; i < frames.length; i++) {
    const previous = frames[i - 1],
      current = frames[i];
    if (current.crashed && !previous.crashed)
      result.push({
        index: i,
        time: frameTime(current),
        label: "碰撞",
        kind: "collision",
      });
    else if (current.overtakes > previous.overtakes)
      result.push({
        index: i,
        time: frameTime(current),
        label: `第 ${current.overtakes} 次超车`,
        kind: "overtake",
      });
    if (current.rival?.crashed && !previous.rival?.crashed)
      result.push({
        index: i,
        time: frameTime(current),
        label: "AI 碰撞",
        kind: "collision",
      });
  }
  if (frames.length > 1)
    result.push({
      index: frames.length - 1,
      time: frameTime(frames.at(-1)!),
      label: "行程结束",
      kind: "finish",
    });
  return result;
}

export function frameBefore(frames: GameSession[], time: number): number {
  let low = 0,
    high = frames.length - 1;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (frameTime(frames[middle]) <= time) low = middle;
    else high = middle - 1;
  }
  return low;
}
