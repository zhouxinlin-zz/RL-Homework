import type { ReactNode } from "react";
import { Icon } from "./Icons";
import {
  duelHighlights,
  duelOutcome,
  reachedGoal,
  safeFinish,
  seriesScore,
} from "./duel";
import RouteArtwork from "./RouteArtwork";
import type { Catalog, GameSession, Records, Settings, Track } from "./types";

export function Modal({
  title,
  eyebrow,
  onBack,
  children,
  wide = false,
}: {
  title: string;
  eyebrow: string;
  onBack: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="game-overlay">
      <section
        className={`game-dialog ${wide ? "wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="dialog-header">
          <div>
            <span>{eyebrow}</span>
            <h1>{title}</h1>
          </div>
          <button
            className="game-icon-button"
            onClick={onBack}
            aria-label="返回"
          >
            <Icon name="close" />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}

export function TrackList({
  tracks,
  selected,
  choose,
  records,
}: {
  tracks: Track[];
  selected: string;
  choose: (track: Track) => void;
  records: Records | null;
}) {
  return (
    <div className="track-grid">
      {tracks.map((track, index) => (
        <button
          className={`track-tile ${track.theme} ${selected === track.id ? "selected" : ""}`}
          key={track.id}
          onClick={() => choose(track)}
        >
          <div className="track-art">
            <RouteArtwork track={track} />
            <span>0{index + 1}</span>
            <b>
              {"★".repeat(
                records?.best.find((b) => b.track === track.id)?.stars ?? 0,
              )}
            </b>
          </div>
          <div className="track-copy">
            <span>第 {index + 1} 关</span>
            <h2>{track.name}</h2>
            <p>
              {track.duration} 秒 · {track.target_m.toLocaleString()} m
            </p>
            <p className="track-brief">{track.brief ?? track.description}</p>
            {records?.best.find((best) => best.track === track.id) && (
              <span className="track-best">
                个人最佳{" "}
                {records.best
                  .find((best) => best.track === track.id)!
                  .score.toLocaleString()}{" "}
                分
              </span>
            )}
            <div className="difficulty">
              {[1, 2, 3, 4].map((i) => (
                <i className={i <= track.difficulty ? "filled" : ""} key={i} />
              ))}
              <small>
                {["", "轻松", "适中", "困难", "专家"][track.difficulty]}
              </small>
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}

export function Setup({
  catalog,
  track,
  onTracks,
  start,
}: {
  catalog: Catalog;
  track: Track;
  onTracks: () => void;
  start: () => void;
}) {
  const expert = catalog.ai_levels?.find((level) => level.id === "expert");
  const index = catalog.tracks.findIndex((item) => item.id === track.id);
  const stages = catalog.tracks.slice(Math.max(0, index));
  return (
    <>
      <div className="setup-focus">
        同一段车流，挑战高手电脑。
        <span>先比安全完赛，再比里程达标，最后比得分。</span>
      </div>
      <button className={`chosen-track ${track.theme}`} onClick={onTracks}>
        <div>
          <span>从这里出发</span>
          <h2>{track.name}</h2>
          <p>
            {track.duration} 秒 / 目标 {track.target_m} 米
          </p>
        </div>
        <span>
          更换路线 <Icon name="back" size={16} />
        </span>
      </button>
      <div className="challenge-itinerary" aria-label="本次赛程">
        {stages.map((item, i) => (
          <div key={item.id}>
            <b>{i + 1}</b>
            <span>{item.name}</span>
            <small>{item.duration} 秒</small>
          </div>
        ))}
      </div>
      <p className="challenge-help">
        {stages.length > 1
          ? `连续挑战 ${stages.length} 段路况，累计双方胜场。每段结束后可重试或继续。`
          : "55 秒高压车流。稳住节奏，在密集车辆之间找到出路。"}
      </p>
      <div className="objective">
        <Icon name="flag" />
        <p>
          {track.brief ?? track.description}
          <br />
          <span>
            本段目标：{track.target_m} 米，超车 {track.overtakes_target ?? 3}{" "}
            次。双方车辆性能相同。
          </span>
        </p>
      </div>
      <button
        className="game-primary"
        disabled={!expert?.available}
        onClick={start}
      >
        开始人机对决 <Icon name="play" />
      </button>
    </>
  );
}

export function SettingsPanel({
  settings,
  change,
  fullscreen,
}: {
  settings: Settings;
  change: (next: Settings) => void;
  fullscreen: () => void;
}) {
  const toggle = (
    key: "sound" | "guides" | "reducedMotion" | "trafficPreview",
  ) =>
    change({
      ...settings,
      [key]: !(key === "trafficPreview"
        ? settings[key] !== false
        : settings[key]),
    });
  return (
    <div className="settings-content">
      {(
        [
          { key: "sound", label: "游戏音效" },
          { key: "guides", label: "本车位置提示" },
          { key: "trafficPreview", label: "周车预览" },
          { key: "reducedMotion", label: "减少动态效果" },
        ] as const
      ).map((item) => (
        <div className="setting-row" key={item.key}>
          <span>{item.label}</span>
          <button
            className={`game-toggle ${(item.key === "trafficPreview" ? settings[item.key] !== false : settings[item.key]) ? "on" : ""}`}
            role="switch"
            aria-checked={
              item.key === "trafficPreview"
                ? settings[item.key] !== false
                : settings[item.key]
            }
            aria-label={item.label}
            onClick={() => toggle(item.key)}
          >
            <i />
          </button>
        </div>
      ))}
      <div className={`audio-levels ${settings.sound ? "" : "muted"}`}>
        {(
          [
            { key: "volume", label: "总音量", fallback: 0.65 },
            { key: "engineVolume", label: "引擎与路面", fallback: 0.55 },
            { key: "effectsVolume", label: "提示与碰撞", fallback: 0.65 },
            { key: "musicVolume", label: "背景音乐", fallback: 0.16 },
          ] as const
        ).map((item) => (
          <label key={item.key} className="volume-row">
            <span>{item.label}</span>
            <input
              aria-label={item.label}
              type="range"
              min={0}
              max={100}
              value={Math.round((settings[item.key] ?? item.fallback) * 100)}
              disabled={!settings.sound}
              onChange={(event) =>
                change({
                  ...settings,
                  [item.key]: Number(event.target.value) / 100,
                })
              }
            />
            <small>
              {Math.round((settings[item.key] ?? item.fallback) * 100)}%
            </small>
          </label>
        ))}
      </div>
      <div className="setting-row">
        <span>车身颜色</span>
        <div className="color-options">
          {["#e4e0d6", "#dc8764", "#8fcaff", "#bdf47c", "#dfb7ff"].map(
            (color) => (
              <button
                aria-label={`车身颜色 ${color}`}
                aria-pressed={settings.color === color}
                style={{ background: color }}
                className={settings.color === color ? "selected" : ""}
                key={color}
                onClick={() => change({ ...settings, color })}
              />
            ),
          )}
        </div>
      </div>
      <div className="setting-row">
        <span>全屏显示</span>
        <button className="game-secondary compact" onClick={fullscreen}>
          <Icon name="expand" /> 切换
        </button>
      </div>
      <details className="game-help">
        <summary>操作与玩法说明</summary>
        <p>
          ← → 或 A / D 换道，点按一次换一条车道。↑ ↓ 或 W / S
          调整车速，按住可连续加减速。Esc 暂停。屏幕按钮也可操作。
        </p>
        <p>
          每局以不碰撞完成行程为第一目标。达到路线里程和超车目标可获得三星。对战依次比较安全完赛、里程达标、得分。连赛累计各段胜场，胜场相同时打平。
        </p>
        <p>
          你和对手从相同车流出发，拥有相同的操控能力。你的驾驶会影响周围车辆，寻找安全空隙再变道。
        </p>
        <p>每局结束后可回看关键时刻，或换一组车流再挑战。</p>
        <p>
          周车预览显示本车前方 120 米、后方 80
          米内的真实车辆。绿色是本车，灰白色是周车，小箭头表示对方相对你的行驶方向。可在设置中关闭。
        </p>
      </details>
    </div>
  );
}

export function RecordList({
  records,
  replay,
}: {
  records: Records | null;
  replay: (id: string) => void;
}) {
  const runs =
    records?.runs.filter(
      (run) =>
        run.version === "3.1.0" &&
        run.mode === "duel" &&
        !run.practice &&
        run.ai_level === "expert",
    ) ?? [];
  const best =
    records?.best.filter((item) =>
      ["convoy", "weave", "pressure"].includes(item.track),
    ) ?? [];
  const score = seriesScore(runs);
  if (!runs.length)
    return (
      <div className="game-empty">
        <Icon name="flag" size={42} />
        <h2>第一段旅程，等你开始</h2>
        <p>完成一局驾驶后，成绩和回放会保存在这里。</p>
        <p>挑战后，可以查看与高手的对战战绩。</p>
      </div>
    );
  return (
    <>
      <div className="duel-history">
        <div className="duel-history-heading">
          <span>最近对战战绩</span>
          <small>
            {runs.length ? `${runs.length} 场挑战` : "等待你的首场挑战"}
          </small>
        </div>
        {runs.length ? (
          <>
            <div className="duel-history-score">
              <span>
                <strong>{score.player}</strong>胜
              </span>
              <span>
                <strong>{score.rival}</strong>负
              </span>
              <span>
                <strong>{score.draws}</strong>平
              </span>
            </div>
          </>
        ) : (
          <p>完成一场 AI 挑战，记录你与对手的胜负。</p>
        )}
      </div>
      <div className="record-overview">
        <div>
          <strong>{runs.length}</strong>
          <span>已保存行程</span>
        </div>
        <div>
          <strong>{best.filter((item) => item.stars > 0).length} / 3</strong>
          <span>已完成路线</span>
        </div>
        <div>
          <strong>
            {best.reduce((total, item) => total + item.stars, 0)} / 9
          </strong>
          <span>路线星级</span>
        </div>
      </div>
      <div className="record-list">
        {runs.map((run) => (
          <button
            className="record-item"
            key={run.session_id}
            onClick={() => replay(run.session_id)}
          >
            <span className={`record-status ${run.crashed ? "crash" : ""}`}>
              {run.crashed ? "×" : "✓"}
            </span>
            <div>
              <strong>{run.track.name}</strong>
              <small>
                高手对决 ·{" "}
                {run.created
                  ? new Date(run.created).toLocaleString("zh-CN", {
                      month: "2-digit",
                      day: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  : ""}
              </small>
            </div>
            <b>
              {run.score.toLocaleString()}
              <small> PTS</small>
            </b>
            <Icon name="replay" />
          </button>
        ))}
      </div>
    </>
  );
}

export function Results({
  session,
  rounds,
  totalRounds,
  retry,
  fresh,
  menu,
  replay,
  next,
}: {
  session: GameSession;
  rounds: GameSession[];
  totalRounds: number;
  retry: () => void;
  fresh: () => void;
  menu: () => void;
  replay: (time?: number) => void;
  next?: () => void;
}) {
  const rival = session.rival;
  const outcome = duelOutcome(session);
  const score = seriesScore(rounds);
  const title =
    outcome === "win"
      ? "本段获胜"
      : outcome === "loss"
        ? "本段落败"
        : "本段平局";
  const highlights = duelHighlights(session);
  const finishLabel = (
    runner: GameSession | NonNullable<GameSession["rival"]>,
  ) =>
    runner.crashed ? "发生碰撞" : safeFinish(runner) ? "安全完成" : "未完赛";
  const metrics = rival
    ? [
        {
          name: "完赛",
          player: finishLabel(session),
          rival: finishLabel(rival),
        },
        {
          name: "里程",
          player: `${session.distance_m.toFixed(0)} m${reachedGoal(session, session.track.target_m) ? " · 达标" : ""}`,
          rival: `${rival.distance_m.toFixed(0)} m${reachedGoal(rival, session.track.target_m) ? " · 达标" : ""}`,
        },
        {
          name: "超车",
          player: `${session.overtakes} 次`,
          rival: `${rival.overtakes} 次`,
        },
        {
          name: "危险跟车",
          player: `${session.danger_seconds.toFixed(1)} s`,
          rival: `${rival.danger_seconds.toFixed(1)} s`,
        },
        {
          name: "平均车速",
          player: `${session.mean_speed_kmh.toFixed(0)} km/h`,
          rival: `${rival.mean_speed_kmh.toFixed(0)} km/h`,
        },
      ]
    : [];
  return (
    <div className="game-overlay result-overlay">
      <section
        className="result-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="驾驶结算"
      >
        <header className="duel-result-heading">
          <div>
            <span className="game-eyebrow">
              {session.track.name} · 第 {rounds.length} / {totalRounds} 段
            </span>
            <h1>{title}</h1>
          </div>
          <div className="result-stars" aria-label={`${session.stars} 星`}>
            {[1, 2, 3].map((star) => (
              <span
                className={star <= session.stars ? "earned" : ""}
                key={star}
              >
                ★
              </span>
            ))}
          </div>
        </header>
        <div className="duel-scorecard" aria-label="本局得分">
          <div>
            <span>你</span>
            <strong>{session.score.toLocaleString()}</strong>
          </div>
          <small>得分</small>
          <div>
            <span>高手电脑</span>
            <strong>{rival?.score.toLocaleString() ?? "—"}</strong>
          </div>
        </div>
        <div className="duel-metrics" role="table" aria-label="双方驾驶表现">
          <div role="row" className="duel-metrics-header">
            <span role="columnheader">本段表现</span>
            <span role="columnheader">你</span>
            <span role="columnheader">高手电脑</span>
          </div>
          {metrics.map((item) => (
            <div role="row" key={item.name}>
              <span role="rowheader">{item.name}</span>
              <span role="cell">{item.player}</span>
              <span role="cell">{item.rival}</span>
            </div>
          ))}
        </div>
        <p className="duel-ranking-note">
          胜负依次比较安全完赛、里程达标、得分。
        </p>
        {totalRounds > 1 && (
          <div className="challenge-score" aria-label="赛程战绩">
            <header>
              <span>{next ? "赛程比分" : "赛程结束"}</span>
              <strong>
                你 {score.player} : {score.rival} 电脑
                {score.draws ? ` · ${score.draws} 段平局` : ""}
              </strong>
            </header>
            <div>
              {rounds.map((round) => (
                <span key={round.session_id}>
                  {round.track.name}
                  <b>
                    {duelOutcome(round) === "win"
                      ? "胜"
                      : duelOutcome(round) === "loss"
                        ? "负"
                        : "平"}
                  </b>
                </span>
              ))}
            </div>
            {!next && (
              <p>
                {score.player > score.rival
                  ? "你赢下了本次赛程。"
                  : score.player < score.rival
                    ? "高手电脑赢下了本次赛程。"
                    : "本次赛程双方打平。"}
              </p>
            )}
          </div>
        )}
        {!!highlights.length && (
          <div className="duel-highlights" aria-label="本局关键时刻">
            <span>回看关键时刻</span>
            <div>
              {highlights.map((event) => (
                <button
                  className="game-secondary compact"
                  key={`${event.actor}-${event.type}-${event.time_s}`}
                  onClick={() => replay(event.time_s)}
                >
                  <Icon name="replay" size={14} />
                  {event.label ??
                    (event.actor === "rival" ? "电脑驾驶" : "你的驾驶")}
                  <small>{event.time_s.toFixed(1)} s</small>
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="result-buttons">
          {next ? (
            <button className="game-primary" onClick={next}>
              继续下一段 <Icon name="play" />
            </button>
          ) : (
            <button className="game-primary" onClick={retry}>
              <Icon name="replay" /> 同场再挑战
            </button>
          )}
          {next && (
            <button className="game-secondary" onClick={retry}>
              重试本段
            </button>
          )}
          <button className="game-secondary" onClick={fresh}>
            换一组车流
          </button>
          <button className="game-secondary" onClick={() => replay()}>
            观看回放
          </button>
          <button className="game-text-button" onClick={menu}>
            返回主菜单
          </button>
        </div>
      </section>
    </div>
  );
}
