"""Game domain: individual driving, live AI duel, scoring and complete replays."""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import secrets
import threading
import time
from typing import Any
from uuid import uuid4

import numpy as np
import torch

from stable_baselines3 import PPO, DQN, A2C
from rl_course.driving_env import make_driving_env, road_risk_v2
from rl_course.driving_env_v3 import make_challenge_env
from rl_course.game_rules import GAME_VERSION, ENV_VERSION, POLICY_FREQUENCY, performance, duel_outcome
from rl_course.challenge_rules import GAME_VERSION as CHALLENGE_GAME_VERSION, ENV_VERSION as CHALLENGE_ENV_VERSION
from rl_course.serialization import frame
from server.catalog import model_spec, level_spec, challenge_model_spec, challenge_level_spec, track_by_id, VEHICLES
from server.records import RecordStore

torch.set_num_threads(1)
CLASSES = {"ppo": PPO, "dqn": DQN, "a2c": A2C}


@dataclass
class Runner:
    env: Any
    obs: Any
    model: Any = None
    model_steps: int = 0
    model_info: dict = field(default_factory=dict)
    inference_stride: int = 1
    steps: int = 0
    reward: float = 0
    last_reward: float = 0
    speeds: list = field(default_factory=list)
    done: bool = False
    action: int = 1
    decision: dict | None = None
    start_x: float = 0
    previous_lane: int = 0
    lane_changes: int = 0
    danger_steps: int = 0

    def advance(self, action=1):
        if self.done:
            return
        if self.model is not None:
            if self.steps % self.inference_stride == 0:
                predicted, _ = self.model.predict(self.obs, deterministic=True)
                action = int(np.asarray(predicted).item())
                policy = getattr(self.model, "policy", None)
                if policy is not None:
                    with torch.no_grad():
                        tensor, _ = policy.obs_to_tensor(self.obs)
                        if hasattr(policy, "get_distribution"):
                            values = policy.get_distribution(tensor).distribution.probs[0]
                            kind = "probability"
                        elif hasattr(policy, "q_net"):
                            values = policy.q_net(tensor)[0]
                            kind = "q_value"
                        else:
                            values = None
                        if values is not None:
                            self.decision = {"kind": kind, "values": [round(float(v), 5) for v in values], "action": action}
            else:
                action = 1
                self.decision = None
        self.obs, reward, terminated, truncated, _ = self.env.step(action)
        self.action = action
        self.steps += 1
        self.reward += float(reward)
        self.last_reward = float(reward)
        self.speeds.append(float(self.env.unwrapped.vehicle.speed) * 3.6)
        self.done = bool(terminated or truncated)
        ego = self.env.unwrapped.vehicle
        lane = ego.lane_index[2]
        if lane != self.previous_lane:
            self.lane_changes += 1
            self.previous_lane = lane
        if road_risk_v2(self.env)["danger"]:
            self.danger_steps += 1

    def snapshot(self, track: dict):
        distance = max(0.0, float(self.env.unwrapped.vehicle.position[0] - self.start_x))
        crashed = bool(self.env.unwrapped.vehicle.crashed)
        failed = bool(crashed or (self.done and not self.env.unwrapped.completed))
        overtakes = int(self.env.unwrapped.overtaken_count)
        danger = self.danger_steps / POLICY_FREQUENCY
        return {"done": self.done, "crashed": crashed, "steps": self.steps, "model_steps": self.model_steps,
                "decision": self.decision,
                "model_info": {**self.model_info, "inference_stride": self.inference_stride} if self.model is not None else None,
                "total_reward": round(self.reward, 3), "distance_m": round(distance, 1),
                "mean_speed_kmh": round(float(np.mean(self.speeds)), 1) if self.speeds else round(float(self.env.unwrapped.vehicle.speed) * 3.6, 1),
                "overtakes": overtakes, "lane_changes": int(self.env.unwrapped.lane_changes), "danger_seconds": round(danger, 1),
                **performance(track, done=self.done, crashed=failed, distance=distance, overtakes=overtakes, danger_seconds=danger),
                "risk": road_risk_v2(self.env), "frame": frame(self.env, self.steps, self.action, self.last_reward)}


@dataclass
class GameSession:
    id: str
    mode: str
    track: dict
    seed: int
    policy: str | None
    player: Runner
    rival: Runner | None = None
    ai_level: str | None = None
    vehicle: str = "sport"
    practice: bool = False
    events: list = field(default_factory=list)
    last_danger_event: dict = field(default_factory=dict)
    frames: list = field(default_factory=list)
    saved: bool = False
    last_access: float = field(default_factory=time.monotonic)
    lock: threading.RLock = field(default_factory=threading.RLock)

    def snapshot(self):
        player = self.player.snapshot(self.track)
        rival = self.rival.snapshot(self.track) if self.rival else None
        return {**player, "session_id": self.id, "mode": self.mode, "track": self.track, "seed": self.seed,
                "policy": self.policy, "ai_level": self.ai_level, "vehicle": self.vehicle, "practice": self.practice,
                "version": CHALLENGE_GAME_VERSION if self.track.get("env_version") == CHALLENGE_ENV_VERSION else GAME_VERSION,
                "env_version": self.track.get("env_version", ENV_VERSION), "events": list(self.events),
                "outcome": duel_outcome(player, rival), "player_done": player["done"],
                "done": player["done"] and (rival is None or rival["done"]), "rival": rival}


class GameManager:
    def __init__(self, store: RecordStore | None = None):
        self.store = store or RecordStore()
        self.sessions: dict[str, GameSession] = {}
        self.models: dict[str, tuple] = {}
        self.lock = threading.RLock()

    def load_model(self, policy):
        spec = challenge_model_spec(policy) if policy.startswith("v3_") else model_spec(policy)
        path = spec["path"]
        with self.lock:
            stamp = (str(path), path.stat().st_mtime_ns, spec.get("sha256"), spec["algorithm"], spec.get("steps", 0),
                     spec.get("seed"), spec.get("run_id"), spec.get("method"))
            cached = self.models.get(policy)
            if cached is None or cached[0] != stamp:
                if spec.get("sha256") and hashlib.sha256(path.read_bytes()).hexdigest() != spec["sha256"]:
                    raise ValueError("AI 模型校验未通过，请恢复完整模型文件。")
                model = CLASSES[spec["algorithm"]].load(str(path), device="cpu")
                provenance = {key: spec.get(key) for key in ("sha256", "algorithm", "steps", "seed", "run_id", "method")}
                provenance["env_version"] = spec.get("env_version", ENV_VERSION)
                cached = (stamp, model, spec.get("steps", 0), provenance)
                self.models[policy] = cached
            return cached[1], cached[2]

    def _runner(self, track, seed, policy=None, inference_stride=1):
        model, steps = self.load_model(policy) if policy else (None, 0)
        cached = self.models.get(policy)
        model_info = dict(cached[3]) if cached and cached[1] is model else {}
        factory = make_challenge_env if track.get("env_version") == CHALLENGE_ENV_VERSION else make_driving_env
        env = factory(track["scenario"], track["duration"])
        obs, _ = env.reset(seed=seed)
        ego = env.unwrapped.vehicle
        return Runner(env=env, obs=obs, model=model, model_steps=steps, model_info=model_info, inference_stride=inference_stride,
                      start_x=float(ego.position[0]), previous_lane=ego.lane_index[2])

    def create(self, mode="human", track_id="coast", policy="ppo", seed=None, ai_level=None, vehicle="sport", practice=False):
        if mode not in ("human", "ai", "duel"):
            raise ValueError("Unknown driving mode")
        track = track_by_id(track_id)
        if vehicle not in {item["id"] for item in VEHICLES}:
            raise ValueError("没有找到这辆车。")
        if practice and mode != "human":
            raise ValueError("驾驶教学仅支持亲自驾驶。")
        seed = secrets.randbelow(1_000_000) if seed is None else seed
        inference_stride = 1
        if mode != "human" and ai_level:
            spec = (challenge_level_spec(ai_level) if track.get("env_version") == CHALLENGE_ENV_VERSION
                    else level_spec(ai_level))
            policy = spec["model"]
            inference_stride = max(1, int(spec.get("inference_stride", 1)))
        # Load before allocating either environment so a missing model cannot leak a session.
        if mode != "human":
            self.load_model(policy)
            cached = self.models.get(policy)
            if cached and cached[3].get("env_version") != track.get("env_version", ENV_VERSION):
                raise ValueError("AI 模型与这条路线的环境版本不匹配。")
        with self.lock:
            stale = [key for key, session in self.sessions.items() if time.monotonic() - session.last_access > 900]
        for session_id in stale:
            self.close(session_id)
        with self.lock:
            if len(self.sessions) >= 12:
                raise RuntimeError("驾驶回合过多，请关闭其他页面后重试。")
            player = self._runner(track, seed, policy if mode == "ai" else None, inference_stride)
            try:
                rival = self._runner(track, seed, policy, inference_stride) if mode == "duel" else None
            except BaseException:
                player.env.close()
                raise
            session = GameSession(uuid4().hex, mode, track, seed, policy if mode != "human" else None, player, rival,
                                  ai_level=ai_level if mode != "human" else None, vehicle=vehicle, practice=practice)
            self.sessions[session.id] = session
            snapshot = session.snapshot()
            session.frames.append(snapshot)
            return snapshot

    def get(self, session_id):
        with self.lock:
            if session_id not in self.sessions:
                raise KeyError(session_id)
            session = self.sessions[session_id]
            session.last_access = time.monotonic()
            return session

    def advance(self, session_id, action=1):
        if action not in range(5):
            raise ValueError("Invalid action")
        session = self.get(session_id)
        with session.lock:
            if session.saved:
                return session.snapshot()
            before = session.snapshot()
            session.player.advance(action)
            if session.rival:
                session.rival.advance()
            snapshot = session.snapshot()
            self._events(session, before, snapshot)
            snapshot["events"] = list(session.events)
            session.frames.append(snapshot)
            if snapshot["done"]:
                self.store.save(snapshot, session.frames)
                session.saved = True
            return snapshot

    @staticmethod
    def _events(session, before, after):
        for actor in ("player", "rival"):
            previous = before if actor == "player" else before.get("rival")
            current = after if actor == "player" else after.get("rival")
            if previous is None or current is None:
                continue
            time_s = round(current["frame"]["time_s"], 2)
            prefix = "你" if actor == "player" else "AI"
            types = []
            if current["overtakes"] > previous["overtakes"]:
                types.append(("overtake", f"{prefix}完成超车"))
            if current["crashed"] and not previous["crashed"]:
                types.append(("collision", f"{prefix}发生碰撞"))
            if current["completed"] and not previous["completed"]:
                types.append(("finish", f"{prefix}安全完赛"))
            if current["risk"]["danger"] and not previous["risk"]["danger"] and time_s - session.last_danger_event.get(actor, -10) >= 3:
                types.append(("danger", f"{prefix}车距过近"))
                session.last_danger_event[actor] = time_s
            session.events.extend({"time_s": time_s, "type": kind, "actor": actor, "label": label} for kind, label in types)

    def finish_rival(self, session_id):
        session = self.get(session_id)
        with session.lock:
            if not session.player.done:
                raise ValueError("请先完成自己的行程。")
            while not session.snapshot()["done"]:
                self.advance(session_id)
            return session.snapshot()

    def close(self, session_id):
        with self.lock:
            session = self.sessions.pop(session_id, None)
        if session is not None:
            with session.lock:
                session.player.env.close()
                if session.rival:
                    session.rival.env.close()


game = GameManager()
