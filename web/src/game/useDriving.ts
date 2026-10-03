import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { GameSession, Phase, RunConfig } from "./types";

export function useDriving() {
  const [session, setSession] = useState<GameSession | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [countdown, setCountdown] = useState(3);
  const [error, setError] = useState("");
  const active = useRef<string | null>(null);
  const generation = useRef(0);
  const queuedActions = useRef<number[]>([]);
  const inFlight = useRef(false);
  const currentPhase = useRef<Phase>("idle");
  const countdownRemainingMs = useRef(0);
  const countdownDeadline = useRef<number | null>(null);

  const transition = useCallback((next: Phase) => {
    currentPhase.current = next;
    setPhase(next);
  }, []);
  const stop = useCallback(() => {
    generation.current += 1;
    const id = active.current;
    active.current = null;
    if (id) void api.close(id).catch(() => undefined);
    transition("idle");
    setSession(null);
    setError("");
    queuedActions.current = [];
    countdownRemainingMs.current = 0;
    countdownDeadline.current = null;
  }, [transition]);

  useEffect(() => {
    function dispose() {
      generation.current += 1;
      if (active.current) void api.close(active.current).catch(() => undefined);
      active.current = null;
    }
    const pagehide = (event: PageTransitionEvent) => {
      if (!event.persisted) dispose();
    };
    window.addEventListener("pagehide", pagehide);
    return () => {
      window.removeEventListener("pagehide", pagehide);
      dispose();
    };
  }, []);

  const start = useCallback(
    async (config: RunConfig) => {
      stop();
      const token = generation.current;
      transition("loading");
      setError("");
      try {
        const next = await api.start(config);
        if (token !== generation.current) {
          void api.close(next.session_id).catch(() => undefined);
          return;
        }
        active.current = next.session_id;
        setSession(next);
        setCountdown(3);
        countdownRemainingMs.current = 3000;
        countdownDeadline.current = null;
        transition("countdown");
      } catch (reason) {
        if (token === generation.current) {
          setError(reason instanceof Error ? reason.message : "无法开始驾驶");
          transition("idle");
        }
      }
    },
    [stop, transition],
  );

  useEffect(() => {
    if (phase !== "countdown") return;
    countdownDeadline.current =
      performance.now() + countdownRemainingMs.current;
    const timer = window.setInterval(() => {
      if (
        currentPhase.current !== "countdown" ||
        countdownDeadline.current === null
      )
        return;
      const remaining = Math.max(
        0,
        countdownDeadline.current! - performance.now(),
      );
      setCountdown(Math.ceil(remaining / 1000));
      if (remaining <= 0) {
        countdownRemainingMs.current = 0;
        countdownDeadline.current = null;
        transition("running");
      }
    }, 50);
    return () => clearInterval(timer);
  }, [phase, transition]);

  useEffect(() => {
    if (phase !== "running") return;
    let cancelled = false;
    let timer = 0;
    async function tick() {
      const id = active.current;
      if (cancelled || !id || currentPhase.current !== "running") return;
      if (inFlight.current) {
        timer = window.setTimeout(tick, 30);
        return;
      }
      inFlight.current = true;
      const started = performance.now();
      const action = queuedActions.current.shift() ?? 1;
      try {
        const next = await api.step(id, action);
        if (active.current !== id) return;
        setSession(next);
        if (next.done) transition("finished");
      } catch (reason) {
        if (active.current === id) {
          setError(reason instanceof Error ? reason.message : "连接中断");
          transition("paused");
        }
      } finally {
        inFlight.current = false;
        if (!cancelled)
          timer = window.setTimeout(
            tick,
            Math.max(0, 200 - (performance.now() - started)),
          );
      }
    }
    timer = window.setTimeout(tick, 200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [phase, transition]);

  const pause = useCallback(() => {
    if (
      currentPhase.current === "countdown" &&
      countdownDeadline.current !== null
    ) {
      countdownRemainingMs.current = Math.max(
        0,
        countdownDeadline.current - performance.now(),
      );
      countdownDeadline.current = null;
    }
    if (
      currentPhase.current === "running" ||
      currentPhase.current === "countdown"
    )
      transition("paused");
    queuedActions.current = [];
  }, [transition]);
  const resume = useCallback(() => {
    if (currentPhase.current !== "paused" || !active.current) return;
    setError("");
    transition(countdownRemainingMs.current > 0 ? "countdown" : "running");
  }, [transition]);
  const action = useCallback((value: number) => {
    if (currentPhase.current !== "running" || ![0, 2, 3, 4].includes(value))
      return;
    // Retain one pending command per axis. A correction supersedes stale input,
    // while a brake followed by a lane change still reaches consecutive ticks.
    const steering = value === 0 || value === 2;
    queuedActions.current = queuedActions.current.filter(
      (pending) => (pending === 0 || pending === 2) !== steering,
    );
    queuedActions.current.push(value);
  }, []);

  useEffect(() => {
    const visibility = () => {
      if (document.hidden) pause();
    };
    window.addEventListener("blur", pause);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      window.removeEventListener("blur", pause);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [pause]);

  const finish = useCallback(async () => {
    const id = active.current;
    if (!id) return;
    transition("loading");
    try {
      const next = await api.finish(id);
      if (active.current === id) {
        setSession(next);
        transition("finished");
      }
    } catch (reason) {
      if (active.current === id) {
        setError(String(reason));
        transition("paused");
      }
    }
  }, [transition]);

  return {
    session,
    phase,
    countdown,
    error,
    start,
    stop,
    pause,
    resume,
    action,
    finish,
  };
}
