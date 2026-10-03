// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import Tutorial from "../src/game/Tutorial";
import type { GameSession } from "../src/game/types";

afterEach(cleanup);
it("marks lessons only from simulator actions and requires a continuous safe interval", () => {
  const snapshot = (
    step: number,
    action = 1,
    laneChanges = 0,
    danger = false,
  ) =>
    ({
      frame: { step, time_s: step / 5, action },
      risk: { danger },
      lane_changes: laneChanges,
      crashed: false,
    }) as GameSession;
  const { rerender } = render(
    <Tutorial session={snapshot(0)} dismiss={() => undefined} />,
  );
  expect(screen.getByText("调整车速")).toBeTruthy();
  rerender(<Tutorial session={snapshot(1, 4)} dismiss={() => undefined} />);
  expect(screen.getByText("完成一次换道")).toBeTruthy();
  rerender(
    <Tutorial session={snapshot(20, 0, 1, true)} dismiss={() => undefined} />,
  );
  rerender(<Tutorial session={snapshot(50, 1, 1)} dismiss={() => undefined} />);
  expect(screen.getByText("留出安全距离")).toBeTruthy();
  rerender(<Tutorial session={snapshot(60, 1, 1)} dismiss={() => undefined} />);
  expect(screen.getByText("准备好独自上路了")).toBeTruthy();
  rerender(
    <Tutorial session={snapshot(61, 1, 1, true)} dismiss={() => undefined} />,
  );
  expect(screen.getByText("准备好独自上路了")).toBeTruthy();
});
