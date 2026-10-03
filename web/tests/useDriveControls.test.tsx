// @vitest-environment jsdom
import { act, cleanup, fireEvent, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useDriveControls } from "../src/game/useDriveControls";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

it("holds speed at a controlled rate and stops immediately when released", () => {
  const action = vi.fn();
  const { result } = renderHook(() => useDriveControls(true, action));
  fireEvent.keyDown(window, { key: "ArrowUp", code: "ArrowUp" });
  expect(action.mock.calls).toEqual([[3]]);
  expect(result.current.pressed).toContain(3);
  act(() => vi.advanceTimersByTime(719));
  expect(action.mock.calls).toEqual([[3], [3], [3]]);
  fireEvent.keyUp(window, { key: "ArrowUp", code: "ArrowUp" });
  act(() => vi.advanceTimersByTime(1000));
  expect(action).toHaveBeenCalledTimes(3);
  expect(result.current.pressed).toEqual([]);
});

it("does not repeat lane changes and clears held keys across pause or lost focus", () => {
  const action = vi.fn();
  const { result, rerender } = renderHook(
    ({ enabled }) => useDriveControls(enabled, action),
    { initialProps: { enabled: true } },
  );
  fireEvent.keyDown(window, { key: "ArrowLeft", code: "ArrowLeft" });
  fireEvent.keyDown(window, {
    key: "ArrowLeft",
    code: "ArrowLeft",
    repeat: true,
  });
  act(() => vi.advanceTimersByTime(1000));
  expect(action.mock.calls).toEqual([[0]]);
  fireEvent.keyDown(window, { key: "s", code: "KeyS" });
  act(() => window.dispatchEvent(new Event("blur")));
  act(() => vi.advanceTimersByTime(1000));
  expect(action.mock.calls).toEqual([[0], [4]]);
  expect(result.current.pressed).toEqual([]);
  act(() => result.current.press("pointer-1", 3));
  rerender({ enabled: false });
  rerender({ enabled: true });
  act(() => vi.advanceTimersByTime(1000));
  expect(action.mock.calls).toEqual([[0], [4], [3]]);
  expect(result.current.pressed).toEqual([]);
});
