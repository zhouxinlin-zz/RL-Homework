import { useEffect, useState } from "react";
import RoadCanvas from "./RoadCanvas";
import "./App.css";

type Policy = "random" | "dqn" | "ppo";
type Scenario = "light" | "normal" | "dense";
type Summary = {
  policy: Policy;
  scenario: Scenario;
  episodes: number;
  crash_rate: number;
  mean_return: number;
  mean_speed_kmh: number;
  mean_survival_seconds: number;
};
export type Vehicle = {
  id: number;
  x: number;
  y: number;
  heading: number;
  speed: number;
  crashed: boolean;
};
export type Frame = {
  step: number;
  time_s: number;
  ego_id: number;
  vehicles: Vehicle[];
};
export type Replay = {
  policy: Policy;
  scenario: Scenario;
  seed: number;
  frames: Frame[];
  summary: { crashed: boolean };
};
type TrainingPoint = { timesteps: number; return: number };
type Training = Partial<Record<"dqn" | "ppo", TrainingPoint[]>>;

const policies: { id: Policy; name: string; detail: string; color: string }[] =
  [
    {
      id: "random",
      name: "随机策略",
      detail: "未经训练的参照",
      color: "#94a6ad",
    },
    { id: "dqn", name: "DQN", detail: "基于动作价值决策", color: "#2c9ab1" },
    { id: "ppo", name: "PPO", detail: "逐步改进驾驶策略", color: "#e49b6c" },
  ];
const scenarios: { id: Scenario; name: string; count: number }[] = [
  { id: "light", name: "稀疏车流", count: 12 },
  { id: "normal", name: "常规车流", count: 20 },
  { id: "dense", name: "拥挤车流", count: 35 },
];

function Curve({ training }: { training: Training }) {
  const width = 800,
    height = 220;
  const all = Object.values(training).flat() as TrainingPoint[];
  if (!all.length)
    return <div className="chart-empty">完成训练后显示真实学习曲线</div>;
  const maxX = Math.max(...all.map((p) => p.timesteps), 1);
  const minY = Math.min(...all.map((p) => p.return));
  const maxY = Math.max(...all.map((p) => p.return));
  const rangeY = Math.max(maxY - minY, 1);
  const line = (data: TrainingPoint[]) => {
    const window = Math.max(1, Math.floor(data.length / 45));
    return data
      .map((p, i) => {
        const batch = data.slice(Math.max(0, i - window + 1), i + 1);
        const avg =
          batch.reduce((sum, row) => sum + row.return, 0) / batch.length;
        return `${40 + (p.timesteps / maxX) * 740},${185 - ((avg - minY) / rangeY) * 155}`;
      })
      .join(" ");
  };
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="chart"
      role="img"
      aria-label="DQN 和 PPO 的训练回报曲线"
    >
      {[0, 1, 2, 3].map((i) => (
        <line
          key={i}
          x1="40"
          x2="780"
          y1={30 + i * 52}
          y2={30 + i * 52}
          stroke="#e7eff0"
        />
      ))}
      {training.dqn && (
        <polyline
          points={line(training.dqn)}
          fill="none"
          stroke="#2c9ab1"
          strokeWidth="3"
        />
      )}
      {training.ppo && (
        <polyline
          points={line(training.ppo)}
          fill="none"
          stroke="#e49b6c"
          strokeWidth="3"
        />
      )}
      <text x="40" y="213">
        0
      </text>
      <text x="780" y="213" textAnchor="end">
        {maxX.toLocaleString()} 步
      </text>
    </svg>
  );
}

function App({ onBack }: { onBack?: () => void }) {
  const [policy, setPolicy] = useState<Policy>("dqn");
  const [scenario, setScenario] = useState<Scenario>("normal");
  const [summary, setSummary] = useState<Summary[]>([]);
  const [training, setTraining] = useState<Training>({});
  const [replay, setReplay] = useState<Replay | null>(null);
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      fetch("/data/summary.json").then((r) => {
        if (!r.ok) throw Error();
        return r.json() as Promise<Summary[]>;
      }),
      fetch("/data/training.json").then((r) => {
        if (!r.ok) throw Error();
        return r.json() as Promise<Training>;
      }),
    ])
      .then(([s, t]) => {
        setSummary(s);
        setTraining(t);
      })
      .catch(() => setError("尚无展示数据，请先运行训练、评估和数据导出。"));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`/data/replay_${policy}_${scenario}.json`, {
      signal: controller.signal,
    })
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json() as Promise<Replay>;
      })
      .then((data) => {
        setReplay(data);
        setError("");
      })
      .catch((e) => {
        if (e.name !== "AbortError")
          setError("所选轨迹未生成，请重新运行评估与导出。");
      });
    return () => controller.abort();
  }, [policy, scenario]);

  useEffect(() => {
    if (!playing || !replay) return;
    const timer = window.setInterval(
      () =>
        setPlayhead((value) => {
          const next = value + 0.085;
          if (next >= replay.frames.length - 1) {
            setPlaying(false);
            return replay.frames.length - 1;
          }
          return next;
        }),
      32,
    );
    return () => window.clearInterval(timer);
  }, [playing, replay]);

  const selected = summary.find(
    (s) => s.policy === policy && s.scenario === scenario,
  );
  const currentFrame = replay?.frames[Math.floor(playhead)];
  const ego = currentFrame?.vehicles.find((v) => v.id === currentFrame.ego_id);
  const maxStep = Math.max(0, (replay?.frames.length ?? 1) - 1);
  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-icon">↗</span>
          <div>
            <strong>TrafficRL</strong>
            <small>实验记录与结果</small>
          </div>
        </div>
        <div className="top-note">
          {onBack && (
            <button className="back-to-drive" onClick={onBack}>
              ← 返回驾驶
            </button>
          )}
          <i />
          课程项目 · 实验版 <span /> HighwayEnv + DQN / PPO
        </div>
      </header>
      <main>
        <section className="hero">
          <div>
            <div className="kicker">REINFORCEMENT LEARNING PROJECT</div>
            <h1>
              同一条路，<em>不同的驾驶策略。</em>
            </h1>
            <p>
              在常规车流中训练智能体，再检验它们面对稀疏与拥挤车流时的安全和效率。
            </p>
          </div>
          <div className="hero-side">
            真实训练 <b>·</b> 统一评估 <b>·</b> 固定种子回放
          </div>
        </section>
        <section className="workspace">
          <div className="panel replay-panel">
            <div className="panel-head">
              <div>
                <span className="section-tag">01 / 驾驶回放</span>
                <h2>策略在道路上的表现</h2>
              </div>
              <span className="record-tag">
                <i /> RECORDED EPISODE
              </span>
            </div>
            <div className="road-container">
              {replay ? (
                <RoadCanvas replay={replay} playhead={playhead} />
              ) : (
                <div className="road-loading">正在载入轨迹…</div>
              )}
              <div className="hud">
                <div>
                  <small>当前速度</small>
                  <strong>
                    {ego ? Math.round(ego.speed * 3.6) : "—"} <span>km/h</span>
                  </strong>
                </div>
                <div>
                  <small>仿真时间</small>
                  <strong>
                    {currentFrame ? Math.round(currentFrame.time_s) : "—"}{" "}
                    <span>s</span>
                  </strong>
                </div>
                <div>
                  <small>驾驶状态</small>
                  <strong className={ego?.crashed ? "crash" : "safe"}>
                    {ego?.crashed ? "发生碰撞" : "行驶中"}
                  </strong>
                </div>
              </div>
            </div>
            <div className="player">
              <button
                onClick={() => {
                  if (playhead >= maxStep) setPlayhead(0);
                  setPlaying(!playing);
                }}
                disabled={!replay}
              >
                {playing ? "Ⅱ 暂停" : "▶ 播放"}
              </button>
              <input
                type="range"
                aria-label="回放进度"
                min="0"
                max={maxStep}
                step="0.01"
                value={Math.min(playhead, maxStep)}
                onChange={(e) => {
                  setPlayhead(Number(e.target.value));
                  setPlaying(false);
                }}
              />
              <span>
                {Math.floor(playhead)} / {maxStep} 秒
              </span>
            </div>
            <p className="caption">
              示例回合采用固定测试种子 {replay?.seed ?? "—"}
              ；统计指标来自全部测试回合。
            </p>
          </div>
          <aside className="panel controls">
            <span className="section-tag">实验条件</span>
            <h2>选择策略与车流</h2>
            <label>驾驶策略</label>
            <div className="policy-list">
              {policies.map((item) => (
                <button
                  key={item.id}
                  className={`policy ${policy === item.id ? "chosen" : ""}`}
                  onClick={() => {
                    setReplay(null);
                    setPlayhead(0);
                    setPolicy(item.id);
                    setPlaying(true);
                  }}
                >
                  <i style={{ background: item.color }} />
                  <span>
                    <strong>{item.name}</strong>
                    <small>{item.detail}</small>
                  </span>
                  <b />
                </button>
              ))}
            </div>
            <label htmlFor="traffic">车流密度</label>
            <select
              id="traffic"
              value={scenario}
              onChange={(e) => {
                setReplay(null);
                setPlayhead(0);
                setScenario(e.target.value as Scenario);
                setPlaying(true);
              }}
            >
              {scenarios.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {item.count} 辆车
                </option>
              ))}
            </select>
            <div className="metrics">
              <div>
                <small>碰撞率</small>
                <strong>
                  {selected ? Math.round(selected.crash_rate * 100) : "—"}%
                </strong>
              </div>
              <div>
                <small>平均速度</small>
                <strong>
                  {selected ? Math.round(selected.mean_speed_kmh) : "—"}
                  <span> km/h</span>
                </strong>
              </div>
              <div>
                <small>平均回报</small>
                <strong>
                  {selected ? selected.mean_return.toFixed(1) : "—"}
                </strong>
              </div>
              <div>
                <small>行驶时间</small>
                <strong>
                  {selected ? selected.mean_survival_seconds.toFixed(1) : "—"}
                  <span> s</span>
                </strong>
              </div>
            </div>
            <p className="caption">
              每组评估 {selected?.episodes ?? "—"} 个回合
            </p>
          </aside>
        </section>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <section className="below">
          <div className="section-head">
            <div>
              <span className="section-tag">02 / 实验结果</span>
              <h2>同一车流下的策略比较</h2>
            </div>
            <p>选择上方车流条件，比较碰撞率、速度和无碰撞行驶时间。</p>
          </div>
          <div className="result-grid">
            {policies.map((item) => {
              const row = summary.find(
                (s) => s.policy === item.id && s.scenario === scenario,
              );
              return (
                <div
                  key={item.id}
                  className={`result panel ${item.id === policy ? "focus" : ""}`}
                >
                  <div className="result-name">
                    <i style={{ background: item.color }} />
                    {item.name}
                  </div>
                  <div className="big-number">
                    {row ? Math.round(row.crash_rate * 100) : "—"}
                    <span>% 碰撞率</span>
                  </div>
                  <div className="meter">
                    <i
                      style={{
                        width: `${row ? (1 - row.crash_rate) * 100 : 0}%`,
                        background: item.color,
                      }}
                    />
                  </div>
                  <div className="result-detail">
                    <span>
                      平均速度{" "}
                      <b>{row ? Math.round(row.mean_speed_kmh) : "—"} km/h</b>
                    </span>
                    <span>
                      行驶时间{" "}
                      <b>
                        {row ? row.mean_survival_seconds.toFixed(1) : "—"} s
                      </b>
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
        <section className="below">
          <div className="section-head">
            <div>
              <span className="section-tag">03 / 训练过程</span>
              <h2>训练回报如何变化</h2>
            </div>
            <p>显示实际训练日志的平滑曲线。横轴为环境交互步数。</p>
          </div>
          <div className="panel chart-panel">
            <div className="legend">
              <span>
                <i className="dqn" />
                DQN
              </span>
              <span>
                <i className="ppo" />
                PPO
              </span>
            </div>
            <Curve training={training} />
          </div>
        </section>
        <footer>
          <span>TRAFFICRL · REINFORCEMENT LEARNING COURSE PROJECT</span>
          <span>仿真：HighwayEnv　算法：Stable-Baselines3</span>
        </footer>
      </main>
    </div>
  );
}

export default App;
