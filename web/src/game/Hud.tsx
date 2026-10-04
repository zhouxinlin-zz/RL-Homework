import { useState } from "react";
import type { GameSession, Runner, Replay } from "./types";
import { Icon } from "./Icons";
import TrafficPreview from "./TrafficPreview";
import { opponentName } from "./opponents";

function PolicyChoices({
  decision,
}: {
  decision: NonNullable<Runner["decision"]>;
}) {
  const low = Math.min(...decision.values),
    high = Math.max(...decision.values);
  return (
    <>
      {decision.values.map((value, index) => (
        <div className={index === decision.action ? "chosen" : ""} key={index}>
          <span>{["左移", "保持", "右移", "加速", "减速"][index]}</span>
          <i>
            <b
              style={{
                width: `${100 * (decision.kind === "probability" ? value : (value - low) / Math.max(0.001, high - low))}%`,
              }}
            />
          </i>
          <small>
            {decision.kind === "probability"
              ? `${Math.round(value * 100)}%`
              : value.toFixed(1)}
          </small>
        </div>
      ))}
    </>
  );
}

function Speed({ runner, label }: { runner: Runner; label: string }) {
  const ego = runner.frame.vehicles.find((v) => v.id === runner.frame.ego_id);
  return (
    <div className={`speed-dial ${runner.crashed ? "crashed" : ""}`}>
      <span>{label}</span>
      <div>
        <strong>{Math.round((ego?.speed ?? 0) * 3.6)}</strong>
        <small>KM/H</small>
      </div>
      <div className="speed-bar">
        <i
          style={{ width: `${Math.min(100, ((ego?.speed ?? 0) / 32) * 100)}%` }}
        />
      </div>
      <p>
        {runner.crashed
          ? "发生碰撞"
          : runner.done
            ? "行程完成"
            : `${runner.overtakes} 次超车`}
      </p>
      {runner.frame.target_speed !== undefined && !runner.done && (
        <small className="target-speed">
          目标 {Math.round(runner.frame.target_speed * 3.6)} km/h
        </small>
      )}
    </div>
  );
}

export default function Hud({
  session,
  pause,
  replay = false,
  trafficPreview = true,
  challenge,
  comparison,
}: {
  session: GameSession;
  pause: () => void;
  replay?: boolean;
  trafficPreview?: boolean;
  challenge?: { round: number; total: number; player: number; rival: number };
  comparison?: Replay["comparison"];
}) {
  const [inspectAI, setInspectAI] = useState(false);
  const elapsed = Math.max(
    session.frame.time_s,
    session.rival?.frame.time_s ?? 0,
  );
  const gap = session.rival ? session.distance_m - session.rival.distance_m : 0;
  const targetOvertakes = session.track.overtakes_target ?? 3;
  const aiAction = ["向左换道", "保持", "向右换道", "加速", "减速"];
  const aiRunner = session.rival ?? (session.mode === "ai" ? session : null);
  const algorithm = aiRunner?.model_info?.algorithm?.toUpperCase() ?? "PPO";
  const decision = aiRunner?.decision;
  if (comparison && session.rival)
    return (
      <div className="game-hud split comparison-hud">
        <div className="hud-top">
          <div className="hud-track">
            <span>TRAINING REPLAY</span>
            <strong>{session.track.name} · 训练前后</strong>
          </div>
          <div className="hud-time">
            <small>回放时间</small>
            <strong>
              {elapsed.toFixed(1)}
              <em>s</em>
            </strong>
          </div>
          <button
            className="game-icon-button"
            aria-label="退出回放"
            onClick={pause}
          >
            <Icon name="close" />
          </button>
        </div>
        <div className="split-divider" />
        <div className="comparison-sides">
          {[session, session.rival].map((runner, index) => (
            <section key={index}>
              <span>{index ? comparison.right : comparison.left}</span>
              <strong>
                {runner.distance_m.toFixed(0)}{" "}
                <small>/ {session.track.target_m} m</small>
              </strong>
              <p>
                {runner.crashed
                  ? "发生碰撞"
                  : runner.done
                    ? !runner.completed
                      ? "未安全完赛"
                      : runner.qualified
                        ? "安全达标"
                        : "安全完赛 · 里程不足"
                    : aiAction[runner.frame.action ?? 1]}{" "}
                · {runner.overtakes} 次超车
              </p>
              <div className="progress-line">
                <i
                  style={{
                    width: `${Math.min(100, (runner.distance_m / session.track.target_m) * 100)}%`,
                  }}
                />
              </div>
              {inspectAI && runner.decision && (
                <div
                  className="policy-readout comparison-policy"
                  aria-label={`${index ? comparison.right : comparison.left} 动作概率`}
                >
                  <PolicyChoices decision={runner.decision} />
                </div>
              )}
            </section>
          ))}
        </div>
        <div className="comparison-context">
          <strong>
            {Math.abs(gap) < 2
              ? "行驶里程接近"
              : `微调后${gap < 0 ? "领先" : "落后"} ${Math.abs(gap).toFixed(0)} m`}
          </strong>
          <span>相同起点 · 固定开发道路 {comparison.seed}</span>
          <small>{comparison.note}</small>
          <button
            className="comparison-inspect"
            aria-expanded={inspectAI}
            onClick={() => setInspectAI((value) => !value)}
          >
            {inspectAI ? "收起动作概率" : "比较动作概率"}
          </button>
          {inspectAI && (
            <small>
              各自决策前的策略输出，高亮为刚执行的动作；概率不是安全评分。
            </small>
          )}
        </div>
        <div className="hud-speed">
          <Speed runner={session} label={comparison.left} />
        </div>
        <div className="hud-rival-speed">
          <Speed runner={session.rival} label={comparison.right} />
        </div>
      </div>
    );
  return (
    <div className={`game-hud ${session.rival ? "split" : ""}`}>
      <div className="hud-top">
        <div className="hud-track">
          <span>{replay ? "REPLAY" : session.track.en}</span>
          <strong>{session.track.name}</strong>
        </div>
        <div className="hud-time">
          <small>剩余时间</small>
          <strong>
            {Math.max(0, session.track.duration - elapsed).toFixed(1)}
            <em>s</em>
          </strong>
        </div>
        <button
          className="game-icon-button"
          aria-label={replay ? "退出回放" : "暂停游戏"}
          onClick={pause}
        >
          <Icon name={replay ? "close" : "pause"} />
        </button>
      </div>
      <div className="hud-progress">
        <div>
          <span>
            {session.distance_m.toFixed(0)} / {session.track.target_m} m
          </span>
          <strong>
            {session.score.toLocaleString()} <small>PTS</small>
          </strong>
        </div>
        <div className="progress-line">
          <i
            style={{
              width: `${Math.min(100, (session.distance_m / session.track.target_m) * 100)}%`,
            }}
          />
        </div>
        <div className="hud-objectives">
          <span
            className={
              session.distance_m >= session.track.target_m ? "done" : ""
            }
          >
            {session.distance_m >= session.track.target_m ? "✓" : "○"} 里程目标
          </span>
          <span className={session.overtakes >= targetOvertakes ? "done" : ""}>
            {session.overtakes >= targetOvertakes ? "✓" : "○"} 超车{" "}
            {session.overtakes}/{targetOvertakes}
          </span>
        </div>
      </div>
      {session.rival && (
        <>
          <div className="split-divider" />
          <div className="rival-label">
            <span>电脑</span>
            <strong>
              {session.rival.score.toLocaleString()} <small>PTS</small>
            </strong>
          </div>
          <div className={`duel-standing ${gap >= 0 ? "ahead" : "behind"}`}>
            <small>
              {challenge && challenge.total > 1
                ? `第 ${challenge.round} / ${challenge.total} 段 · `
                : ""}
              {opponentName(session.policy, session.ai_level)}对手
            </small>
            <strong>
              {session.crashed && !session.rival.crashed
                ? "你的行程结束"
                : session.rival.crashed && !session.crashed
                  ? "对手发生碰撞"
                  : Math.abs(gap) < 2
                    ? "并驾齐驱"
                    : `${gap > 0 ? "领先" : "落后"} ${Math.abs(gap).toFixed(0)} m`}
            </strong>
            <span>
              {session.rival.done
                ? "对手行程结束"
                : `对手正在${aiAction[session.rival.frame.action ?? 1] === "保持" ? "保持车道" : aiAction[session.rival.frame.action ?? 1]}`}
            </span>
            {challenge && challenge.total > 1 && (
              <span>
                赛程比分　你 {challenge.player} : {challenge.rival} 电脑
              </span>
            )}
          </div>
        </>
      )}
      <div className="hud-speed">
        <Speed
          runner={session}
          label={session.mode === "ai" ? "电脑驾驶" : "你的车速"}
        />
      </div>
      {trafficPreview && (
        <TrafficPreview
          frame={session.frame}
          player={session.mode === "duel"}
        />
      )}
      {session.rival && (
        <div className="hud-rival-speed">
          <Speed runner={session.rival} label="对手车速" />
        </div>
      )}
      {aiRunner && (
        <button
          className={`ai-inspect-toggle ${inspectAI ? "selected" : ""}`}
          aria-expanded={inspectAI}
          onClick={() => setInspectAI((value) => !value)}
        >
          {inspectAI ? "收起 AI 决策" : "查看 AI 决策"}
        </button>
      )}
      {decision && inspectAI && (
        <div className="policy-readout" aria-label="AI 实时决策">
          <header>
            <span>{algorithm} 决策</span>
            <small>
              {aiRunner?.model_steps.toLocaleString()} 步检查点 ·{" "}
              {decision.kind === "probability" ? "动作概率" : "动作价值 Q"}
            </small>
          </header>
          <PolicyChoices decision={decision} />
        </div>
      )}
      {session.risk.danger && !session.player_done && (
        <div className="danger-alert">
          <i /> 注意前车距离
        </div>
      )}
      {!session.player_done && (session.risk.left || session.risk.right) && (
        <div className="side-risk">
          {session.risk.left && <span>‹ 左侧车辆接近</span>}
          {session.risk.right && <span>右侧车辆接近 ›</span>}
        </div>
      )}
    </div>
  );
}
