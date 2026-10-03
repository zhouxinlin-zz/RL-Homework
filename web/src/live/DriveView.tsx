import { useEffect, useRef, useState } from "react";
import LiveRoad from "./LiveRoad";
import { closeSession, createSession, stepSession } from "./api";
import type { DrivingMode, DrivingSession, Policy, Scenario } from "./types";
import "./DriveView.css";

const trafficOptions: { id: Scenario; label: string; note: string }[] = [
  { id: "light", label: "畅通", note: "车流较少" },
  { id: "normal", label: "日常", note: "普通车流" },
  { id: "dense", label: "拥挤", note: "车辆密集" },
];
const actionNames: Record<number, string> = {
  0: "向左换道",
  1: "保持行驶",
  2: "向右换道",
  3: "加速",
  4: "减速",
};
type RunResult = {
  reward: number;
  time: number;
  crashed: boolean;
  meanSpeed: number;
};
type Challenge = {
  seed: number;
  scenario: Scenario;
  human: RunResult;
  ai?: RunResult;
};

function resultOf(run: DrivingSession): RunResult {
  return {
    reward: run.total_reward,
    time: run.frame.time_s,
    crashed: run.crashed,
    meanSpeed: run.mean_speed_kmh,
  };
}

export default function DriveView({ onResearch }: { onResearch: () => void }) {
  const [mode, setMode] = useState<DrivingMode>("ai");
  const [policy, setPolicy] = useState<Policy>("ppo");
  const [scenario, setScenario] = useState<Scenario>("normal");
  const [session, setSession] = useState<DrivingSession | null>(null);
  const [playing, setPlaying] = useState(false);
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState("");
  const [lastActions, setLastActions] = useState<string[]>([]);
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const pendingAction = useRef(1);
  const stepping = useRef(false);
  const activeId = useRef<string | null>(null);
  const challengeSeed = useRef<number | null>(null);
  const sessionId = session?.session_id;

  useEffect(
    () => () => {
      const id = activeId.current;
      activeId.current = null;
      if (id) void closeSession(id).catch(() => undefined);
    },
    [],
  );

  useEffect(() => {
    if (!playing || !sessionId) return;
    const timer = window.setInterval(async () => {
      if (stepping.current) return;
      stepping.current = true;
      const action = pendingAction.current;
      pendingAction.current = 1;
      try {
        const next = await stepSession(
          sessionId,
          session?.mode === "human" ? action : undefined,
        );
        if (activeId.current !== sessionId) return;
        setSession(next);
        if (next.frame.action !== null)
          setLastActions((items) =>
            [actionNames[next.frame.action!] ?? "继续行驶", ...items].slice(
              0,
              5,
            ),
          );
        if (next.done) {
          setPlaying(false);
          if (next.mode === "human") {
            setChallenge({
              seed: next.seed,
              scenario: next.scenario,
              human: resultOf(next),
            });
          } else if (challengeSeed.current === next.seed) {
            setChallenge((current) =>
              current && current.seed === next.seed
                ? { ...current, ai: resultOf(next) }
                : current,
            );
            challengeSeed.current = null;
          }
        }
      } catch (error) {
        if (activeId.current !== sessionId) return;
        setPlaying(false);
        setMessage(error instanceof Error ? error.message : "驾驶连接中断");
      } finally {
        stepping.current = false;
      }
    }, 820);
    return () => window.clearInterval(timer);
  }, [playing, sessionId, session?.mode]);

  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      if (!session || session.mode !== "human" || !playing) return;
      const mapping: Record<string, number> = {
        ArrowLeft: 0,
        a: 0,
        ArrowRight: 2,
        d: 2,
        ArrowUp: 3,
        w: 3,
        ArrowDown: 4,
        s: 4,
        " ": 1,
      };
      const action = mapping[event.key];
      if (action !== undefined) {
        event.preventDefault();
        pendingAction.current = action;
      }
    }
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [session, playing]);

  async function begin(challengeRun?: { seed: number; scenario: Scenario }) {
    setPlaying(false);
    setCreating(true);
    setMessage("");
    setLastActions([]);
    pendingAction.current = 1;
    activeId.current = null;
    if (challengeRun) {
      setMode("ai");
      setScenario(challengeRun.scenario);
      challengeSeed.current = challengeRun.seed;
    } else {
      setChallenge(null);
      challengeSeed.current = null;
    }
    try {
      if (sessionId) await closeSession(sessionId).catch(() => undefined);
      const next = await createSession(
        challengeRun ? "ai" : mode,
        challengeRun?.scenario ?? scenario,
        policy,
        challengeRun?.seed,
      );
      activeId.current = next.session_id;
      setSession(next);
      setPlaying(true);
    } catch (error) {
      challengeSeed.current = null;
      setMessage(error instanceof Error ? error.message : "无法创建驾驶回合");
      setSession(null);
    } finally {
      setCreating(false);
    }
  }

  const ego = session?.frame.vehicles.find(
    (vehicle) => vehicle.id === session.frame.ego_id,
  );
  const speed = ego ? Math.round(ego.speed * 3.6) : 0;
  const time = session ? Math.round(session.frame.time_s) : 0;
  const status = !session
    ? "等待开始"
    : session.crashed
      ? "发生碰撞"
      : session.done
        ? "顺利完成"
        : playing
          ? "正在行驶"
          : "已暂停";

  return (
    <div className="drive-app">
      <header className="drive-header">
        <div className="drive-brand">
          <span className="drive-logo">↗</span>
          <div>
            <strong>TrafficRL</strong>
            <small>强化学习驾驶项目</small>
          </div>
        </div>
        <nav>
          <button className="active">驾驶体验</button>
          <button onClick={onResearch}>
            实验记录 <span>↗</span>
          </button>
        </nav>
        <div className="drive-header-tag">
          <i />
          本地运行
        </div>
      </header>
      <main className="drive-main">
        <div className="drive-intro">
          <div>
            <span>强化学习 · 自动驾驶模拟</span>
            <h1>看 AI 如何在车流中做决定。</h1>
            <p>
              选择驾驶方式，开始一段高速公路行程。AI
              使用已训练的模型自主决策；你也可以亲自驾驶，再邀请 AI
              挑战同一路况。
            </p>
          </div>
          <div className="drive-intro-count">
            <strong>
              30<span>s</span>
            </strong>
            <small>每局最长行驶时间</small>
          </div>
        </div>
        <div className="drive-layout">
          <section className="drive-stage">
            <div className="stage-head">
              <div>
                <span className={`status-dot ${playing ? "moving" : ""}`} />
                {status}
              </div>
              <span>
                HIGHWAY SIMULATION ·{" "}
                {
                  trafficOptions.find(
                    (item) => item.id === (session?.scenario ?? scenario),
                  )?.label
                }
              </span>
            </div>
            <div className="stage-image">
              <LiveRoad session={session} />
              <div className="stage-hud">
                <div>
                  <small>实时速度</small>
                  <strong>
                    {speed}
                    <em> km/h</em>
                  </strong>
                </div>
                <div>
                  <small>行驶时间</small>
                  <strong>
                    {time}
                    <em> s</em>
                  </strong>
                </div>
                <div>
                  <small>本局得分</small>
                  <strong>
                    {session ? session.total_reward.toFixed(1) : "0.0"}
                  </strong>
                </div>
              </div>
              {!session && (
                <div className="stage-start-message">
                  <span>READY TO DRIVE</span>
                  <h2>准备好出发了吗？</h2>
                  <p>右侧选择驾驶方式，然后点击「开始行驶」。</p>
                </div>
              )}
              {session?.done && (
                <div className="stage-finish">
                  <strong>
                    {session.crashed ? "本局发生碰撞" : "本局顺利完成"}
                  </strong>
                  <span>点击「再来一局」重新开始</span>
                </div>
              )}
            </div>
            <div className="stage-bottom">
              <div>
                <span className="stage-bottom-icon">●</span>{" "}
                {!session
                  ? "选择驾驶方式，开始行程"
                  : session.mode === "human"
                    ? "键盘 ↑ 加速 · ↓ 减速 · ← → 换道"
                    : "AI 根据周围车流自动选择动作"}
              </div>
              <span>高速公路模拟</span>
            </div>
          </section>
          <aside className="drive-controls">
            <div className="controls-heading">
              <span>驾驶设置</span>
              <h2>开启一段行程</h2>
            </div>
            <div className="field-title">驾驶方式</div>
            <div className="mode-switch">
              <button
                className={mode === "ai" ? "selected" : ""}
                onClick={() => {
                  setMode("ai");
                  setPlaying(false);
                }}
              >
                <strong>AI 驾驶</strong>
                <small>看模型自主行驶</small>
              </button>
              <button
                className={mode === "human" ? "selected" : ""}
                onClick={() => {
                  setMode("human");
                  setPlaying(false);
                }}
              >
                <strong>自己驾驶</strong>
                <small>用方向键操作</small>
              </button>
            </div>
            <div className="field">
              <label htmlFor="driver">选择 AI 驾驶员</label>
              <select
                id="driver"
                value={policy}
                onChange={(event) => {
                  setPolicy(event.target.value as Policy);
                  setPlaying(false);
                }}
              >
                <option value="ppo">平稳驾驶</option>
                <option value="dqn">积极驾驶</option>
              </select>
              <p>名称描述这一轮训练中的驾驶表现；算法与完整结果见实验记录。</p>
            </div>
            <div className="field">
              <label>道路情况</label>
              <div className="traffic-choice">
                {trafficOptions.map((item) => (
                  <button
                    key={item.id}
                    className={scenario === item.id ? "selected" : ""}
                    onClick={() => {
                      setScenario(item.id);
                      setPlaying(false);
                    }}
                  >
                    <strong>{item.label}</strong>
                    <small>{item.note}</small>
                  </button>
                ))}
              </div>
            </div>
            <button
              className="primary-drive-button"
              onClick={() => void begin()}
              disabled={creating}
            >
              {creating ? "正在准备…" : session ? "↻ 再来一局" : "▶ 开始行驶"}
            </button>
            {session && !session.done && (
              <button
                className="secondary-drive-button"
                onClick={() => setPlaying((value) => !value)}
              >
                {playing ? "Ⅱ 暂停驾驶" : "▶ 继续驾驶"}
              </button>
            )}
            {challenge && (
              <button
                className="challenge-button"
                onClick={() =>
                  void begin({
                    seed: challenge.seed,
                    scenario: challenge.scenario,
                  })
                }
                disabled={creating || playing}
              >
                ▶ {challenge.ai ? "让 AI 再挑战一次" : "让 AI 跑同一路况"}
              </button>
            )}
            {message && (
              <div className="drive-message" role="alert">
                {message}
              </div>
            )}
            <div className="session-note">
              <span>01</span> 普通开局会生成新路况；同路况挑战会复用初始车流。
              <br />
              <span>02</span> 模型训练已完成，开始后直接驾驶。
            </div>
          </aside>
        </div>
        {challenge && (
          <section className="challenge-card">
            <div className="challenge-heading">
              <div>
                <span>SAME ROAD CHALLENGE</span>
                <h2>你和 AI，谁开得更稳？</h2>
                <p>两次行程从相同初始车流出发，直接比较驾驶表现。</p>
              </div>
              <strong>
                {challenge.ai
                  ? challenge.human.crashed && !challenge.ai.crashed
                    ? "AI 避开了碰撞"
                    : !challenge.human.crashed && challenge.ai.crashed
                      ? "你避开了碰撞"
                      : "查看两次行程"
                  : "等待 AI 挑战"}
              </strong>
            </div>
            <div className="challenge-results">
              <div>
                <span>你的行程</span>
                <strong>
                  {challenge.human.crashed ? "发生碰撞" : "安全到达"}
                </strong>
                <small>
                  {challenge.human.time.toFixed(0)} 秒 · 得分{" "}
                  {challenge.human.reward.toFixed(1)} · 均速{" "}
                  {challenge.human.meanSpeed.toFixed(0)} km/h
                </small>
              </div>
              <div>
                <span>AI 的行程</span>
                <strong>
                  {challenge.ai
                    ? challenge.ai.crashed
                      ? "发生碰撞"
                      : "安全到达"
                    : playing && session?.mode === "ai"
                      ? "正在行驶…"
                      : "等待开始"}
                </strong>
                <small>
                  {challenge.ai
                    ? `${challenge.ai.time.toFixed(0)} 秒 · 得分 ${challenge.ai.reward.toFixed(1)} · 均速 ${challenge.ai.meanSpeed.toFixed(0)} km/h`
                    : "点击右侧按钮，让 AI 跑同一局"}
                </small>
              </div>
            </div>
          </section>
        )}
        <div className="drive-lower">
          <div className="drive-info-card">
            <span>THIS RUN</span>
            <h3>本局概览</h3>
            <div className="run-numbers">
              <div>
                <strong>{session?.steps ?? 0}</strong>
                <small>行动次数</small>
              </div>
              <div>
                <strong>{session?.mean_speed_kmh.toFixed(0) ?? "0"}</strong>
                <small>平均速度 km/h</small>
              </div>
              <div>
                <strong>{session?.crashed ? "1" : "0"}</strong>
                <small>碰撞次数</small>
              </div>
            </div>
          </div>
          <div className="drive-info-card">
            <span>RECENT ACTIONS</span>
            <h3>
              {session?.mode === "human" ? "你的最近操作" : "AI 的最近决策"}
            </h3>
            <div className="action-feed">
              {lastActions.length ? (
                lastActions.map((action, index) => (
                  <span key={`${action}-${index}`}>{action}</span>
                ))
              ) : (
                <p>开始行驶后，这里会记录每一步决策。</p>
              )}
            </div>
          </div>
        </div>
        {session?.mode === "human" && (
          <div className="touch-controls">
            <span>屏幕操作</span>
            <div>
              {[
                [0, "← 换道"],
                [3, "＋ 加速"],
                [4, "－ 减速"],
                [2, "换道 →"],
              ].map(([action, label]) => (
                <button
                  key={action}
                  onClick={() => {
                    pendingAction.current = Number(action);
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
        <footer className="drive-footer">
          <span>TrafficRL · 三人强化学习课程项目</span>
          <span>
            驾驶仿真 HighwayEnv · 模型 Stable-Baselines3 · 画面 PixiJS
          </span>
        </footer>
      </main>
    </div>
  );
}
