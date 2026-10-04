"""Apply the frozen refinement experiment to the existing 14-page defense deck."""
from __future__ import annotations

import hashlib
import json


def update(slides, brief, root):
    folder = next((root / f"artifacts/experiments_v3/iteration_{n}"
        for n in (6, 5) if (root / f"artifacts/experiments_v3/iteration_{n}/release.json").exists()), None)
    if folder is None:
        return "", {}
    release = json.loads((folder / "release.json").read_text(encoding="utf-8"))
    payload = (root / release["report"]).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == release["report_sha256"]
    report = json.loads(payload)
    iteration = folder.name
    retention = "anchor_strength" in report.get("training_method", {})
    before, after = (report["models"][key]["overall"] for key in ("previous", "candidate"))
    official = report["candidate_spec"] if report["promoted"] else report["previous_spec"]
    config = json.loads((root / official["config"]).read_text(encoding="utf-8")) if report["promoted"] else None
    verdict = "通过门槛，升级正式 PPO" if report["promoted"] else "未过全部门槛，保留原 PPO"
    summary = (f"本轮新增 {report['total_training_steps']:,} 步交互。相同的 300 局新测试道路上，"
        f"PPO 达标率从 {before['qualification_rate']:.1%} 到 {after['qualification_rate']:.1%}，"
        f"碰撞从 {before['crashes']} 到 {after['crashes']} 次。{verdict}。")
    # Old observations remain available as explicitly historical evidence.
    for index in (7, 9):
        slide = slides[index]
        slide["title"] = "上一轮：" + slide["title"]
        slide["body"] = (slide["body"].replace("正式 PPO", "原 PPO").replace("本轮", "该轮")
            .replace("<h2>", "<h2>上一轮：", 1))
        slide["talk"] = "先回顾上一轮多算法实验。" + slide["talk"]
        slide["source"] += "；历史实验，与本轮使用不同测试道路。"
    slides[6]["title"] = "上游训练：更久未必更好"
    slides[6]["body"] = (slides[6]["body"].replace("06 / 开发评估曲线", "06 / 上游开发记录")
        .replace("正式部署检查点", "当时部署检查点").replace("正式部署点", "当时部署点"))
    slides[6]["talk"] = "这张图是本轮微调所继承的上游 PPO 训练记录。" + slides[6]["talk"]
    slides[6]["transition"] = "本轮从这个已部署检查点继续训练，后面比较微调前后的结果。"
    slides[5]["body"] = (slides[5]["body"].replace("ITERATION 4", iteration.upper().replace("_", " "))
        .replace("正式高手与效率候选使用不同奖励设置", "微调前后使用不同训练奖励")
        .replace("正式高手 / v3.1", "微调前 / v3.1")
        .replace("提高前进和超车的正反馈。", "增加前进与安全达标的奖励。")
        .replace("额外每米 +0.035、超车 +0.2", "额外每米 +0.015；安全达标 +6"))
    slides[5]["talk"] = "左边是原 PPO 的安全奖励，右边是本轮微调奖励。在原奖励基础上，安全前进每米额外加零点零一五，安全达到里程目标再加六分，事故惩罚项合计负六十。训练还采用真实关卡时长，将高压场景采样提高到百分之六十。游戏双方的计分和物理规则保持一致。"
    slides[5]["source"] = "driving_env.py；driving_env_v3.py；train_refinement.py：RefinementRoad"
    if retention:
        slides[5]["body"] = (slides[5]["body"].replace("效率候选 /", "效率与安全微调 /")
            .replace("同时加重事故惩罚，观察真实取舍。", "危险跟车额外 −0.25 / 步。")
            .replace("再提高通行效率", "兼顾效率与跟车安全"))
        slides[5]["talk"] += "上一轮微调提高了达标率，但出现新的高压追尾。本轮继承其效率权重，额外惩罚危险跟车；在接近前车的状态，用原 PPO 的动作分布作为训练参照，减少已有安全行为的遗忘。参照模型只参与训练损失，比赛仍只执行一个网络。"
        slides[5]["source"] += "；train_safety_refinement.py：训练奖励与参考策略 KL 损失"
    slides[8]["body"] = slides[8]["body"].replace("36 局开发道路", "24 局开发道路")
    slides[8]["talk"] = "本轮每次用二十四局开发道路观察，再将每组两个检查点放到另一组九十六局复核。选择一个候选后冻结文件和哈希，才运行新的三百局独立测试，同时重测原 PPO 与规则基线。发布要求整体达标率和得分提高，整体及每关碰撞不增加，每关达标率不下降。失败时不拿测试集重新挑权重。"
    slides[8]["source"] = f"{iteration}/selection.json；release_refinement.py"
    slides[8]["transition"] = "先回顾上一轮多算法的取舍，再看本轮新道路上的 PPO 微调验收。"
    slides[9]["transition"] = "下面切换到本轮新道路；重新测试原 PPO，再与本轮冻结候选比较。"
    slides[9]["talk"] = slides[9]["talk"].replace("所以最终仍部署原 PPO", "所以该轮保留原 PPO")
    columns = []
    for key, label in (("previous", "微调前 PPO"), ("candidate", "微调后 PPO")):
        stats = report["models"][key]["overall"]
        columns.append(f'<div class="col {"accent" if key == "candidate" else ""}" data-anim="column">'
            f'<div class="col-tag">{label}</div><h3 class="col-ttl">同一组 300 局新道路</h3>'
            f'<div class="metric-pair"><div><div class="value">{stats["qualification_rate"]*100:.1f}%</div><div class="caption">安全达标率</div></div>'
            f'<div><div class="value">{stats["crashes"]}/300</div><div class="caption">碰撞局数</div></div></div>'
            f'<p class="col-desc">平均得分 {stats["mean_score"]:.0f} 分</p></div>')
    pressure = [report["models"][key]["routes"]["pressure"]["qualification_rate"] for key in ("previous", "candidate")]
    slides[10].update(title="本轮微调：在新道路上验收", body=
        '<div class="head" data-anim="head"><div class="t-meta">10 / PPO 微调验收</div>'
        '<h2>本轮微调：在新道路上验收</h2><p class="lead">实际赛程训练 · 高压场景占 60% · 限制策略更新幅度</p></div>'
        '<div class="duo-compare">' + '<div class="vrule"></div>'.join(columns) + '</div>'
        f'<p class="chart-note">高压关达标率：{pressure[0]:.0%} → {pressure[1]:.0%}（各 100 局）。<br>{verdict}。</p>',
        talk=summary + "具体改动是匹配三关实际时长、增加高压场景采样、缩小 PPO 更新，并增加安全达标奖励。游戏中还提供固定开发道路的训练前后双屏回放；片段解释行为，这组完整测试判断是否升级。不同训练种子、学习率和预算共同变化，因此不把提升全部归因于某一个参数。",
        show="左侧微调前，右侧冻结候选；下方给出最难关与发布结论。", purpose="用新道路验证实际训练，而非修改目标或挑选有利片段。",
        source=f"{iteration}/report.json、selection.json、test_previous.json、test_candidate.json；每模型 300 局",
        transition="最后总结已完成的工作，以及仍需继续验证的边界。")
    if retention:
        slides[10]["body"] = slides[10]["body"].replace("实际赛程训练 · 高压场景占 60% · 限制策略更新幅度", "继承效率微调权重 · 危险跟车惩罚 · 参考策略约束")
        slides[10]["talk"] = summary + "这轮继承之前的效率微调权重，增加危险跟车惩罚，并在近距离状态保留原 PPO 的行为倾向。新增交互只统计本轮两组安全微调，不包含上游训练。左侧是最初正式 PPO，右侧是经过两阶段微调的冻结候选。我们没有降低里程要求，也没有让规则替模型接管驾驶。当前结果只适用于这组仿真测试。"
        slides[6]["transition"] = "这份上游 PPO 先做效率微调，再做跟车安全微调；后面比较最终候选与原模型。"
    slides[11]["source"] = f"{iteration}/report.json、release.json；README.md"
    slides[11]["body"] = slides[11]["body"].replace("高压关待改进", "训练与验证").replace("高压关仍待改善；", "仍有道路未达标；")
    slides[11]["title"] = "结论：用新道路检验训练改进"
    slides[11]["talk"] = summary + "项目把驾驶任务、强化学习训练、同道路评估和交互展示连起来。结论局限于这些仿真道路，尚未建立系统的人类基准。下一步需要多训练种子、更多未见道路以及人类对照。"
    if config:
        lr = f"{config['learning_rate']:.0e}"
        slides[12]["body"] = (slides[12]["body"].replace("3e−4", lr).replace("8 epoch", "4 epoch")
            .replace("PPO 裁剪 0.2", f"PPO 裁剪 {config['clip_range']}").replace("熵系数 0.008", "熵系数 0.001"))
        slides[12]["source"] = official["config"] + "；target_kl=0.01；" + official["path"]
        if retention:
            slides[12]["talk"] += f"此外，每轮 PPO 更新后，对当前采样中接近前车的状态增加一次参考策略 KL 更新，权重为 {config['anchor_strength']}。参考网络固定；它不参与游戏推理。这是训练时的策略保留约束，不是碰撞安全保证。"
    brief[6] = (35, "原 PPO 奖励前进、超车与完赛，并惩罚风险。我们先增加安全前进和达标奖励、采用实际赛程，改善保守行为；又针对追尾增加危险跟车惩罚，并在接近前车时约束策略不要过度偏离原安全策略。约束只用于训练，游戏仍由单个网络驾驶。奖励更严格并不保证事故更少，因此必须重新验收。" if retention else slides[5]["talk"])
    brief[7] = (45, "这张图展示上游 PPO 的训练过程，蓝线是当时选中的检查点，也是本轮的微调起点。即使训练更久，里程与危险时间仍会波动，所以需要保存并验证多个检查点。本轮进一步使用实际赛程训练，增加高压场景，再用独立测试检验改进。")
    brief[10] = (45, summary + ("这只统计本轮安全微调，另有上游效率训练。" if retention else "") + "先在开发道路选定候选并冻结，再用新道路测试两份权重和规则基线。没有降低里程目标，也没有根据测试结果重新选择其他检查点。")
    # The short route uses the new result page instead of the historical comparison.
    brief[11] = brief.pop(10)
    ordered = dict(sorted(brief.items()))
    brief.clear()
    brief.update(ordered)
    brief[12] = (30, slides[11]["talk"])
    note = ('<section><h2>本轮微调结论</h2><p>' + summary + '</p><p>'
        '第 7 页为上游记录，第 8、10 页为上一轮多算法对照，第 11 页为本轮 PPO 验收。'
        '两轮测试种子不同，不能跨轮直接计算提升。精简版跳过上一轮结果，直接展示第 11 页。</p>'
        f'<p>本轮证据：<a href="../../artifacts/experiments_v3/{iteration}/report.json">测试报告</a>、'
        f'<a href="../../artifacts/experiments_v3/{iteration}/selection.json">冻结选择</a>。'
        f'报告 SHA-256：<code>{release["report_sha256"]}</code>。</p></section>')
    answers = {"为什么训练更多步没有选最后一个？": "更多训练可能改善通行效率，也可能引入碰撞。我们按开发道路选择并冻结检查点，测试道路只作验收。" + summary,
        "三百局零碰撞，为什么还说没有解决？": "零碰撞是上一轮特定道路上的观察，不是模型的永久属性。" + summary + "有限测试不能保证其他道路零风险，也不能证明超过人类。",
        "A2C 比 PPO 赢得更多，为什么不替换？": "上一轮 A2C 对原 PPO 为 217 胜、72 负、11 平，但碰撞由 0 增加到 5 次，没有通过当时的发布门槛。该轮与本轮的测试道路不同，不直接混算。" + summary,
        "如何解释 AI 减速？": "减速可能是避险，也可能是过度保守。本轮通过实际赛程、效率奖励和危险状态约束尝试改善。要结合前车距离、动作概率和整组测试观察，不能只看瞬时车速。" + summary,
        "下一步最值得做什么？": "本轮已做实际赛程微调和新道路验收。下一步应检查剩余未达标与碰撞案例，控制单项变量做消融，增加独立训练种子与人类基准。"}
    return note, answers
