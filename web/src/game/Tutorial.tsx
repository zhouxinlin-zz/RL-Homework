import { useState } from "react";
import type { GameSession } from "./types";

export default function Tutorial({
  session,
  dismiss,
}: {
  session: GameSession;
  dismiss: () => void;
}) {
  const [lesson, setLesson] = useState({
    frame: -1,
    adjusted: false,
    safeSince: 0,
    safeDone: false,
  });
  // Retain accomplishments when the next authoritative simulator frame arrives.
  // The frame guard ensures this update settles before React commits the lesson UI.
  if (lesson.frame !== session.frame.step) {
    const safeSince = session.risk.danger
      ? session.frame.time_s
      : lesson.safeSince;
    setLesson({
      frame: session.frame.step,
      adjusted:
        lesson.adjusted ||
        session.frame.action === 3 ||
        session.frame.action === 4,
      safeSince,
      safeDone:
        lesson.safeDone ||
        (!session.risk.danger &&
          session.frame.time_s - safeSince >= 8 &&
          session.frame.time_s >= 10),
    });
  }
  const goals = [
    {
      done: lesson.adjusted,
      title: "调整车速",
      detail: "按 ↑ 或 ↓ 调整一档目标车速，留意左下方速度表。",
      key: "↑ ↓",
    },
    {
      done: session.lane_changes > 0,
      title: "完成一次换道",
      detail: "观察旁边的车辆，按 ← 或 → 换一条车道。按住不会连续换道。",
      key: "← →",
    },
    {
      done: lesson.safeDone,
      title: "留出安全距离",
      detail: "连续 8 秒保持安全车距。拥挤时先减速，再寻找换道空间。",
      key: "8 秒",
    },
  ];
  const current = goals.find((goal) => !goal.done);
  const complete = !current && !session.crashed;
  return (
    <aside className="tutorial-card" aria-label="驾驶入门" aria-live="polite">
      <div className="tutorial-top">
        <span>驾驶入门 · {goals.filter((goal) => goal.done).length} / 3</span>
        <button onClick={dismiss} aria-label="收起入门提示">
          ×
        </button>
      </div>
      <div className="tutorial-steps">
        {goals.map((goal) => (
          <i key={goal.title} className={goal.done ? "done" : ""} />
        ))}
      </div>
      <strong>{complete ? "准备好独自上路了" : current?.title}</strong>
      <p>
        {complete
          ? "继续完成这段练习，或在结算后挑战正式路线。练习不计入关卡星级。"
          : current?.detail}
      </p>
      <div className="tutorial-key">
        {complete ? (
          <button onClick={dismiss}>继续练习 →</button>
        ) : (
          <kbd>{current?.key}</kbd>
        )}
      </div>
    </aside>
  );
}
