import { useCallback, useEffect, useRef, useState } from "react";

const actions: Record<string, number> = {
  arrowleft: 0,
  a: 0,
  arrowright: 2,
  d: 2,
  arrowup: 3,
  w: 3,
  arrowdown: 4,
  s: 4,
};

/** Lane changes are deliberate taps; speed controls support a controlled hold. */
export function useDriveControls(
  enabled: boolean,
  onAction: (action: number) => void,
) {
  const [pressed, setPressed] = useState<number[]>([]);
  const held = useRef(new Map<string, number>());
  const nextRepeat = useRef(0);
  const callback = useRef(onAction);
  useEffect(() => {
    callback.current = onAction;
  }, [onAction]);
  const clear = useCallback(() => {
    held.current.clear();
    setPressed([]);
  }, []);
  const press = useCallback(
    (source: string, action: number) => {
      if (!enabled || held.current.has(source)) return;
      held.current.set(source, action);
      nextRepeat.current = performance.now() + 320;
      setPressed([...held.current.values()]);
      callback.current(action);
    },
    [enabled],
  );
  const release = useCallback((source: string) => {
    held.current.delete(source);
    setPressed([...held.current.values()]);
  }, []);
  useEffect(() => {
    if (!enabled) return;
    const keydown = (event: KeyboardEvent) => {
      if (
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        (event.target instanceof HTMLElement &&
          event.target.matches("input,select,textarea,[contenteditable=true]"))
      )
        return;
      const action = actions[event.key.toLowerCase()];
      if (action === undefined) return;
      event.preventDefault();
      if (!event.repeat) press(event.code || event.key.toLowerCase(), action);
    };
    const keyup = (event: KeyboardEvent) =>
      release(event.code || event.key.toLowerCase());
    const visibility = () => {
      if (document.hidden) clear();
    };
    const timer = window.setInterval(() => {
      const speed = [...held.current.values()]
        .filter((action) => action === 3 || action === 4)
        .at(-1);
      if (speed !== undefined && performance.now() >= nextRepeat.current) {
        callback.current(speed);
        nextRepeat.current = performance.now() + 200;
      }
    }, 40);
    window.addEventListener("keydown", keydown);
    window.addEventListener("keyup", keyup);
    window.addEventListener("blur", clear);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      clearInterval(timer);
      clear();
      window.removeEventListener("keydown", keydown);
      window.removeEventListener("keyup", keyup);
      window.removeEventListener("blur", clear);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [enabled, press, release, clear]);
  return { pressed: enabled ? pressed : [], press, release };
}
