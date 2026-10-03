// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import Hud from "../src/game/Hud";
import { nearbyTraffic } from "../src/game/trafficProjection";
import type { GameSession } from "../src/game/types";
import type { WorldFrame } from "../src/game/types";

afterEach(cleanup);
it("limits the preview to true nearby vehicles and honors its disabled setting", () => {
  const frame: WorldFrame = {
    step: 0,
    time_s: 0,
    action: 1,
    reward: 0,
    ego_id: 0,
    vehicles: [0, 120, -80, 121, -81].map((x, id) => ({
      id,
      x: x + 200,
      y: (id % 3) * 4,
      speed: 24,
      heading: 0,
      length: 4.7,
      width: 1.85,
      crashed: false,
    })),
  };
  expect(nearbyTraffic(frame).map((vehicle) => vehicle.id)).toEqual([0, 1, 2]);
  expect(nearbyTraffic(frame)[0].y).toBe(108);
  const session = {
    session_id: "test",
    track: { name: "海岸公路", en: "COASTLINE", target_m: 600, duration: 30 },
    mode: "human",
    frame,
    risk: { danger: false },
    distance_m: 0,
    overtakes: 0,
    score: 0,
    crashed: false,
    done: false,
  } as GameSession;
  const { rerender, container } = render(
    <Hud session={session} pause={() => undefined} trafficPreview />,
  );
  expect(screen.getByLabelText("周车预览")).toBeTruthy();
  expect(container.querySelectorAll("[data-vehicle-id]")).toHaveLength(3);
  rerender(
    <Hud session={session} pause={() => undefined} trafficPreview={false} />,
  );
  expect(screen.queryByLabelText("周车预览")).toBeNull();
  expect(screen.getByLabelText("暂停游戏")).toBeTruthy();
  rerender(
    <Hud
      session={{ ...session, mode: "duel", rival: session }}
      pause={() => undefined}
      trafficPreview
    />,
  );
  expect(screen.getByRole("complementary", { name: "你的周车" })).toBeTruthy();
  rerender(
    <Hud
      session={{ ...session, mode: "ai" }}
      pause={() => undefined}
      trafficPreview
    />,
  );
  expect(screen.getByRole("complementary", { name: "周车预览" })).toBeTruthy();
});
