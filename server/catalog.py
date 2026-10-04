"""Game content and the registry of evaluated v2 policies."""
from pathlib import Path
import hashlib
import json
from server.refinement import evidence as refinement_evidence, public_summary

from rl_course.game_rules import ENV_VERSION, GAME_VERSION, TRACKS
from rl_course.challenge_rules import CHALLENGE_TRACKS, ENV_VERSION as CHALLENGE_ENV_VERSION, challenge_track_by_id

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT / "artifacts" / "experiments_v2" / "deployment.json"
CHALLENGE_DEPLOYMENT = ROOT / "artifacts" / "experiments_v3" / "deployment.json"
LEGACY_TRACKS = TRACKS
ALL_TRACKS = [*CHALLENGE_TRACKS, *LEGACY_TRACKS]


def track_by_id(track_id: str) -> dict:
    if track_id in {track["id"] for track in CHALLENGE_TRACKS}:
        return challenge_track_by_id(track_id)
    for track in LEGACY_TRACKS:
        if track["id"] == track_id:
            return {**track, "env_version": ENV_VERSION}
    raise ValueError("没有找到这条路线。")
DRIVERS = [
    {"id": "ppo", "name": "VECTOR", "subtitle": "向量", "algorithm": "PPO", "color": "#bdf47c", "description": "通过多轮策略更新学习驾驶。"},
    {"id": "dqn", "name": "APEX", "subtitle": "顶点", "algorithm": "DQN", "color": "#ffad73", "description": "估计各个动作的长期回报，再选择行动。"},
    {"id": "a2c", "name": "PULSE", "subtitle": "脉冲", "algorithm": "A2C", "color": "#87c9ff", "description": "让行动策略与价值估计一起学习。"},
    {"id": "ppo_mixed", "name": "ATLAS", "subtitle": "图谱", "algorithm": "PPO · 混合车流", "color": "#c6afff", "description": "在稀疏、常规和拥挤车流间轮换训练。"},
]
LEVELS = [
    {"id": "beginner", "name": "入门", "description": "熟悉赛道与规则，练习战胜第一个对手。"},
    {"id": "standard", "name": "标准", "description": "应对混合车流，和 AI 比一比驾驶节奏。"},
    {"id": "expert", "name": "高手", "description": "挑战当前评测中表现最强的驾驶策略。"},
]
VEHICLES = [
    {"id": "sport", "name": "GT 轿跑", "description": "低矮车身，利落轮廓"},
    {"id": "touring", "name": "旅行车", "description": "修长车身，全景车顶"},
    {"id": "suv", "name": "SUV", "description": "宽肩轮廓，城市风格"},
]


def deployment() -> dict:
    if not DEPLOYMENT.exists():
        return {"env_version": ENV_VERSION, "models": {}, "levels": {}}
    data = json.loads(DEPLOYMENT.read_text(encoding="utf-8"))
    if data.get("env_version") != ENV_VERSION:
        return {"env_version": ENV_VERSION, "models": {}, "levels": {}}
    return data


def model_spec(policy: str) -> dict:
    spec = deployment().get("models", {}).get(policy)
    if not spec:
        raise FileNotFoundError("这位 AI 的新版模型尚未就绪，请选择其他对手或自由驾驶。")
    if spec.get("env_version", ENV_VERSION) != ENV_VERSION:
        raise FileNotFoundError("这份 AI 模型与当前道路版本不匹配，请恢复新版模型。")
    path = (ROOT / spec["path"]).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise FileNotFoundError("AI 模型文件缺失，请运行启动自检或重新解压完整项目。")
    return {**spec, "path": path}


def model_path(policy: str) -> Path:
    return model_spec(policy)["path"]


def level_spec(level: str) -> dict:
    if level not in {item["id"] for item in LEVELS}:
        raise ValueError("没有找到这个 AI 难度。")
    spec = deployment().get("levels", {}).get(level)
    if not spec:
        raise FileNotFoundError("这一难度的 AI 尚未就绪，请选择其他难度或自由驾驶。")
    model_spec(spec["model"])
    return spec


def driver_catalog() -> list[dict]:
    result = []
    for driver in DRIVERS:
        try:
            spec = model_spec(driver["id"])
        except FileNotFoundError:
            spec = {}
        presentation = {}
        if spec.get("method") == "demonstration-warmstart-ppo":
            presentation = {"algorithm": "示范预训练 + PPO", "description": "先通过驾驶示范学习，再使用 PPO 在混合车流中继续训练。"}
        elif spec.get("method") == "imitation-only":
            presentation = {"algorithm": "模仿学习", "description": "从驾驶示范中学习的初始策略，尚未进行强化学习微调。"}
        result.append({**driver, **presentation, "available": bool(spec), "steps": spec.get("steps", 0), "version": ENV_VERSION})
    return result


def ai_catalog() -> list[dict]:
    result = []
    for level in LEVELS:
        try:
            spec = level_spec(level["id"])
        except FileNotFoundError:
            spec = {}
        result.append({**level, "available": bool(spec), "policy": spec.get("model"),
                       "description": spec.get("description", level["description"]),
                       "evaluation": spec.get("evaluation", spec.get("validation"))})
    return result


def challenge_deployment() -> dict:
    if not CHALLENGE_DEPLOYMENT.exists():
        return {"env_version": CHALLENGE_ENV_VERSION, "models": {}, "levels": {}}
    data = json.loads(CHALLENGE_DEPLOYMENT.read_text(encoding="utf-8"))
    if data.get("env_version") != CHALLENGE_ENV_VERSION or data.get("stage") != "final":
        return {"env_version": CHALLENGE_ENV_VERSION, "models": {}, "levels": {}}
    release_path = ROOT / "artifacts/experiments_v3/iteration_4/release.json"
    if release_path.exists():
        try:
            release = json.loads(release_path.read_text(encoding="utf-8"))
            evaluation = release["evaluation"]
            report = (ROOT / evaluation["report"]).resolve()
            if (release.get("stage") == "final" and release.get("env_version") == CHALLENGE_ENV_VERSION
                    and report.is_relative_to(ROOT) and report.is_file()
                    and hashlib.sha256(report.read_bytes()).hexdigest() == evaluation.get("report_sha256")):
                data = {**data, "models": {**data["models"], **release["models"]}, "evaluation": evaluation}
        except (KeyError, ValueError, TypeError, OSError):
            pass
    refinement = refinement_evidence(ROOT)
    if refinement:
        release, report = refinement
        data = {**data, "models": {**data["models"], "v3_expert": release["model"]},
                "levels": {**data["levels"], "expert": {**data["levels"]["expert"],
                    "evaluation": report["models"][report["official"]]["overall"]}},
                "refinement": report}
    return data


def challenge_model_spec(policy: str) -> dict:
    spec = challenge_deployment().get("models", {}).get(policy)
    if not spec or spec.get("env_version") != CHALLENGE_ENV_VERSION:
        raise FileNotFoundError("挑战模型尚未完成校验，请先完成训练与评估。")
    path = (ROOT / spec["path"]).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise FileNotFoundError("挑战模型文件缺失。")
    return {**spec, "path": path}


def challenge_level_spec(level: str) -> dict:
    spec = challenge_deployment().get("levels", {}).get(level)
    if not spec:
        raise FileNotFoundError("这个 AI 难度尚未就绪。")
    challenge_model_spec(spec["model"])
    return spec


def challenge_ai_catalog() -> list[dict]:
    labels = {
        "beginner": ("入门", "熟悉路线，练习换道与超车。"),
        "standard": ("标准", "把握车流空隙，争取更多超车。"),
        "expert": ("高手", "稳定发挥，考验你的驾驶判断。"),
    }
    result = []
    for level, (name, description) in labels.items():
        try:
            spec = challenge_level_spec(level)
        except FileNotFoundError:
            spec = {}
        result.append({"id": level, "name": name, "description": description,
                       "available": bool(spec), "policy": spec.get("model"),
                       "evaluation": spec.get("evaluation")})
    return result


def challenge_driver_catalog() -> list[dict]:
    display = {
        "v3_beginner": ("LEARNER", "入门", "#87c9ff"),
        "v3_standard": ("ATLAS", "标准", "#c6afff"),
        "v3_expert": ("VECTOR", "高手", "#bdf47c"),
        "v3_ppo": ("VECTOR-P", "PPO 对照", "#bdf47c"),
        "v3_dqn": ("APEX", "DQN 对照", "#ffad73"),
        "v3_a2c": ("PULSE", "A2C 对照", "#87c9ff"),
    }
    models = challenge_deployment().get("models", {})
    result = []
    for policy, (name, subtitle, color) in display.items():
        if policy not in models:
            continue
        spec = models.get(policy, {})
        try:
            challenge_model_spec(policy)
        except FileNotFoundError:
            spec = {}
        result.append({"id": policy, "name": name, "subtitle": subtitle, "algorithm": spec.get("algorithm", "ppo").upper(),
                       "color": color, "description": spec.get("description", spec.get("method", "在编队车流中训练并通过独立道路评估。")),
                       "available": bool(spec), "steps": spec.get("steps", 0),
                       "env_version": CHALLENGE_ENV_VERSION})
    return result


def challenge_training_catalog() -> dict | None:
    """A small, checked summary of the frozen experiment for the game UI."""
    manifest = challenge_deployment()
    evaluation = manifest.get("evaluation", {})
    relative = evaluation.get("report")
    if evaluation.get("status") != "complete" or not relative:
        return None
    report_path = (ROOT / relative).resolve()
    if not report_path.is_relative_to(ROOT) or not report_path.is_file():
        return None
    content = report_path.read_bytes()
    if hashlib.sha256(content).hexdigest() != evaluation.get("report_sha256"):
        return None
    try:
        report = json.loads(content)
        if report.get("stage") != "final" or report.get("env_version") != CHALLENGE_ENV_VERSION:
            return None
        names = {
            "beginner": "先学习驾驶示范，再自主练习",
            "standard": "在示范基础上加强安全训练",
            "expert": "继续训练已有策略，减少危险驾驶",
        }
        levels = {}
        for level, label in names.items():
            alias = manifest["levels"][level]["model"]
            record = report["models"][alias]
            spec = manifest["models"][alias]
            levels[level] = {"policy": alias, "method": spec.get("method_label") or label,
                             "checkpoint_steps": spec["steps"],
                             "training_steps": spec.get("training_steps", spec["steps"]),
                             "run_id": spec.get("run_id"), "algorithm": spec["algorithm"].upper(),
                             "checkpoint_sha256": spec["sha256"],
                             "overall": record["summary"],
                             "routes": record["by_scenario"]}
        paired = report["paired_game_outcomes"]
        refinement = manifest.get("refinement")
        expert_vs_rule = paired["expert_vs_rule"]["paired"]["all"]
        if refinement:
            selected = refinement["models"][refinement["official"]]
            levels["expert"].update(overall=selected["overall"], routes=selected["routes"])
            expert_vs_rule = refinement["expert_vs_rule"]
        return {"algorithm": manifest["models"][manifest["levels"]["expert"]["model"]]["algorithm"].upper(),
                "evaluation": "300 条独立测试道路，每关 100 条",
                "levels": levels,
                "comparison": report.get("algorithm_comparison", []),
                "improvement": report.get("improvement"),
                "refinement": public_summary(refinement) if refinement else None,
                "standard_vs_beginner": paired["standard_vs_beginner"]["paired"]["all"],
                "expert_vs_rule": expert_vs_rule}
    except (KeyError, TypeError, ValueError):
        return None
