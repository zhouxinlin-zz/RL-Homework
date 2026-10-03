// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/game/api";
import { useDriving } from "../src/game/useDriving";
import type { GameSession } from "../src/game/types";

vi.mock("../src/game/api", () => ({
  api: { start: vi.fn(), step: vi.fn(), close: vi.fn(), finish: vi.fn() },
}));
const config = { mode: "human" as const, track_id: "coast", policy: "ppo" };
const initial = {
  session_id: "test-run",
  mode: "human",
  done: false,
  player_done: false,
  frame: { step: 0, time_s: 0, action: 1, vehicles: [], ego_id: 0, reward: 0 },
} as GameSession;

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  vi.mocked(api.close).mockResolvedValue(undefined);
  vi.mocked(api.start).mockResolvedValue(initial);
  vi.mocked(api.step).mockResolvedValue({ ...initial, steps: 1 });
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("driving lifecycle", () => {
  it("replaces outdated commands without losing a command on the other axis", async () => {
    const { result } = renderHook(useDriving);
    await act(async () => {
      await result.current.start(config);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    act(() => {
      result.current.action(3);
      result.current.action(0);
      result.current.action(4);
      result.current.action(2);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(601);
    });
    expect(api.step).toHaveBeenNthCalledWith(1, "test-run", 4);
    expect(api.step).toHaveBeenNthCalledWith(2, "test-run", 2);
    expect(api.step).toHaveBeenNthCalledWith(3, "test-run", 1);
  });
  it("preserves a brake then lane-change input across consecutive ticks", async () => {
    const { result } = renderHook(useDriving);
    await act(async () => {
      await result.current.start(config);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    act(() => {
      result.current.action(4);
      result.current.action(0);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(401);
    });
    expect(api.step).toHaveBeenNthCalledWith(1, "test-run", 4);
    expect(api.step).toHaveBeenNthCalledWith(2, "test-run", 0);
    act(() => {
      result.current.action(3);
      result.current.pause();
      result.current.resume();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(201);
    });
    expect(api.step).toHaveBeenNthCalledWith(3, "test-run", 1);
  });
  it("counts down before sending an action and stops stepping when paused", async () => {
    const { result } = renderHook(useDriving);
    await act(async () => {
      await result.current.start(config);
    });
    expect(result.current.phase).toBe("countdown");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(result.current.phase).toBe("running");
    act(() => result.current.action(3));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(201);
    });
    expect(api.step).toHaveBeenCalledWith("test-run", 3);
    act(() => result.current.pause());
    const count = vi.mocked(api.step).mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(api.step).toHaveBeenCalledTimes(count);
  });

  it("closes a late-created session after returning to the menu", async () => {
    let resolve!: (value: GameSession) => void;
    vi.mocked(api.start).mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    const { result } = renderHook(useDriving);
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.start(config);
    });
    act(() => result.current.stop());
    await act(async () => {
      resolve(initial);
      await pending;
    });
    expect(result.current.phase).toBe("idle");
    expect(result.current.session).toBeNull();
    expect(api.close).toHaveBeenCalledWith("test-run");
  });

  it("does not overlap requests or restore a stopped run from a late response", async () => {
    let resolve!: (value: GameSession) => void;
    vi.mocked(api.step).mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    const { result } = renderHook(useDriving);
    await act(async () => {
      await result.current.start(config);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(api.step).toHaveBeenCalledTimes(1);
    act(() => result.current.stop());
    await act(async () => {
      resolve({ ...initial, steps: 1 });
    });
    expect(result.current.session).toBeNull();
    expect(result.current.phase).toBe("idle");
  });

  it("finishes once the backend has finalized the run", async () => {
    vi.mocked(api.step).mockResolvedValue({
      ...initial,
      done: true,
      player_done: true,
    });
    const { result } = renderHook(useDriving);
    await act(async () => {
      await result.current.start(config);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(201);
    });
    expect(result.current.phase).toBe("finished");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(api.step).toHaveBeenCalledTimes(1);
  });

  it("preserves the remaining countdown when focus is lost and does not begin driving early", async () => {
    const { result } = renderHook(useDriving);
    await act(async () => {
      await result.current.start(config);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1400);
    });
    expect(result.current.countdown).toBe(2);
    act(() => window.dispatchEvent(new Event("blur")));
    expect(result.current.phase).toBe("paused");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(api.step).not.toHaveBeenCalled();
    act(() => result.current.resume());
    expect(result.current.phase).toBe("countdown");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1550);
    });
    expect(result.current.phase).toBe("countdown");
    expect(api.step).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(result.current.phase).toBe("running");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(201);
    });
    expect(api.step).toHaveBeenCalledTimes(1);
  });
});
