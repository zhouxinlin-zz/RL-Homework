// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import GameApp from "../src/game/GameApp";
import { api } from "../src/game/api";
import type { Catalog, GameSession } from "../src/game/types";

vi.mock("../src/game/RoadScene", () => ({
  default: () => <div data-testid="road-scene" />,
}));
vi.mock("../src/game/api", () => ({
  api: {
    catalog: vi.fn(),
    records: vi.fn(),
    start: vi.fn(),
    step: vi.fn(),
    close: vi.fn(),
    replay: vi.fn(),
  },
}));
const catalog: Catalog = {
  version: "3.1.0",
  step_ms: 200,
  tracks: [
    {
      id: "convoy",
      name: "慢车编队",
      en: "CONVOY",
      scenario: "convoy",
      env_version: "3.1",
      duration: 35,
      target_m: 790,
      theme: "coast",
      difficulty: 2,
      description: "",
    },
    {
      id: "weave",
      name: "交织车流",
      en: "WEAVE",
      scenario: "weave",
      env_version: "3.1",
      duration: 45,
      target_m: 900,
      theme: "city",
      difficulty: 3,
      description: "",
    },
    {
      id: "pressure",
      name: "连续高压",
      en: "PRESSURE",
      scenario: "pressure",
      env_version: "3.1",
      duration: 55,
      target_m: 1270,
      theme: "sunset",
      difficulty: 4,
      description: "",
    },
  ],
  drivers: [
    {
      id: "v3_expert",
      name: "VECTOR",
      subtitle: "向量",
      algorithm: "PPO",
      color: "#bdf47c",
      available: true,
      steps: 175000,
      description: "",
    },
  ],
  ai_levels: [
    { id: "beginner", name: "入门", description: "", available: true },
    { id: "standard", name: "标准", description: "", available: true },
    { id: "expert", name: "高手", description: "", available: true },
  ],
};
function sample(
  trackId: string,
  id: string,
  done = false,
  outcome: "win" | "loss" = "win",
): GameSession {
  const track = catalog.tracks.find((item) => item.id === trackId)!;
  const frame = {
    step: 0,
    time_s: done ? track.duration : 0,
    action: 1,
    reward: 0,
    ego_id: 0,
    vehicles: [
      {
        id: 0,
        x: 0,
        y: 4,
        speed: 25,
        heading: 0,
        length: 5,
        width: 2,
        crashed: false,
      },
    ],
  };
  const runner = {
    done,
    crashed: false,
    steps: 0,
    model_steps: 175000,
    total_reward: 0,
    distance_m: 1300,
    mean_speed_kmh: 90,
    overtakes: 5,
    lane_changes: 2,
    danger_seconds: 0,
    score: 1800,
    stars: 3,
    risk: { gap_m: null, ttc_s: null, danger: false },
    frame,
  };
  return {
    ...runner,
    session_id: id,
    mode: "duel",
    track,
    seed: 531124,
    policy: "v3_expert",
    ai_level: "expert",
    player_done: done,
    rival: { ...runner, score: outcome === "win" ? 1700 : 1900 },
    outcome: done ? outcome : null,
    events: [
      { actor: "player", type: "danger", time_s: 10, label: "你车距过近" },
    ],
    version: "3.1.0",
  };
}
beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(api.catalog).mockResolvedValue(catalog);
  vi.mocked(api.records).mockResolvedValue({
    runs: [],
    best: [],
    total_runs: 0,
  });
  vi.mocked(api.close).mockResolvedValue(undefined);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
async function openGame() {
  render(<GameApp />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1);
  });
}
function prepareRound(
  track: string,
  id: string,
  outcome: "win" | "loss" = "win",
) {
  vi.mocked(api.start).mockResolvedValue(sample(track, id));
  vi.mocked(api.step).mockResolvedValue(sample(track, id, true, outcome));
}
async function finishRound(button: HTMLElement) {
  await act(async () => {
    fireEvent.click(button);
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(201);
  });
}

it("offers one expert contest and no spare opponents or modes", async () => {
  await openGame();
  expect(screen.getByRole("navigation", { name: "游戏主菜单" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /选择起始路线/ }));
  expect(screen.getByRole("dialog", { name: "赛前准备" })).toBeTruthy();
  expect(screen.getByText("同一段车流，挑战高手电脑。")).toBeTruthy();
  expect(screen.queryByRole("group", { name: "AI 难度" })).toBeNull();
  expect(screen.queryByText("其他电脑对手")).toBeNull();
  expect(screen.queryByText("自由驾驶")).toBeNull();
  expect(screen.queryByText("驾驶入门")).toBeNull();
});

it("starts the three-route contest with the real expert and sends keyboard actions", async () => {
  const session = sample("convoy", "duel-1");
  vi.mocked(api.start).mockResolvedValue(session);
  vi.mocked(api.step).mockResolvedValue(session);
  await openGame();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /开始人机对决/ }));
  });
  expect(api.start).toHaveBeenCalledWith({
    mode: "duel",
    track_id: "convoy",
    policy: "v3_expert",
    seed: 531124,
    ai_level: "expert",
    vehicle: "sport",
    practice: false,
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
  fireEvent.keyDown(window, { key: "ArrowUp" });
  fireEvent.keyDown(window, { key: "ArrowRight", repeat: true });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(201);
  });
  expect(api.step).toHaveBeenCalledWith("duel-1", 3);
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.getByRole("dialog", { name: "游戏暂停" })).toBeTruthy();
});

it("blocks gameplay if the expert is missing rather than substituting an easy model", async () => {
  vi.mocked(api.catalog).mockResolvedValue({
    ...catalog,
    ai_levels: catalog.ai_levels!.map((item) => ({
      ...item,
      available: item.id !== "expert",
    })),
  });
  await openGame();
  expect(
    (screen.getByRole("button", { name: /开始人机对决/ }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: /选择起始路线/ }));
  expect(
    (screen.getByRole("button", { name: /开始人机对决/ }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(screen.queryByRole("button", { name: /入门/ })).toBeNull();
  expect(api.start).not.toHaveBeenCalled();
});

it("keeps series scores through replay and retries, then advances with the same expert", async () => {
  prepareRound("convoy", "round-1");
  await openGame();
  await finishRound(screen.getByRole("button", { name: /开始人机对决/ }));
  expect(screen.getByLabelText("赛程战绩").textContent).toContain(
    "你 1 : 0 电脑",
  );
  vi.mocked(api.replay).mockResolvedValue({
    summary: sample("convoy", "round-1", true),
    frames: [sample("convoy", "round-1"), sample("convoy", "round-1", true)],
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /你车距过近/ }));
  });
  expect(screen.getByRole("slider", { name: "回放进度" })).toBeTruthy();
  expect(api.close).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "退出回放" }));
  expect(screen.getByLabelText("赛程战绩").textContent).toContain(
    "你 1 : 0 电脑",
  );
  prepareRound("convoy", "round-1-retry");
  await finishRound(screen.getByRole("button", { name: "重试本段" }));
  expect(screen.getByLabelText("赛程战绩").textContent).toContain(
    "你 1 : 0 电脑",
  );
  prepareRound("weave", "round-2", "loss");
  await finishRound(screen.getByRole("button", { name: /继续下一段/ }));
  expect(api.start).toHaveBeenLastCalledWith(
    expect.objectContaining({
      track_id: "weave",
      seed: 531124,
      policy: "v3_expert",
      ai_level: "expert",
    }),
  );
  expect(screen.getByLabelText("赛程战绩").textContent).toContain(
    "你 1 : 1 电脑",
  );
  prepareRound("pressure", "round-3");
  await finishRound(screen.getByRole("button", { name: /继续下一段/ }));
  expect(screen.getByLabelText("赛程战绩").textContent).toContain(
    "你 2 : 1 电脑",
  );
  expect(screen.getByText("你赢下了本次赛程。")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /继续下一段/ })).toBeNull();
});

it("lets a short pressure contest request new traffic without changing the model", async () => {
  prepareRound("pressure", "short-1");
  await openGame();
  fireEvent.click(screen.getByRole("button", { name: /选择起始路线/ }));
  await finishRound(screen.getByRole("button", { name: /开始人机对决/ }));
  expect(screen.queryByLabelText("赛程战绩")).toBeNull();
  prepareRound("pressure", "short-2");
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "换一组车流" }));
  });
  expect(api.start).toHaveBeenLastCalledWith(
    expect.objectContaining({
      track_id: "pressure",
      seed: undefined,
      policy: "v3_expert",
      ai_level: "expert",
    }),
  );
});

it("keeps the contest playable when history cannot be loaded", async () => {
  vi.mocked(api.records).mockRejectedValue(new Error("History unavailable"));
  await openGame();
  expect(
    (screen.getByRole("button", { name: /开始人机对决/ }) as HTMLButtonElement)
      .disabled,
  ).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: /选择起始路线/ }));
  expect(screen.getByRole("dialog", { name: "赛前准备" })).toBeTruthy();
});
