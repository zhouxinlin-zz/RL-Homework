"""Build the offline defense deck and notes from the frozen project evidence.

Run from anywhere: python docs/defense/source/build.py
Uses the Python standard library; does not train, evaluate, or change reports.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
ROOT = HERE.parents[2]
EXPERIMENT = ROOT / "artifacts/experiments_v3/iteration_4"
REPORT = json.loads((EXPERIMENT / "report.json").read_text(encoding="utf-8"))
REPORT_HASH = hashlib.sha256((EXPERIMENT / "report.json").read_bytes()).hexdigest()
MODELS = REPORT["models"]
RUNS = {
    p.parent.name: json.loads(p.read_text(encoding="utf-8"))
    for p in EXPERIMENT.glob("*_s*/progress.json")
}
TOTAL_STEPS = sum(r["actual_steps"] for r in RUNS.values())
assert TOTAL_STEPS == 700816, "Evidence changed; review the narration before rebuilding."
EXPERT_PROGRESS = json.loads(
    (ROOT / "artifacts/experiments_v3/safe_transfer_s47/progress.json").read_text(encoding="utf-8")
)
assert EXPERT_PROGRESS["actual_timesteps"] == 501760

SLIDES: list[dict] = []


def head(kicker: str, title: str, lead: str = "") -> str:
    return (
        f'<div class="head" data-anim="head"><div class="t-meta">{kicker}</div>'
        f'<h2>{title}</h2>{f"<p class=lead>{lead}</p>" if lead else ""}</div>'
    )


def blocks(items: list[tuple[str, str, str, str]]) -> str:
    colors = ["b-grey", "b-ink", "b-accent"]
    return '<div class="stack-row">' + "".join(
        f'<article class="stack-block {colors[i]}" data-anim="step">'
        f'<div class="layer-nb">{tag}</div><h3 class="layer-ttl">{title}</h3>'
        f'<p class="layer-desc">{desc}</p><div class="layer-tag">{foot}</div></article>'
        for i, (tag, title, desc, foot) in enumerate(items)
    ) + "</div>"


def add(title, layout, theme, body, purpose, show, talk, transition, seconds, source, recipe="grid-reveal", custom=False):
    SLIDES.append(dict(title=title, layout=layout, theme=theme, body=body, purpose=purpose,
                       show=show, talk=talk, transition=transition, seconds=seconds,
                       source=source, recipe=recipe, custom=custom))


add(
    "变道之间", "SWISS-COVER-ASCII", "accent hero",
    '<canvas class="ascii-bg" aria-hidden="true"></canvas><div class="cover-main">'
    '<div data-anim="title"><h1 class="cover-title">LANE<br><i>SHIFT</i></h1>'
    '<p class="cover-subtitle">变道之间：强化学习驾驶对决</p></div>'
    '<div class="cover-rule" data-anim="rule"></div>'
    '<p class="cover-summary" data-anim="summary">在动态车流中，学习安全与效率的取舍。<br>'
    '从环境设计、策略训练，到可复现评估与交互展示。</p></div>',
    "一句话交代项目和研究问题。",
    "项目名 + 核心问题。封面不放技术栈或功能清单。",
    "我们的项目叫《变道之间》，是一款可以和强化学习策略同场比较的驾驶游戏。我们关心的不是车能不能一直向前走，而是在前方慢车、邻道后车和有限时间同时存在时，模型如何决定何时换道、何时加速、何时等待。接下来先看游戏，再说明策略怎样训练，以及我们怎样判断训练是否真的有效。",
    "先用一局游戏，把这个决策问题看清楚。", 25,
    "README.md；PROJECT_PLAN.md", "cover",
)

image_data = base64.b64encode((ROOT / "artifacts/preview/v3/3d-pressure.png").read_bytes()).decode("ascii")
add(
    "同一起点，两种驾驶", "S22", "light",
    '<div class="hero-img-wrap"><div class="hero-overlay-block" data-anim="title-block">'
    '<div class="t-meta">01 / 交互展示</div><h2>同一起点<br>两种驾驶</h2></div>'
    f'<img data-image-slot="s22-hero-21x9" src="data:image/png;base64,{image_data}" '
    'alt="实际游戏截图：左侧玩家、右侧 PPO，连续高压路况" data-anim="img"></div>'
    '<div class="image-hero-body" data-anim="kpi"><p>左侧由玩家操作，右侧由 PPO 决策。<br>'
    '初始车流相同，之后独立响应动作。<br>胜负先看安全，再看达标和得分。</p>'
    '<div class="image-hero-stats">'
    '<div><div class="number">55 s</div><div class="label">连续高压<br>短演示路线</div></div>'
    '<div><div class="number">5 Hz</div><div class="label">决策频率<br>双方相同</div></div>'
    '<div><div class="number">PPO</div><div class="label">正式对手<br>本地固定权重</div></div>'
    '</div></div>',
    "用真实界面说明项目是什么，并完成一次短演示。",
    "完整保留真实游戏截图。现场切换到游戏，选择连续高压；不以这局胜负证明模型能力。",
    "画面左侧是玩家，右侧是训练好的 PPO。双方面对相同的初始车流，使用相同的动作和速度范围，但进入不同车道后，后续交通会分别演化。我现在选择连续高压，演示约五十五秒。请注意右侧在接近慢车时，是选择等待还是寻找空隙。比赛先比较安全完赛，再比较里程达标，最后比较得分。演示展示的是策略行为，后面会用三百局未见道路来评价稳定性。",
    "刚才看到的等待和换道，来自我们设计的三类交通挑战。", 85,
    "artifacts/preview/v3/3d-pressure.png；rl_course/driving_env_v3.py；rl_course/game_rules.py",
    "image-hero", True,
)

add(
    "挑战来自车流关系", "S05", "light",
    head("02 / 环境设计", "挑战来自车流关系", "持续生成交通编队，让选择车道与时机成为整段行程的问题。")
    + blocks([
        ("CONVOY", "慢车编队", "前方慢车阻挡通行。<br>判断何时离开当前车道。", "35 秒 · 790 米"),
        ("WEAVE", "交织车流", "邻道后车快速接近。<br>同时观察前方与后方。", "45 秒 · 900 米"),
        ("PRESSURE", "连续高压", "多车道受阻并持续补车。<br>在安全窗口中争取效率。", "55 秒 · 1270 米"),
    ]),
    "解释关卡为什么能够考验决策，而不只是换背景。",
    "三种路况并列；每种只说一个主要矛盾。",
    "三关的差异来自车辆之间的关系。慢车编队主要要求主动寻找超车机会；交织车流加入邻道快速接近的后车，不能只看前方空不空；连续高压会持续补充车流，要求长时间兼顾安全和进度。每关都有里程目标，所以一直慢速跟车虽然可能不撞，也不一定达标。环境是在 HighwayEnv 上扩展的，场景美术不参与模型的判断。",
    "要学习这些决策，先把环境变成模型能够读取的状态和动作。", 40,
    "rl_course/driving_env_v3.py：交通编队、持续补车；challenge_rules.py：关卡目标",
)

add(
    "把驾驶写成学习任务", "S05", "hero light",
    head("03 / 状态与动作", "把驾驶写成学习任务", "状态输入 → 策略网络 → 高层驾驶动作")
    + blocks([
        ("OBSERVATION", "30 维状态", "本车 6 维。<br>三车道各 8 维前后车信息。<br>距离、速度与侧向运动。", "结构化数值输入 · 不读取截图"),
        ("POLICY", "两层 MLP", "策略分支输出动作概率。<br>价值分支估计长期回报。<br>各分支隐藏层 128 → 128。", "训练使用价值估计 · 比赛执行策略"),
        ("ACTION", "5 种动作", "左换道 · 保持 · 右换道<br>加速 · 减速<br>每秒做 5 次决策。", "底层物理仿真 15 Hz"),
    ]),
    "把观察、网络、动作三个基本概念讲清。",
    "三段流程。明确是数值状态 MLP，不是视觉大模型。",
    "模型每次读取三十个数。其中六个描述本车，其余描述三个车道最近的前后车，包括距离、相对速度和横向运动。策略网络输出五个动作的概率；训练时，价值网络帮助判断一个动作对未来是否有利。两条网络分支都使用两层一百二十八单元的 MLP。模型不读取游戏截图，也不调用大语言模型 API。每秒决策五次，仿真在更细的物理时间步执行这些指令。",
    "有了输入和动作，下一步是让模型通过反复交互改进选择。", 45,
    "rl_course/driving_env.py：LaneObservation；已部署 PPO 权重中的 policy_kwargs",
)

add(
    "从交互反馈中更新策略", "S14", "hero dark",
    head("04 / 强化学习闭环", "从交互反馈中更新策略")
    + '<div class="loop-diagram"><ol class="loop-steps">'
    '<li data-anim="step"><span class="step-number">01</span><span>观察车流，按当前策略选择动作。</span></li>'
    '<li data-anim="step"><span class="step-number">02</span><span>仿真执行，获得新状态和奖励。</span></li>'
    '<li data-anim="step"><span class="step-number">03</span><span>收集一批经历，估计动作的长期优势。</span></li>'
    '<li data-anim="step"><span class="step-number">04</span><span>PPO 限制过大的更新，再继续交互。</span></li>'
    '</ol><div class="loop-graphic" data-anim="loop">'
    '<svg class="loop-svg" viewBox="0 0 400 300" aria-hidden="true"><ellipse cx="200" cy="150" rx="155" ry="115"/>'
    '<path d="M348 108 l12 17 l-20 -2 M52 192 l-12 -17 l20 2"/></svg>'
    '<div class="loop-label top">观察状态</div><div class="loop-label right">选择动作</div>'
    '<div class="loop-label bottom">环境反馈</div><div class="loop-label left">更新策略</div>'
    '<div class="loop-center">PPO</div></div></div>'
    '<p class="chart-note">训练时更新参数；比赛时只加载权重做推理。</p>',
    "用闭环解释自动训练，不把训练说成手写驾驶规则。",
    "左侧四步说明，右侧闭环。详细 PPO 公式放在备答说明，不占正文。",
    "训练是自动进行的。模型先按当前策略驾驶，环境返回进度、安全风险等反馈。收集一批经历后，用价值估计计算哪些动作比预期更好，再提高这些动作在类似状态下出现的概率。PPO 的核心思路是限制新策略偏离旧策略过多，减少一次更新过大的问题。这个过程反复执行。课堂运行时不再训练，只加载已经选好的权重，因此现场表现可复现，也不会因为玩家的一次操作临时改变网络。",
    "模型究竟在追求什么，主要由奖励定义。", 50,
    "rl_course/train_v3.py；Stable-Baselines3 PPO 文档（参考链接见讲稿）",
    "loop-form",
)

add(
    "奖励定义驾驶偏好", "S08", "light",
    head("05 / 奖励设计", "奖励定义驾驶偏好", "正式高手与效率候选使用不同奖励设置；游戏计分规则保持一致。")
    + '<div class="duo-compare"><div class="col" data-anim="left">'
    '<div class="col-tag">正式高手 / v3.1</div><h3 class="col-ttl">先学会安全通行</h3>'
    '<p class="col-desc">奖励前进、有效超车与完赛。<br>惩罚危险跟车、冒险换道和反复变道。</p>'
    '<ul class="col-list"><li>每米 +0.025；每次超车 +0.4</li><li>事故惩罚项合计 −30</li></ul></div>'
    '<div class="vrule"></div><div class="col accent" data-anim="right">'
    '<div class="col-tag">效率候选 / ITERATION 4</div><h3 class="col-ttl">再提高通行效率</h3>'
    '<p class="col-desc">提高前进和超车的正反馈。<br>同时加重事故惩罚，观察真实取舍。</p>'
    '<ul class="col-list"><li>未碰撞且在道路上：额外每米 +0.035、超车 +0.2</li><li>事故惩罚项提高至 −60</li></ul></div></div>',
    "解释保守行为和奖励改进，同时分清已部署模型与候选。",
    "双栏对照；只保留关键数值。事故惩罚是奖励中的一项，不是整步奖励。",
    "如果只强调不撞车，模型容易学会减速等待。正式高手通过前进、超车和完赛奖励鼓励通行，同时惩罚危险行为。后续实验进一步提高前进和超车奖励，并把事故惩罚加重，希望模型在安全前提下更积极。不过，增加惩罚系数不意味着碰撞一定减少，策略会改变，我们必须重新测试。这里左侧是正式高手使用的奖励，右侧是新候选实验，不能混为一谈。训练奖励也不同于游戏结算分数。",
    "接下来说明正式模型的来源，以及训练量怎样统计。", 45,
    "rl_course/driving_env.py：_reward；driving_env_v3.py；train_challenge_models.py：TrainingRoad",
    "duo-compare",
)

add(
    "训练记录可以追溯", "S02", "light",
    head("06 / 模型来源", "训练记录可以追溯")
    + '<div class="timeline-v" data-anim="timeline">'
    '<div class="tl-node"><span class="dot"></span><span class="yr">已有 PPO</span><span class="multi">迁移初始化</span><span class="desc">v2 模型 → v3 车流编队 → v3.1 安全微调</span></div>'
    '<div class="tl-node"><span class="dot"></span><span class="yr">安全微调</span><span class="multi">501,760 步</span><span class="desc">safe_transfer_s47 的完整交互记录；另有上游训练</span></div>'
    '<div class="tl-node accent"><span class="dot"></span><span class="yr">正式部署</span><span class="multi">175,000 步</span><span class="desc">选中的检查点位置，不是全部训练预算</span></div></div>'
    '<div class="kpi-row-4" data-anim="kpi">'
    '<div class="kpi-cell"><div class="lbl">向量化环境</div><div class="nb">4</div><p class="note">CPU 收集交互</p></div>'
    '<div class="kpi-cell"><div class="lbl">每轮采样</div><div class="nb">2,048</div><p class="note">4 × 512 条交互</p></div>'
    '<div class="kpi-cell"><div class="lbl">每批样本</div><div class="nb">256</div><p class="note">PPO 小批量更新</p></div>'
    '<div class="kpi-cell"><div class="lbl">每轮优化</div><div class="nb">8</div><p class="note">epoch</p></div></div>',
    "避免把检查点步数误报为全部训练量。",
    "上半页来源链，下半页最必要的训练配置。训练曲线另见游戏训练成果与归档。",
    "正式模型不是从零开始只训练十七万五千步。它先继承早期 PPO，再迁移到结构化车流，最后完成安全奖励下的微调。最后一段累计交互五十万一千七百六十步，实际部署的是其中十七万五千步的检查点。我们根据开发道路表现选择，而不是默认越晚越好。四个环境各采集五百一十二步后，组成一批经历；每批二百五十六条，重复八轮优化。配置、检查点和开发指标都有归档。",
    "在这个正式模型之外，我们还尝试了几种提高效率的候选方案。", 45,
    "artifacts/experiments_v3/safe_transfer_s47/{config,progress}.json；deployment.json",
    "timeline",
)

add(
    "三种算法各回答什么", "S05", "dark",
    head("07 / 对照实验", "三种算法各回答什么", f"本轮五次运行新增 {TOTAL_STEPS:,} 步交互，保留各自初始化来源。")
    + blocks([
        ("PPO / 已有策略微调", "稳定更新策略", "从正式高手出发。<br>检验新奖励能否改善效率。", "本轮 200,704 步"),
        ("DQN / 从零后续训", "学习动作价值", "经验回放与目标网络。<br>提供另一类学习方法作对照。", "125,008 + 200,000 步"),
        ("A2C / 两种初始化", "比较策略更新", "从零训练；另试 PPO 权重初始化。<br>后续均使用 A2C 更新。", "125,056 + 50,048 步"),
    ]),
    "说明三个模型的用途，诚实描述不等预算比较。",
    "三个训练方案；网络权重来源与算法更新规则分别解释。",
    "PPO 候选从正式高手微调，检验新奖励能否让已有策略更积极。DQN 学习每个动作的长期价值，通过经验回放训练；我们先从零训练，再继续训练。A2C 是另一种策略与价值联合学习的方法，既试了从零，也试了用 PPO 的网络权重初始化，再按 A2C 规则更新。五次运行新增七十万零八百一十六步。由于初始化和预算不一致，这里比较的是本项目候选方案，不能把它说成严格公平的算法排名。",
    "有了多个检查点，关键是避免只挑最好看的一次结果。", 45,
    "iteration_4/*/progress.json；train_challenge_models.py；SB3 PPO / DQN / A2C 文档",
)

nodes = [
    ("01", "训练中验证", "36 局开发道路"),
    ("02", "扩大复核", "96 局开发道路"),
    ("03", "冻结候选", "锁定权重与哈希"),
    ("04", "独立测试", "每策略 300 局"),
    ("05", "发布验收", "检查安全与效率"),
]
timeline = '<div class="timeline-h" data-anim="timeline"><div class="tl-row">' + "".join(
    f'<div class="th-node {"up" if i % 2 == 0 else "down"} {"accent" if i == 2 else ""}">'
    f'<div class="dot"></div><div class="label"><span class="yr">{n}</span>'
    f'<span class="name">{name}</span><span class="desc">{desc}</span></div></div>'
    for i, (n, name, desc) in enumerate(nodes)
) + "</div></div>"
add(
    "先冻结，再看独立结果", "S11", "hero light",
    head("08 / 评估协议", "先冻结，再看独立结果") + timeline
    + '<p class="protocol-bottom">三关 × 100 个未见种子 = 每策略 300 局。<br>'
    '同一组初始道路，同时比较碰撞、达标率与得分。</p>',
    "证明成绩来自预先冻结的模型和完整测试，而非手选展示片段。",
    "五个步骤。讲清开发集选检查点，测试集只用于冻结后的验收。",
    "训练中先用三十六局开发道路观察表现，再用另一组九十六局复核，锁定每种算法的检查点以及升级候选。之后才使用新的测试种子，每关一百局，每个策略共三百局。所有策略面对相同初始道路，记录逐局成绩。发布程序还检查权重哈希和道路覆盖。这组测试决定冻结候选是否通过升级门槛，不用来反复挑另一个检查点。以后如果根据这些结果继续改模型，还要更换新的测试道路。",
    "下面的数字全部来自这同一组独立道路。", 45,
    "iteration_4/selection.json、report.json、test_*.json；release_challenge_models.py",
    "timeline-horizontal",
)

bar_rows = []
for key, label in [("v3_expert", "正式 PPO"), ("v3_ppo", "PPO 候选"), ("v3_dqn", "DQN 候选"),
                   ("v3_a2c", "A2C 候选"), ("rule", "规则驾驶")]:
    stats = MODELS[key]["summary"]
    rate = stats["qualification_rate"] * 100
    bar_rows.append(
        f'<div class="row-lbl">{label}</div><div class="row-track">'
        f'<div data-anim="bar" class="row-fill {"accent" if key == "v3_expert" else ""}" style="width:{rate:.4f}%"></div></div>'
        f'<div class="row-val">{rate:.1f}%</div><div class="crash">{stats["crashes"]} / {stats["episodes"]}</div>'
    )
add(
    "效率提升伴随安全代价", "S07", "light",
    head("09 / 独立测试结果", "效率提升伴随安全代价")
    + '<div class="h-bar-chart"><div class="column-head">策略</div><div class="column-head">达标率 · 横轴 0–100%</div>'
    '<div class="column-head">达标率</div><div class="column-head">碰撞局数</div>'
    + "".join(bar_rows) + '</div><p class="chart-note">'
    '正式 PPO 比规则驾驶高 <span class="accent-text">9.0 个百分点</span>。<br>'
    'A2C 达标更多，但新增碰撞，未通过升级门槛。</p>',
    "同时呈现安全与效率，给出保留正式 PPO 的证据。",
    "五行达标率条形图，右侧同排标碰撞局数；不要只读最高的百分比。",
    "每个策略都测试了三百局。正式 PPO 达标率百分之七十二点三，这组道路中没有观测到碰撞；规则基线是百分之六十三点三。效率候选里，A2C 达标率达到百分之七十九，但发生五次碰撞。PPO 候选也提高了达标率，同时出现八次碰撞。DQN 在这套训练设置下表现较弱。我们预设的升级要求是达标和得分提高、碰撞不增加，所以最终仍部署原 PPO。这不是把最高分模型直接拿来展示。",
    "平均结果之外，我们还单独检查最困难的路况。", 55,
    "iteration_4/report.json：models.*.summary；每策略 n=300；达标=安全完赛且满足里程",
    "h-bar",
)

def pressure_col(key, label, explanation, accent=False):
    stats = MODELS[key]["by_scenario"]["pressure"]
    return (
        f'<div class="col {"accent" if accent else ""}" data-anim="column">'
        f'<div class="col-tag">{label}</div><h3 class="col-ttl">{explanation}</h3>'
        f'<div class="metric-pair"><div><div class="value">{stats["qualification_rate"]*100:.0f}%</div>'
        f'<div class="caption">里程达标</div></div><div><div class="value">{stats["crashes"]}/100</div>'
        '<div class="caption">碰撞局数</div></div></div></div>'
    )

add(
    "高压路况仍是瓶颈", "S08", "light",
    head("10 / 失败分析", "高压路况仍是瓶颈", "安全通过不等于有效通行；整体均值会掩盖最难的一关。")
    + '<div class="duo-compare">'
    + pressure_col("v3_expert", "正式 PPO", "更稳，但仍偏保守")
    + '<div class="vrule"></div>'
    + pressure_col("v3_a2c", "A2C 候选", "更高达标，也有事故", True)
    + '</div><p class="chart-note">下一步围绕高压失败案例改进，使用新测试道路验证。<br>'
    '本次零碰撞是样本结果，不能理解为安全保证。</p>',
    "展示对失败和局限的理解，避免声称模型问题已全部解决。",
    "同一关的 100 局，PPO 与 A2C 各给两个数。",
    "连续高压更能暴露问题。正式 PPO 只有百分之三十二达标，没有观测到碰撞；A2C 达标提高到百分之四十三，但有四次碰撞。我们能够确认的是安全和效率还没有同时解决，不能只因为总体达标率提高就宣布成功。后续应分析失去超车窗口、过早减速和冒险换道等失败案例，再针对性改奖励、采样和训练。是否优于人类也需要专门收集基准，目前一次现场对决无法回答这个问题。",
    "最后用三点总结本项目已经完成的工作与结论。", 45,
    "iteration_4/report.json：models.v3_expert / v3_a2c.by_scenario.pressure；各 n=100",
    "duo-compare",
)

add(
    "总结：学习、验证、展示", "SWISS-CLOSING-ASCII", "split",
    '<div class="split-half"><div class="half b-accent"><canvas class="ascii-bg" aria-hidden="true"></canvas>'
    '<div class="chrome-min"><span>LANE SHIFT / 总结</span></div>'
    '<h2 class="closing-title" data-anim="title">让策略<br>做出选择<br><i>让证据回答</i></h2>'
    '<p class="cover-summary" style="max-width:100%">强化学习驾驶对决</p></div>'
    '<div class="half"><div class="chrome-min"><span>CONCLUSION</span><span>12 / 14</span></div>'
    '<ol class="takeaways">'
    '<li data-anim="item"><h3>构建可学习的任务</h3><p>结构化车流、状态动作设计、奖励与交互展示形成完整流程。</p></li>'
    '<li data-anim="item"><h3>用实验选择模型</h3><p>PPO 为正式对手；多算法对照说明效率提升与事故之间的取舍。</p></li>'
    '<li data-anim="item"><h3>明确目前的边界</h3><p>高压关仍待改善；尚无足够证据支持“超过人类”。</p></li>'
    '</ol></div></div>',
    "用完整项目流程与证据意识收束，而非堆功能或夸大算法贡献。",
    "三条结论；正常讲述在此结束，后两页仅用于备答。",
    "总结来说，我们完成了从交通任务、奖励设计、策略训练，到独立评估和人机对决展示的完整流程。模型方面，当前 PPO 提供了较稳定的正式对手，多算法候选揭示了效率改进可能带来新的安全代价。项目还没有解决连续高压下的全部问题，也没有证明超过人类。我们的主要收获是，不只让模型跑起来，还能解释它怎么训练、如何选用，以及在哪些情况下仍然不足。",
    "正文结束。根据提问选择后面的参数页或问题页。", 30,
    "README.md；iteration_4/report.json 与 release.json", "closing", True,
)

specs = [
    ("网络", "30 维输入<br>128 → 128 隐藏层<br>5 维动作概率<br>独立价值分支"),
    ("采样", "4 个向量环境<br>每环境 512 步<br>共 2048 条交互<br>每批 256 条"),
    ("更新", "学习率 3e−4<br>折扣率 0.99<br>GAE 0.95<br>每轮 8 epoch"),
    ("约束与探索", "PPO 裁剪 0.2<br>熵系数 0.008<br>仅训练时更新<br>推理确定性选动作"),
]
add(
    "备答：正式 PPO 配置", "S19", "hero light",
    head("APPENDIX A / 按需展开", "正式 PPO 配置")
    + '<div class="four-cards">' + "".join(
        f'<div class="fc-col" data-anim="spec"><div class="t-meta">0{i+1}</div>'
        f'<h3>{title}</h3><p>{desc}</p></div>' for i, (title, desc) in enumerate(specs)
    ) + "</div>",
    "回答具体参数，不在正文逐项背诵。",
    "参数来自实际加载的正式权重，不是文档默认值。",
    "这一页列的是已部署 PPO 权重保存的配置。四个向量环境每次合计采样二千零四十八条交互，再进行小批量更新。零点九九折扣率用于累计未来奖励，GAE 用来估计优势；裁剪系数限制策略概率比的更新幅度，熵项鼓励探索。这些是本项目的实际设置，不意味着是所有交通场景的最优参数。候选 PPO、DQN、A2C 的学习率和训练方式另有记录，不能套用这页。",
    "如果被追问公式，结合讲稿中的 PPO 目标说明；不需要逐项推导。", 0,
    "v3_expert-b4f0d5f66de4.zip：PPO.load 后读取属性；train_v3.py",
    "four-cards",
)

qa_short = [
    ("AI 会现场学习吗？", "不会。训练已完成，现场加载固定模型做推理。"),
    ("三个算法一起开车？", "不会。比赛只有正式 PPO；其他模型用于离线对照。"),
    ("为什么不选 A2C？", "达标率提高，但碰撞增加，没有通过预设升级门槛。"),
    ("零碰撞等于安全？", "只代表这 300 局的观测结果，不保证其他道路零风险。"),
    ("已经超过人类吗？", "尚未建立系统人类基准，现场一局不能证明。"),
    ("项目贡献在哪里？", "环境、奖励、训练评估与交互整合；算法采用 SB3 实现。"),
]
add(
    "备答：常见问题", "S16", "light",
    head("APPENDIX B / 按需展开", "常见问题")
    + '<div class="brief-grid">' + "".join(
        f'<article class="brief-card {"card-accent" if i == 2 else "card-fill"}" data-anim="qa">'
        f'<h3>{q}</h3><p>{a}</p></article>' for i, (q, a) in enumerate(qa_short)
    ) + "</div>",
    "为高频追问准备简明且能被代码与记录支持的回答。",
    "六个问题，按提问选读，不作为正文继续讲完。",
    "回答时先给结论，再指出依据。例如，问为什么保留 PPO，就解释事先设定的安全门槛和同道路测试；问能不能超过人类，就明确目前缺少系统人类基准。不要把候选初始化方式省略，也不要把成熟算法本身说成我们提出的新算法。",
    "需要更细的数字时回到第 10、11 页，或打开训练成果。", 0,
    "server/catalog.py；iteration_4/report.json、release.json；README.md",
    "field-notes",
)


def chrome(i: int) -> str:
    return f'<div class="chrome-min"><span class="l">LANE SHIFT / 强化学习课程项目</span><span class="r">{i:02d} / {len(SLIDES):02d}</span></div>'


pages = []
for i, s in enumerate(SLIDES, 1):
    body = s["body"]
    if s["layout"] == "S22":
        body = body.replace('<div class="hero-img-wrap">', '<div class="hero-img-wrap">' + chrome(i))
        inner = '<div class="canvas-card image-hero-card">' + body + "</div>"
    elif s["layout"] == "SWISS-CLOSING-ASCII":
        inner = '<div class="canvas-card">' + body + "</div>"
    elif s["layout"] == "SWISS-COVER-ASCII":
        body = body.replace('</canvas>', '</canvas>' + chrome(i), 1)
        inner = '<div class="canvas-card">' + body + "</div>"
    else:
        inner = '<div class="canvas-card">' + chrome(i) + '<div class="body-area">' + body + f'<p class="source">依据：{html.escape(s["source"])}</p></div></div>'
    pages.append(f'<section class="slide {s["theme"]}" data-title="{html.escape(s["title"])}" data-layout="{s["layout"]}" data-animate="{s["recipe"]}" id="slide-{i}">{inner}</section>')

css = "\n".join((HERE / name).read_text(encoding="utf-8") for name in ("theme.css", "defense.css"))
js = (HERE / "deck.js").read_text(encoding="utf-8")
deck = (
    '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    '<meta name="description" content="LANE SHIFT 强化学习课程项目答辩：环境、奖励、训练、评估与交互展示">'
    '<title>LANE SHIFT · 变道之间｜答辩初稿</title><style>' + css + '</style></head>'
    '<body class="canvas-mode low-power"><main id="deck">' + "\n".join(pages) + '</main>'
    '<nav id="nav" aria-label="幻灯片导航"></nav><div class="nav-buttons">'
    '<button id="prev" aria-label="上一页">←</button><button id="contents">目录</button><button id="next" aria-label="下一页">→</button></div>'
    '<div id="hint">← → 翻页 · F 全屏 · Esc 目录 · B 静态</div>'
    '<aside id="overview" hidden><h2>答辩目录 <button id="close-index">返回</button></h2><div class="index-list"></div></aside>'
    '<script>' + js + '</script></body></html>'
)
(OUT / "LANE-SHIFT-defense.html").write_text(deck, encoding="utf-8")

faq = [
    ("PPO 的目标函数怎么解释？",
     "核心裁剪目标可写为 E[min(ρₜAₜ, clip(ρₜ, 1−ε, 1+ε)Aₜ)]，其中 ρₜ 是同一动作在新旧策略下的概率比，Aₜ 是优势估计。直观上，好的动作增加概率，但不要一步改变太大。实现还包含价值损失与熵项。PPO 的裁剪不是碰撞安全约束，不能保证车辆不撞。"),
    ("奖励和得分为什么不一样？",
     "奖励是每步优化信号，包含风险、换道等稠密反馈；游戏分数用于结算，强调可理解的里程、超车、完赛和风险时间。达标率要求安全完赛且达到目标里程，超车目标影响星级；胜负先比较完赛和达标，再看分数。"),
    ("三百局零碰撞，为什么还说没有解决？",
     "有限测试只表明这些道路上没有观测到事故，不证明其他道路或训练种子同样安全。正式 PPO 高压达标只有 32%，说明安全之外的效率问题仍明显。"),
    ("A2C 比 PPO 赢得更多，为什么不替换？",
     "A2C 同道路对正式 PPO 为 217 胜、72 负、11 平，但其碰撞为 5/300，正式 PPO 为 0/300。对决胜率和事故率回答不同问题；升级门槛要求达标、均分提高且碰撞不增加。候选虽然多数局更有效率，仍未满足预设安全要求。"),
    ("既然用了已有库，我们做了什么？",
     "HighwayEnv 提供交通仿真基础，SB3 提供成熟算法；本项目完成结构化编队和持续补车、状态与奖励设计、迁移及候选训练、开发选模和冻结评估、模型身份校验，以及本地人机对决可视化。不把 PPO、DQN、A2C 说成原创算法。"),
    ("为什么不用摄像头或端到端视觉？",
     "本项目关注驾驶决策和策略评估，使用结构化状态减少感知误差，便于分析奖励与行为的关系。代价是简化了任务，也使 AI 与看画面的人类输入形式不同，因此不能直接称为严格的人类能力排名。"),
    ("用 PPO 权重初始化 A2C，还算 A2C 吗？",
     "初始化使用 PPO 的策略和价值网络参数；之后采样与参数更新由 A2C 实现执行。所以可称为 PPO 初始化的 A2C 候选，必须说明迁移来源，不能说成完全从零训练的 A2C。代码参数名 actor-from-ppo 只是一种命名，实际复制整个 policy 的状态字典。"),
    ("为什么训练更多步没有选最后一个？",
     "强化学习表现可能波动，更多更新可能破坏已有行为。正式检查点由开发道路选出，完整安全微调为 501,760 步，部署检查点为 175,000 步。候选 PPO 的 25,000 步也只是本次微调中的位置，不包含上游训练。"),
    ("这是不是完全公平的算法比较？",
     "测试道路、动作空间和计分统一，但初始化、预算和超参数不同，且未做多训练随机种子的统计比较。因此结论只适用于当前候选配置；若研究算法本身，需要统一预算、控制初始化、增加训练种子并报告不确定性。"),
    ("怎么防止测试集泄漏？",
     "开发集选择检查点和升级候选，写入 selection.json 后再跑独立测试。当前测试用于冻结候选的发布验收，未通过就保留原高手，不回头挑另一权重。今后若依据本次测试继续改模型，应建立新的未见道路测试集。"),
    ("如何解释 AI 减速？",
     "减速可能是对近距离车辆的合理反应，也可能是安全惩罚下的过度保守。要同时看周车状态、达标率和失败回放，不能只看一秒钟的速度。候选实验增加效率奖励，但碰撞也增加，这正是当前尚未解决的取舍。"),
    ("下一步最值得做什么？",
     "先分类高压关失败：错过安全窗口、长期跟车、冒险汇入等；再有针对性地调整困难场景采样或奖励，固定更公平的训练预算，保留新的测试道路验收。若要回答人类水平，需收集足量受试者、多关卡、多次尝试及统一操作规则。"),
]

notes_css = """
*{box-sizing:border-box}body{margin:0;background:#f6f6f3;color:#151515;font-family:"Microsoft YaHei UI","Segoe UI",sans-serif;line-height:1.85}
main{max-width:980px;margin:0 auto;padding:50px 44px 90px}h1{font-size:36px;font-weight:500;line-height:1.45}h2{font-size:26px;font-weight:500;margin:32px 0 12px}h3{font-size:19px;margin:22px 0 6px}
p{margin:10px 0}a{color:#002fa7}header{border-bottom:4px solid #002fa7;padding-bottom:28px}
article{padding:25px 0 32px;border-bottom:1px solid #bbb;break-inside:avoid}blockquote{margin:18px 0;padding:18px 24px;background:white;border-left:3px solid #002fa7;font-size:18px;line-height:1.9}
.meta{font-size:14px;color:#535353}.label{font-size:14px;letter-spacing:.08em;color:#002fa7;font-weight:600}.transition{font-style:italic}
nav{display:grid;grid-template-columns:1fr 1fr;gap:8px 28px;margin:24px 0}nav a{text-decoration:none;border-bottom:1px solid #ddd;padding:7px 0}
code{font-family:Consolas,monospace;overflow-wrap:anywhere}li{margin:8px 0}details{padding:12px 0;border-bottom:1px solid #ccc}summary{font-size:18px;cursor:pointer}
@media print{body{background:white}main{max-width:none;padding:0}header,nav{break-inside:avoid}details{display:block}details p{display:block}a{color:inherit}blockquote{font-size:12pt}h2{break-after:avoid}article{break-inside:auto}@page{size:A4;margin:18mm}}
"""
toc = "".join(f'<a href="#page-{i}">{i:02d}　{html.escape(s["title"])}</a>' for i, s in enumerate(SLIDES, 1))
articles = []
for i, s in enumerate(SLIDES, 1):
    articles.append(
        f'<article id="page-{i}"><div class="label">第 {i:02d} 页 / {"正文" if i <= 12 else "备答"}</div>'
        f'<h2>{html.escape(s["title"])}</h2><p class="meta">建议时间：{str(s["seconds"])+" 秒" if s["seconds"] else "根据提问选讲"}'
        f' · <a href="LANE-SHIFT-defense.html#{i}">打开这一页</a></p>'
        f'<p><strong>这一页要说明：</strong>{html.escape(s["purpose"])}</p>'
        f'<p><strong>页面与操作：</strong>{html.escape(s["show"])}</p>'
        f'<h3>可照读讲稿</h3><blockquote>{html.escape(s["talk"])}</blockquote>'
        f'<p class="transition"><strong>过渡：</strong>{html.escape(s["transition"])}</p>'
        f'<p class="meta"><strong>核对依据：</strong><code>{html.escape(s["source"])}</code></p></article>'
    )
faqs = "".join(f'<details open><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>' for q, a in faq)
notes = (
    '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    '<title>LANE SHIFT｜逐页答辩提纲与讲稿</title><style>' + notes_css + '</style></head><body><main>'
    '<header><div class="label">LANE SHIFT / DEFENSE NOTES</div><h1>逐页答辩提纲与讲稿</h1>'
    '<p>12 页正文 + 2 页备答。按目前讲稿约 8–10 分钟，含约 1 分钟实机展示；具体随语速和操作略有变化。</p>'
    '<p>讲述顺序：看见任务 → 理解建模 → 解释训练 → 检查证据 → 讨论边界。页面只放核心内容，下面的讲稿用于预演或放在第二屏。</p>'
    '<p><a href="LANE-SHIFT-defense.html">打开离线幻灯片</a> · <a href="LANE-SHIFT-defense.pdf">打开 PDF</a> · <a href="../../README.md">项目说明</a></p></header>'
    '<h2>使用与预演</h2><ul>'
    '<li>双击网页幻灯片，F 全屏，左右键翻页；Esc 目录，B 静态。PDF 可作为备用，两者均不需要联网。</li>'
    '<li>先运行 Start-Game.cmd 与 Check-Game.cmd；让游戏和幻灯片同时打开。第 2 页切到游戏，从“选择起始路线”进入连续高压。</li>'
    '<li>操作阶段只解释换道、减速和结算；不同时展开设置、记录和算法页面。若时间不足，截图说明玩法，直接进入训练与评估部分。</li>'
    '<li>演示输赢都可以正常讲：这是行为展示，不是预设 AI 必胜。需要讨论泛化时引用第 10、11 页的独立测试。</li>'
    '<li>若只有 5 分钟：讲第 1、2、4、5、9、10、12 页，实机压缩为 20 秒观察；不要临时修改测试数字。</li>'
    '</ul><nav>' + toc + '</nav>' + "".join(articles)
    + '<h2 id="faq">常见追问：完整回答</h2>' + faqs
    + '<h2>数字口径与证据</h2><ul>'
    '<li>独立测试：种子 1631100–1631199，三关各 100 局。图表只引用 iteration_4/report.json，不与 evaluation_final 的另一组种子混算。</li>'
    '<li>正式 PPO：72.3%、0/300；规则：63.3%、0/300；PPO 候选：78.3%、8/300；DQN：56.7%、65/300；A2C：79.0%、5/300。</li>'
    '<li>高压关：正式 PPO 32%、0/100；A2C 43%、4/100。百分比保留一位时可能有四舍五入。</li>'
    '<li>新增五次训练合计 700,816 步。正式模型的 501,760 步为 safe_transfer_s47 完整记录，175,000 为部署检查点。均不应等同于包含上游的总预算。</li>'
    f'<li>本材料生成时 report.json 的 SHA-256：<code>{REPORT_HASH}</code>。</li>'
    '<li>原始数据：<a href="../../artifacts/experiments_v3/iteration_4/report.json">报告</a>、'
    '<a href="../../artifacts/experiments_v3/iteration_4/selection.json">冻结选择</a>、'
    '<a href="../../artifacts/experiments_v3/iteration_4/release.json">发布结果</a>。源码与证据路径在每页讲稿下方标注。</li></ul>'
    '<h2>外部参考</h2><p>算法原理使用成熟实现，项目成绩来自本地冻结实验，不来自外部基准。</p><ul>'
    '<li><a href="https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html">Stable-Baselines3：PPO（裁剪更新、采样与参数）</a></li>'
    '<li><a href="https://stable-baselines3.readthedocs.io/en/master/modules/dqn.html">Stable-Baselines3：DQN（经验回放与目标网络）</a></li>'
    '<li><a href="https://stable-baselines3.readthedocs.io/en/master/modules/a2c.html">Stable-Baselines3：A2C（优势 actor-critic）</a></li>'
    '<li><a href="https://highway-env.farama.org/">HighwayEnv：交通仿真环境</a></li>'
    '<li><a href="https://arxiv.org/abs/1707.06347">Schulman 等：Proximal Policy Optimization Algorithms，2017</a></li></ul>'
    '<h2>修改材料</h2><p>编辑 <code>docs/defense/source/build.py</code> 中的逐页内容，执行 '
    '<code>.venv\\Scripts\\python.exe docs/defense/source/build.py</code> 重建网页与讲稿。配色和布局在同目录 CSS，翻页在 deck.js。'
    'PDF 导出脚本为 <code>docs/defense/source/export.mjs</code>，需要 web 的 Playwright 开发依赖与 Edge。'
    '源文件采用 Swiss 模板的排版基础；最终网页已内嵌样式、脚本和截图，可以单文件离线展示。</p>'
    '</main></body></html>'
)
(OUT / "defense-notes.html").write_text(notes, encoding="utf-8")
print(f"Built {len(SLIDES)} slides and matching notes; main talk {sum(s['seconds'] for s in SLIDES)} seconds.")
print(f"Frozen report SHA-256: {REPORT_HASH}")
