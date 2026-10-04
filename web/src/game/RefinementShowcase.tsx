import type { Refinement } from "./types";

const percent = (value: number) => `${(100 * value).toFixed(1)}%`;
const names: Record<string, string> = {
  convoy: "慢车编队",
  weave: "交织车流",
  pressure: "连续高压",
};

export default function RefinementShowcase({
  data,
  onReplay,
}: {
  data: Refinement;
  onReplay: (track: string) => void;
}) {
  const before = data.models.previous;
  const after = data.models.candidate;
  return (
    <section className="refinement-showcase" aria-label="PPO 训练前后对照">
      <div className="model-lead">
        <div>
          <span className="game-eyebrow">PPO / 本轮微调</span>
          <h2>同一条路，观察训练带来的变化。</h2>
          <p>
            {data.safety_retention
              ? "先提高通行效率，再针对危险跟车进行安全微调；运行时由单个 PPO 网络驾驶。"
              : "按实际赛程训练，增加高压车流采样，并限制每轮策略的更新幅度。"}
          </p>
        </div>
        <div className="model-key-number">
          <strong>{(data.total_training_steps / 10000).toFixed(1)}万</strong>
          <span>本轮新增环境交互 / 含各组训练</span>
          {data.upstream_refinement_steps > 0 && (
            <small>
              另有上轮效率训练{" "}
              {(data.upstream_refinement_steps / 10000).toFixed(1)} 万步
            </small>
          )}
        </div>
      </div>
      <div className="refinement-results">
        {[
          { title: "微调前 PPO", stats: before.overall },
          { title: "微调后 PPO", stats: after.overall },
        ].map(({ title, stats }) => (
          <article key={title}>
            <h3>{title}</h3>
            <strong>{percent(stats.qualification_rate)}</strong>
            <span>安全达标率</span>
            <p>
              {stats.crashes} / {stats.episodes} 局碰撞 <b>·</b> 平均{" "}
              {Math.round(stats.mean_score)} 分
            </p>
          </article>
        ))}
      </div>
      <p className="comparison-note">
        双方各 {after.overall.episodes}{" "}
        局，使用同一组新测试道路；先选定权重，再进行测试。
        {data.promoted
          ? "微调模型已通过安全与效率门槛，正式对手已更新。"
          : "本轮候选未通过全部升级条件，正式对手继续使用原 PPO。"}
      </p>
      <div className="refinement-routes" aria-label="各关训练前后达标率">
        {Object.keys(names).map((key) => (
          <div key={key}>
            <span>{names[key]}</span>
            <strong>
              {percent(before.routes[key].qualification_rate)} <i>→</i>{" "}
              {percent(after.routes[key].qualification_rate)}
            </strong>
            <small>
              碰撞 {before.routes[key].crashes} → {after.routes[key].crashes} /{" "}
              {data.episodes_per_route} 局
            </small>
          </div>
        ))}
      </div>
      <div className="model-section-heading">
        <div>
          <span className="game-eyebrow">看策略怎样驾驶</span>
          <h3>训练前后，同步回放</h3>
        </div>
        <span>左侧微调前 · 右侧微调后</span>
      </div>
      <div className="refinement-replays">
        {data.replays.map((route) => (
          <button key={route.id} onClick={() => onReplay(route.id)}>
            <span>{route.name}</span>
            <small>{route.duration} 秒 · 可暂停与慢放</small>
            <b aria-hidden="true">↗</b>
          </button>
        ))}
      </div>
      <p className="comparison-note">
        每关固定一条开发道路，未按输赢挑选；回放用于观察减速、换道和超车，不代替完整测试。
      </p>
      <details className="advanced-driver checkpoint-details">
        <summary>展开训练曲线与选模记录</summary>
        <div className="refinement-curves">
          {data.histories.map((run, index) => {
            const maximum = Math.max(1, run.actual_steps);
            const points = run.points
              .map(
                (p) =>
                  `${35 + (p.steps / maximum) * 400},${120 - p.qualification_rate * 100}`,
              )
              .join(" ");
            return (
              <figure key={run.run_id}>
                <figcaption>
                  训练 {index + 1} · 种子 {run.seed} · 学习率{" "}
                  {run.learning_rate}
                  {run.anchor_strength != null &&
                    ` · 安全约束 ${run.anchor_strength}`}
                </figcaption>
                <svg
                  viewBox="0 0 460 152"
                  role="img"
                  aria-label={`训练 ${index + 1} 开发集达标率曲线`}
                >
                  {[0, 0.5, 1].map((value) => (
                    <g key={value}>
                      <line
                        x1="35"
                        x2="435"
                        y1={120 - value * 100}
                        y2={120 - value * 100}
                        stroke="#637875"
                        strokeOpacity=".4"
                      />
                      <text x="30" y={124 - value * 100} textAnchor="end">
                        {value * 100}%
                      </text>
                    </g>
                  ))}
                  <polyline
                    points={points}
                    fill="none"
                    stroke="var(--accent)"
                    strokeWidth="2"
                  />
                  {run.points.map((p) => (
                    <circle
                      key={p.steps}
                      cx={35 + (p.steps / maximum) * 400}
                      cy={120 - p.qualification_rate * 100}
                      r="3"
                      fill={p.crashes ? "#ffad73" : "#bdf47c"}
                    />
                  ))}
                  <text x="35" y="145">
                    0
                  </text>
                  <text x="435" y="145" textAnchor="end">
                    {maximum.toLocaleString()} 步
                  </text>
                </svg>
              </figure>
            );
          })}
        </div>
        <p>
          每点为 24
          局固定开发道路。橙点表示该次开发评估发生碰撞；曲线保留原始记录、不做平滑。零点继承已有
          PPO
          {data.safety_retention
            ? " 的效率微调权重；图中只统计后续安全微调的新增步数"
            : ""}
          。 再用 96 局开发道路选择检查点；候选为 {data.candidate_run} 的{" "}
          {data.checkpoint_steps.toLocaleString()} 步。 上方{" "}
          {after.overall.episodes} 局为另一组冻结后的独立测试。
        </p>
      </details>
    </section>
  );
}
