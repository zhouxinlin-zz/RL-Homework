import type { TrainingCatalog } from "./types";
import RefinementShowcase from "./RefinementShowcase";

export type TrainingTab = "results" | "algorithms" | "refinement";

const percent = (value: number) => `${(value * 100).toFixed(1)}%`;

export default function ModelShowcase({
  training,
  onPlay,
  onReplay,
  tab,
  setTab,
}: {
  training: TrainingCatalog | null | undefined;
  onPlay: () => void;
  onReplay: (track: string) => void;
  tab: TrainingTab;
  setTab: (tab: TrainingTab) => void;
}) {
  if (!training?.levels.expert) {
    return (
      <div className="model-unavailable">
        <h2>训练记录暂不可用</h2>
        <p>
          程序尚未核对本机的最终测试报告。请运行 Check-Game.cmd
          检查模型与实验文件。
        </p>
      </div>
    );
  }
  const expert = training.levels.expert;

  return (
    <div className="model-showcase">
      {!!training.comparison?.length && (
        <div className="training-tabs" role="group" aria-label="训练展示内容">
          <button
            className={tab === "results" ? "selected" : ""}
            aria-pressed={tab === "results"}
            onClick={() => setTab("results")}
          >
            正式对手与训练
          </button>
          <button
            className={tab === "algorithms" ? "selected" : ""}
            aria-pressed={tab === "algorithms"}
            onClick={() => setTab("algorithms")}
          >
            PPO / DQN / A2C 对照
          </button>
          {training.refinement && (
            <button
              className={tab === "refinement" ? "selected" : ""}
              aria-pressed={tab === "refinement"}
              onClick={() => setTab("refinement")}
            >
              本轮微调与回放
            </button>
          )}
        </div>
      )}
      {tab === "refinement" && training.refinement ? (
        <RefinementShowcase data={training.refinement} onReplay={onReplay} />
      ) : tab === "algorithms" ? (
        <AlgorithmComparison training={training} />
      ) : (
        <>
          <div className="model-lead">
            <div>
              <span className="game-eyebrow">当前实际使用的模型</span>
              <h2>高手对手 · {expert.algorithm ?? training.algorithm}</h2>
              <p>三段赛程共用同一个网络；每次驾驶动作都由网络直接决定。</p>
            </div>
            <div className="model-key-number">
              <strong>300</strong>
              <span>条独立测试道路 / 每个模型</span>
            </div>
          </div>

          <div className="learning-loop" aria-label="强化学习训练流程">
            <div>
              <small>01 / 观察</small>
              <strong>30 维交通状态</strong>
              <span>本车、车道、周围车辆</span>
            </div>
            <i aria-hidden="true">→</i>
            <div>
              <small>02 / 决策</small>
              <strong>5 种驾驶动作</strong>
              <span>保持、变道、加速、减速</span>
            </div>
            <i aria-hidden="true">→</i>
            <div>
              <small>03 / 反馈</small>
              <strong>安全与效率奖励</strong>
              <span>前进、超车、危险、碰撞</span>
            </div>
            <i aria-hidden="true">→</i>
            <div>
              <small>04 / 更新</small>
              <strong>策略 / 价值网络</strong>
              <span>MLP · {expert.algorithm ?? training.algorithm}</span>
            </div>
          </div>

          <div className="model-section-heading">
            <div>
              <span className="game-eyebrow">训练之后</span>
              <h3>独立测试结果</h3>
            </div>
            <span>三条关卡 × 每关 100 个未见种子</span>
          </div>
          <div className="deployed-model" aria-label="正式对手检查点">
            <div className="deployed-identity">
              <strong>{expert.algorithm ?? training.algorithm}</strong>
              <span>正式对战模型</span>
              <small>
                选用 {expert.checkpoint_steps.toLocaleString()} 步检查点
              </small>
            </div>
            <div>
              <strong>{percent(expert.overall.qualification_rate)}</strong>
              <span>安全达标率</span>
            </div>
            <div>
              <strong>
                {expert.overall.crashes} / {expert.overall.episodes}
              </strong>
              <span>碰撞次数</span>
            </div>
            <div>
              <strong>{Math.round(expert.overall.mean_score)}</strong>
              <span>平均得分</span>
            </div>
          </div>
          <div className="model-proof deployed-proof">
            <div>
              <span className="game-eyebrow">规则驾驶对照</span>
              <strong>
                高手对规则驾驶 <b>{training.expert_vs_rule.wins} 胜</b>
              </strong>
              <small>
                {training.expert_vs_rule.pairs} 条相同道路 ·{" "}
                {training.expert_vs_rule.losses} 负{" "}
                {training.expert_vs_rule.draws} 平
              </small>
            </div>
            <div>
              <span className="game-eyebrow">为什么选择它</span>
              <strong>优先保证安全完赛</strong>
              <small>
                候选算法用于检验改进。达标率提高但碰撞增加的模型，不替换正式对手。
              </small>
            </div>
            <p>
              这是仿真道路的模型对比，没有系统的人类基准。高手在连续高压关的达标率为{" "}
              {percent(expert.routes.pressure.qualification_rate)}。
            </p>
          </div>
          <details className="advanced-driver checkpoint-details">
            <summary>训练来源与模型标识</summary>
            <p>
              {expert.method}。
              {expert.training_steps
                ? `该训练记录共运行 ${expert.training_steps.toLocaleString()} 步，选择其中 ${expert.checkpoint_steps.toLocaleString()} 步的检查点。`
                : ""}
            </p>
            <code>
              {expert.policy} · {expert.run_id ?? "已归档"}
              <br />
              {expert.checkpoint_sha256
                ? `SHA-256 ${expert.checkpoint_sha256}`
                : ""}
            </code>
          </details>
        </>
      )}
      <button className="game-primary model-play" onClick={onPlay}>
        与高手模型对决 <span aria-hidden="true">↗</span>
      </button>
    </div>
  );
}

function AlgorithmComparison({ training }: { training: TrainingCatalog }) {
  return (
    <div className="algorithm-comparison">
      <h2>用候选实验，检验对手能否改进。</h2>
      <p>
        正式对手使用 {training.algorithm}。下列为上一轮归档的 PPO、DQN、A2C
        候选训练实验，不在正式比赛中轮流接管车辆；三者用相同的 300
        条独立道路评估。
      </p>
      <div className="algorithm-results">
        {training.comparison?.map((item) => {
          const maximum = Math.max(
            1,
            ...item.history.map((point) => point.steps),
          );
          const points = item.history
            .map(
              (point) =>
                `${8 + (point.steps / maximum) * 274},${82 - point.qualification_rate * 70}`,
            )
            .join(" ");
          return (
            <article key={item.id}>
              <header>
                <strong>{item.algorithm} 候选</strong>
                <span>
                  {item.method ||
                    (item.pretrained ? "已训练权重初始化" : "从零初始化")}
                </span>
              </header>
              <p>
                {item.algorithm === "PPO"
                  ? "限制每轮策略变化，稳定更新。"
                  : item.algorithm === "DQN"
                    ? "学习动作价值，选择预期回报最高的动作。"
                    : "同时更新动作策略与状态价值。"}
              </p>
              <div className="algorithm-score">
                <strong>{percent(item.overall.qualification_rate)}</strong>
                <span>安全达标率</span>
              </div>
              <div className="algorithm-stats">
                <span>
                  {item.overall.crashes}/{item.overall.episodes} 碰撞
                </span>
                <span>平均 {Math.round(item.overall.mean_score)} 分</span>
              </div>
              <small>
                本轮训练 {item.training_steps.toLocaleString()} 步<br />
                选用 {item.checkpoint_steps.toLocaleString()} 步检查点
              </small>
              {item.history.length > 0 && (
                <div className="learning-chart">
                  <span>训练过程中：开发集达标率</span>
                  <svg
                    viewBox="0 0 290 94"
                    role="img"
                    aria-label={`${item.algorithm} 开发集达标率随训练步数变化`}
                  >
                    {[12, 47, 82].map((y) => (
                      <line
                        key={y}
                        x1="8"
                        x2="282"
                        y1={y}
                        y2={y}
                        stroke="#637875"
                        strokeOpacity=".3"
                      />
                    ))}
                    <polyline
                      points={points}
                      fill="none"
                      stroke={
                        item.algorithm === "PPO"
                          ? "#bdf47c"
                          : item.algorithm === "DQN"
                            ? "#ffad73"
                            : "#87c9ff"
                      }
                      strokeWidth="2"
                    />
                    {item.history.map((point) => (
                      <circle
                        key={point.steps}
                        cx={8 + (point.steps / maximum) * 274}
                        cy={82 - point.qualification_rate * 70}
                        r="2.5"
                        fill="#e7eedc"
                      />
                    ))}
                  </svg>
                  <div>
                    <small>0 步 / 0–100%</small>
                    <small>{Math.round(maximum / 1000)}k 步</small>
                  </div>
                </div>
              )}
            </article>
          );
        })}
      </div>
      {training.improvement && (
        <p className="model-improvement">
          该轮 {training.improvement.algorithm} 候选对当时高手：安全达标率{" "}
          {percent(training.improvement.before.qualification_rate)} →{" "}
          <b>{percent(training.improvement.candidate.qualification_rate)}</b>
          ；碰撞 {training.improvement.before.crashes} →{" "}
          <b>{training.improvement.candidate.crashes}</b> 次。
          {training.improvement.promoted
            ? "已通过安全与效率门槛，升级为高手对手。"
            : "未通过升级门槛，该轮保留原 PPO。最新微调结果见单独的训练回放页。"}
        </p>
      )}
      <p className="comparison-note">
        曲线用于开发阶段选检查点；卡片数字来自冻结后的独立测试。初始化方式和训练预算不同，这里比较本项目的具体模型。
      </p>
    </div>
  );
}
