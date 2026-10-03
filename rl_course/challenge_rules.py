"""The three formation challenges used by the version 3 duel."""
from __future__ import annotations

GAME_VERSION = "3.1.0"
ENV_VERSION = "3.1"
POLICY_FREQUENCY = 5

CHALLENGE_TRACKS = [
    {"id": "convoy", "name": "慢车编队", "en": "CONVOY", "scenario": "convoy",
     "env_version": ENV_VERSION, "duration": 35, "target_m": 790, "overtakes_target": 3,
     "theme": "coast", "difficulty": 2,
     "description": "连续慢车挡住主车道，观察邻道车距并寻找超车窗口。",
     "brief": "判断邻道前后车距，选择时机通过慢车。",
     "objectives": ["安全完成 35 秒行程", "行驶 790 米", "安全超车 3 次"]},
    {"id": "weave", "name": "交织车流", "en": "WEAVE", "scenario": "weave",
     "env_version": ENV_VERSION, "duration": 45, "target_m": 900, "overtakes_target": 3,
     "theme": "city", "difficulty": 3,
     "description": "邻道后车速度更快，超车前需要先判断汇入空隙。",
     "brief": "留意高速接近的后车，必要时先减速。",
     "objectives": ["安全完成 45 秒行程", "行驶 900 米", "安全超车 3 次"]},
    {"id": "pressure", "name": "连续高压", "en": "PRESSURE", "scenario": "pressure",
     "env_version": ENV_VERSION, "duration": 55, "target_m": 1270, "overtakes_target": 5,
     "theme": "sunset", "difficulty": 4,
     "description": "前方多车道受阻，后方车辆接近；长距离内持续处理车流。",
     "brief": "连续评估前方慢车和两侧后车，兼顾安全与通行效率。",
     "objectives": ["安全完成 55 秒行程", "行驶 1270 米", "安全超车 5 次"]},
]


def challenge_track_by_id(track_id: str) -> dict:
    for track in CHALLENGE_TRACKS:
        if track["id"] == track_id:
            return dict(track)
    raise ValueError("没有找到这条挑战路线。")
