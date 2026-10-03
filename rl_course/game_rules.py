"""Versioned rules shared by game sessions and offline policy evaluation."""
from __future__ import annotations

GAME_VERSION = "2.0.0"
ENV_VERSION = "2.0"
POLICY_FREQUENCY = 5

TRACKS = [
    {"id": "coast", "name": "海岸公路", "en": "COASTLINE", "scenario": "light", "duration": 30, "target_m": 650, "overtakes_target": 1, "theme": "coast", "difficulty": 1, "description": "舒展的海岸线，练习调速与第一次安全超车。", "brief": "保持车距，寻找一次从容的超车机会。", "objectives": ["安全完成 30 秒行程", "行驶 650 米", "安全超车 1 次"]},
    {"id": "metro", "name": "城市环线", "en": "METRO LOOP", "scenario": "normal", "duration": 45, "target_m": 950, "overtakes_target": 3, "theme": "city", "difficulty": 2, "description": "快慢车辆混行，在车道间选择合适的通行节奏。", "brief": "观察相邻车道，提前选择通行空间。", "objectives": ["安全完成 45 秒行程", "行驶 950 米", "安全超车 3 次"]},
    {"id": "rush", "name": "晚高峰", "en": "RUSH HOUR", "scenario": "dense", "duration": 45, "target_m": 850, "overtakes_target": 3, "theme": "sunset", "difficulty": 3, "description": "连续车流与更小的空隙，给换道留下反应时间。", "brief": "先确认前后车距，再进入相邻车道。", "objectives": ["安全完成 45 秒行程", "行驶 850 米", "安全超车 3 次"]},
    {"id": "endurance", "name": "长途巡航", "en": "LONG RUN", "scenario": "normal", "duration": 60, "target_m": 1320, "overtakes_target": 5, "theme": "coast", "difficulty": 3, "description": "持续补充的混合车流，考验整段行程的稳定发挥。", "brief": "连续完成多次安全超车，保持稳定节奏。", "objectives": ["安全完成 60 秒行程", "行驶 1320 米", "安全超车 5 次"]},
    {"id": "midnight", "name": "午夜环城", "en": "MIDNIGHT", "scenario": "dense", "duration": 60, "target_m": 1140, "overtakes_target": 4, "theme": "night", "difficulty": 4, "description": "灯火下的繁忙长途，车辆与道路规则和白天相同。", "brief": "在繁忙车流中兼顾安全、距离与超车。", "objectives": ["安全完成 60 秒行程", "行驶 1140 米", "安全超车 4 次"]},
]


def track_by_id(track_id: str) -> dict:
    for track in TRACKS:
        if track["id"] == track_id:
            return dict(track)
    raise ValueError("没有找到这条路线。")


def performance(track: dict, *, done: bool, crashed: bool, distance: float,
                overtakes: int, danger_seconds: float) -> dict:
    completed = bool(done and not crashed)
    qualified = bool(completed and distance >= track["target_m"])
    stars = int(completed) + int(qualified) + int(qualified and overtakes >= track.get("overtakes_target", 3))
    score = max(0, round(distance + 35 * overtakes + 300 * completed - 250 * crashed - 5 * danger_seconds))
    return {"completed": completed, "qualified": qualified, "score": score, "stars": stars}


def duel_outcome(player: dict, rival: dict | None) -> str | None:
    """Safe completion takes precedence over score, including late crashes."""
    if rival is None or not player["done"] or not rival["done"]:
        return None
    def rank(run):
        return (bool(run.get("completed", run["done"] and not run["crashed"])),
                bool(run.get("qualified", False)), run["score"])
    left, right = rank(player), rank(rival)
    return "win" if left > right else "loss" if left < right else "draw"
