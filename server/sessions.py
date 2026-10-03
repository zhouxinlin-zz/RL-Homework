"""Manage live HighwayEnv episodes and pretrained policies."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import numpy as np
from stable_baselines3 import DQN, PPO

from rl_course.environment import SCENARIOS, make_env
from rl_course.serialization import frame


Mode = Literal["ai", "human"]
Policy = Literal["dqn", "ppo"]


@dataclass
class DrivingSession:
    session_id: str
    env: Any
    observation: Any
    mode: Mode
    policy: Policy | None
    scenario: str
    seed: int
    created_at: float = field(default_factory=time.monotonic)
    last_access: float = field(default_factory=time.monotonic)
    step_count: int = 0
    total_reward: float = 0.0
    speeds_kmh: list[float] = field(default_factory=list)
    done: bool = False
    last_action: int | None = None
    last_reward: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)


class SessionManager:
    def __init__(self, models_dir: Path = Path("artifacts/models")) -> None:
        self.models_dir = models_dir
        self.sessions: dict[str, DrivingSession] = {}
        self.models: dict[Policy, Any] = {}
        self.lock = threading.Lock()

    def model_available(self, policy: Policy) -> bool:
        return (self.models_dir / f"{policy}_seed42.zip").exists()

    def _model(self, policy: Policy) -> Any:
        with self.lock:
            if policy not in self.models:
                path = self.models_dir / f"{policy}_seed42.zip"
                if not path.exists():
                    raise FileNotFoundError(f"Trained model is missing: {path}")
                model_class = DQN if policy == "dqn" else PPO
                self.models[policy] = model_class.load(str(path), device="cpu")
            return self.models[policy]

    def _prune(self) -> None:
        now = time.monotonic()
        with self.lock:
            stale = [key for key, item in self.sessions.items() if now - item.last_access > 1800]
            for key in stale:
                self.sessions.pop(key).env.close()

    def create(self, mode: Mode, scenario: str, policy: Policy | None, seed: int | None) -> dict[str, Any]:
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario}")
        if mode == "ai":
            if policy is None:
                raise ValueError("AI mode needs a policy")
            self._model(policy)
        self._prune()
        with self.lock:
            if len(self.sessions) >= 32:
                raise RuntimeError("Too many active sessions")
        episode_seed = seed if seed is not None else secrets.randbelow(1_000_000)
        env = make_env(scenario)
        observation, _ = env.reset(seed=episode_seed)
        session = DrivingSession(
            session_id=uuid4().hex,
            env=env,
            observation=observation,
            mode=mode,
            policy=policy if mode == "ai" else None,
            scenario=scenario,
            seed=episode_seed,
        )
        with self.lock:
            self.sessions[session.session_id] = session
        return self.snapshot(session)

    def get(self, session_id: str) -> DrivingSession:
        with self.lock:
            session = self.sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        session.last_access = time.monotonic()
        return session

    @staticmethod
    def snapshot(session: DrivingSession) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "mode": session.mode,
            "policy": session.policy,
            "scenario": session.scenario,
            "seed": session.seed,
            "done": session.done,
            "crashed": bool(session.env.unwrapped.vehicle.crashed),
            "steps": session.step_count,
            "total_reward": session.total_reward,
            "mean_speed_kmh": float(np.mean(session.speeds_kmh)) if session.speeds_kmh else 0.0,
            "frame": frame(session.env, session.step_count, session.last_action, session.last_reward),
        }

    def step(self, session_id: str, requested_action: int | None = None) -> dict[str, Any]:
        session = self.get(session_id)
        with session.lock:
            if session.done:
                return self.snapshot(session)
            if session.mode == "ai":
                prediction, _ = self._model(session.policy).predict(session.observation, deterministic=True)
                action = int(np.asarray(prediction).item())
            else:
                action = 1 if requested_action is None else requested_action
                if not session.env.action_space.contains(action):
                    raise ValueError("Action must be an integer between 0 and 4")
            observation, reward, terminated, truncated, _ = session.env.step(action)
            session.observation = observation
            session.step_count += 1
            session.total_reward += float(reward)
            session.speeds_kmh.append(float(session.env.unwrapped.vehicle.speed) * 3.6)
            session.done = bool(terminated or truncated)
            session.last_action = action
            session.last_reward = float(reward)
            return self.snapshot(session)

    def close(self, session_id: str) -> None:
        with self.lock:
            session = self.sessions.pop(session_id, None)
        if session is None:
            raise KeyError(session_id)
        with session.lock:
            session.env.close()


manager = SessionManager()
