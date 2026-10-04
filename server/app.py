"""Local HTTP API for AI and human driving sessions.

Run with: python -m uvicorn server.app:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from rl_course.driving_env_v3 import SCENARIOS
from rl_course.driving_env import TRAFFIC as LEGACY_TRAFFIC
from server.sessions import manager
from server.catalog import ROOT, driver_catalog, ai_catalog, VEHICLES, LEGACY_TRACKS, challenge_ai_catalog, challenge_driver_catalog, challenge_training_catalog
from rl_course.challenge_rules import CHALLENGE_TRACKS, GAME_VERSION as CHALLENGE_GAME_VERSION, ENV_VERSION as CHALLENGE_ENV_VERSION
from server.game import game
from server.runtime import LOADED_REVISION
from server.refinement import replay as refinement_replay


app = FastAPI(title="Lane Shift", version=CHALLENGE_GAME_VERSION)


@app.middleware("http")
async def prevent_stale_game(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/") or request.url.path in ("/", "/index.html", "/research"):
        response.headers["Cache-Control"] = "no-store"
    return response
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


class CreateSession(BaseModel):
    mode: Literal["ai", "human"] = "ai"
    scenario: Literal["light", "normal", "dense"] = "normal"
    policy: Literal["dqn", "ppo"] | None = "ppo"
    seed: int | None = Field(default=None, ge=0)


class StepSession(BaseModel):
    action: int | None = Field(default=None, ge=0, le=4)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "loaded_revision": LOADED_REVISION,
        "version": CHALLENGE_GAME_VERSION,
        "env_version": CHALLENGE_ENV_VERSION,
        "scenarios": list(SCENARIOS),
        "archive_scenarios": list(LEGACY_TRAFFIC),
        "models": {driver["id"]: driver["available"] for driver in challenge_driver_catalog()},
        "ai_levels": {level["id"]: level["available"] for level in challenge_ai_catalog()},
        "archive_models": {driver["id"]: driver["available"] for driver in driver_catalog()},
    }


@app.post("/api/sessions")
def create_session(request: CreateSession) -> dict:
    try:
        return manager.create(request.mode, request.scenario, request.policy, request.seed)
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    try:
        session = manager.get(session_id)
        with session.lock:
            return manager.snapshot(session)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Session not found") from error


@app.post("/api/sessions/{session_id}/step")
def step_session(session_id: str, request: StepSession) -> dict:
    try:
        return manager.step(session_id, request.action)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Session not found") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.delete("/api/sessions/{session_id}", status_code=204)
def close_session(session_id: str) -> None:
    try:
        manager.close(session_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Session not found") from error


class GameRequest(BaseModel):
    mode: Literal["human", "ai", "duel"] = "human"
    track_id: Literal["coast", "metro", "rush", "endurance", "midnight", "convoy", "weave", "pressure"] = "coast"
    policy: Literal["dqn", "ppo", "a2c", "ppo_mixed", "v3_beginner", "v3_standard", "v3_expert", "v3_ppo", "v3_dqn", "v3_a2c"] = "ppo_mixed"
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)
    ai_level: Literal["beginner", "standard", "expert"] | None = "standard"
    vehicle: Literal["sport", "touring", "suv"] = "sport"
    practice: bool = False


def game_call(function, *args):
    try:
        return function(*args)
    except KeyError as error:
        raise HTTPException(404, "这段驾驶记录已不存在。") from error
    except FileNotFoundError as error:
        raise HTTPException(503, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    except RuntimeError as error:
        raise HTTPException(429, str(error)) from error


@app.get("/api/game/catalog")
def catalog():
    return {"version": CHALLENGE_GAME_VERSION, "env_version": CHALLENGE_ENV_VERSION,
            "tracks": CHALLENGE_TRACKS, "archive_tracks": LEGACY_TRACKS,
            "drivers": challenge_driver_catalog(), "ai_levels": challenge_ai_catalog(),
            "training": challenge_training_catalog(),
            "archive_drivers": driver_catalog(), "archive_ai_levels": ai_catalog(),
            "vehicles": VEHICLES, "step_ms": 200}


@app.post("/api/game/sessions")
def game_create(request: GameRequest):
    return game_call(game.create, request.mode, request.track_id, request.policy, request.seed,
                     request.ai_level, request.vehicle, request.practice)


@app.post("/api/game/sessions/{session_id}/step")
def game_step(session_id: str, request: StepSession):
    return game_call(game.advance, session_id, request.action if request.action is not None else 1)


@app.post("/api/game/sessions/{session_id}/finish")
def game_finish(session_id: str):
    return game_call(game.finish_rival, session_id)


@app.delete("/api/game/sessions/{session_id}", status_code=204)
def game_close(session_id: str):
    game.close(session_id)


@app.get("/api/game/records")
def game_records():
    return game.store.list()


@app.get("/api/game/records/{run_id}/replay")
def game_replay(run_id: str):
    return game_call(game.store.replay, run_id)


@app.get("/api/game/training/replays/{track}")
def training_replay(track: Literal["convoy", "weave", "pressure"]):
    return game_call(refinement_replay, ROOT, track)


if (ROOT / "web" / "dist").exists():
    @app.get("/research")
    def archive_research():
        return RedirectResponse("/", status_code=307)

    app.mount("/", StaticFiles(directory=ROOT / "web" / "dist", html=True), name="game")
