import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { api } from "./api";
import { useDriving } from "./useDriving";
import { useDriveControls } from "./useDriveControls";
import Hud from "./Hud";
import {
  Modal,
  RecordList,
  Results,
  SettingsPanel,
  Setup,
  TrackList,
} from "./Menus";
import { Icon } from "./Icons";
import { gameAudio, tone } from "./sound";
import ModelShowcase, { type TrainingTab } from "./ModelShowcase";
import { frameBefore, frameTime, replayMarkers } from "./replay";
import type {
  Catalog,
  GameSession,
  Records,
  Replay,
  Settings,
  Track,
} from "./types";
import { seriesScore } from "./duel";
import "./Game.css";
const RoadScene = lazy(() => import("./RoadScene"));

type Panel =
  "menu" | "setup" | "levels" | "settings" | "records" | "training" | null;
const defaultSettings: Settings = {
  sound: true,
  guides: true,
  trafficPreview: true,
  color: "#e4e0d6",
  reducedMotion: false,
  vehicle: "sport",
  volume: 0.65,
  engineVolume: 0.55,
  effectsVolume: 0.65,
  musicVolume: 0.16,
};
function loadSettings(): Settings {
  try {
    const stored = JSON.parse(
      localStorage.getItem("lane-shift.settings") ?? "{}",
    );
    return {
      ...defaultSettings,
      ...stored,
      color: /^#[\da-f]{6}$/i.test(stored.color ?? "")
        ? stored.color
        : defaultSettings.color,
      vehicle: ["sport", "touring", "suv"].includes(stored.vehicle)
        ? stored.vehicle
        : "sport",
      volume: Math.max(
        0,
        Math.min(1, Number.isFinite(stored.volume) ? stored.volume : 0.65),
      ),
      engineVolume: Math.max(
        0,
        Math.min(
          1,
          Number.isFinite(stored.engineVolume) ? stored.engineVolume : 0.55,
        ),
      ),
      effectsVolume: Math.max(
        0,
        Math.min(
          1,
          Number.isFinite(stored.effectsVolume) ? stored.effectsVolume : 0.65,
        ),
      ),
      musicVolume: Math.max(
        0,
        Math.min(
          1,
          Number.isFinite(stored.musicVolume) ? stored.musicVolume : 0.16,
        ),
      ),
    };
  } catch {
    return defaultSettings;
  }
}

export default function GameApp() {
  const driving = useDriving();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [panel, setPanel] = useState<Panel>("menu");
  const [trainingTab, setTrainingTab] = useState<TrainingTab>("results");
  const [returnPanel, setReturnPanel] = useState<Panel>("menu");
  const [trackId, setTrackId] = useState("pressure");
  const [challengeStartId, setChallengeStartId] = useState("pressure");
  const [completedRounds, setCompletedRounds] = useState<GameSession[]>([]);
  const [records, setRecords] = useState<Records | null>(null);
  const [settings, setSettings] = useState(loadSettings);
  const [sceneReady, setSceneReady] = useState(false);
  const controls = useDriveControls(
    driving.phase === "running" && !driving.session?.player_done,
    (action) => {
      driving.action(action);
      if (settings.sound && (action === 0 || action === 2))
        gameAudio.event("lane");
    },
  );
  const [notice, setNotice] = useState("");
  const [replay, setReplay] = useState<Replay | null>(null);
  const [replayIndex, setReplayIndex] = useState(0);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replayRate, setReplayRate] = useState(1);
  const [replayLoading, setReplayLoading] = useState(false);
  const sceneReadinessChanged = useCallback((ready: boolean) => {
    setSceneReady(ready);
    if (!ready) setReplayPlaying(false);
  }, []);
  const replayRequest = useRef(0);
  const previousReplay = useRef({ id: "", index: -1 });
  const previousPhase = useRef(driving.phase);
  const previousOvertakes = useRef(0);
  const previousCrash = useRef(false);
  const pauseDriving = driving.pause;
  useEffect(() => {
    if (!sceneReady) pauseDriving();
  }, [sceneReady, driving.phase, pauseDriving]);
  const track =
    catalog?.tracks.find((t) => t.id === trackId) ?? catalog?.tracks[0] ?? null;
  const challengeTracks =
    catalog?.tracks.slice(
      Math.max(
        0,
        catalog.tracks.findIndex((item) => item.id === challengeStartId),
      ),
    ) ?? [];
  const matchScore = seriesScore(completedRounds);
  const sceneSession = replay ? replay.frames[replayIndex] : driving.session;
  const active = driving.phase !== "idle" || replay !== null;
  const markers = useMemo(
    () => (replay ? replayMarkers(replay.frames, replay.comparison) : []),
    [replay],
  );
  useEffect(() => {
    if (
      replay &&
      replayPlaying &&
      previousReplay.current.id === replay.summary.session_id &&
      replayIndex === previousReplay.current.index + 1 &&
      replayIndex > 0
    ) {
      const previous = replay.frames[replayIndex - 1],
        current = replay.frames[replayIndex];
      if (current.crashed && !previous.crashed) gameAudio.event("collision");
      else if (current.overtakes > previous.overtakes)
        gameAudio.event("overtake");
    }
    previousReplay.current = {
      id: replay?.summary.session_id ?? "",
      index: replayIndex,
    };
  }, [replay, replayIndex, replayPlaying]);

  useEffect(() => {
    const ego = sceneSession?.frame.vehicles.find(
      (vehicle) => vehicle.id === sceneSession.frame.ego_id,
    );
    const playing = replay
      ? replayPlaying
      : driving.phase === "running" && !driving.session?.player_done;
    gameAudio.drive((ego?.speed ?? 0) * 3.6, playing, settings);
    gameAudio.music(playing || (!replay && driving.phase === "idle"), settings);
  }, [
    sceneSession,
    replay,
    replayPlaying,
    driving.phase,
    driving.session?.player_done,
    settings,
  ]);
  useEffect(() => () => gameAudio.silence(), []);
  useEffect(() => {
    const quiet = () => {
      setReplayPlaying(false);
      gameAudio.silence();
    };
    const visible = () => {
      if (document.hidden) quiet();
    };
    window.addEventListener("blur", quiet);
    document.addEventListener("visibilitychange", visible);
    return () => {
      window.removeEventListener("blur", quiet);
      document.removeEventListener("visibilitychange", visible);
    };
  }, []);

  const load = useCallback(async () => {
    try {
      const content = await api.catalog();
      setCatalog(content);
      setNotice("");
      void api
        .records()
        .then(setRecords)
        .catch(() => setRecords(null));
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "游戏服务连接失败");
    }
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);
  useEffect(() => {
    if (driving.phase === "finished")
      void api
        .records()
        .then(setRecords)
        .catch(() => undefined);
    if (
      settings.sound &&
      driving.phase === "finished" &&
      previousPhase.current !== "finished"
    ) {
      if (!driving.session?.crashed) gameAudio.event("finish");
    }
    previousPhase.current = driving.phase;
  }, [driving.phase, driving.session?.crashed, settings.sound]);
  useEffect(() => {
    const overtakes = driving.session?.overtakes ?? 0;
    if (settings.sound && overtakes > previousOvertakes.current)
      gameAudio.event("overtake");
    previousOvertakes.current = overtakes;
  }, [driving.session?.overtakes, settings.sound]);
  useEffect(() => {
    const crashed = driving.session?.crashed ?? false;
    if (crashed && !previousCrash.current) gameAudio.event("collision");
    previousCrash.current = crashed;
  }, [driving.session?.crashed]);
  useEffect(() => {
    if (settings.sound && driving.phase === "countdown")
      tone(400 + (3 - driving.countdown) * 100, 0.12);
  }, [driving.countdown, driving.phase, settings.sound]);

  const changeSettings = (next: Settings) => {
    if (next.sound) gameAudio.unlock();
    gameAudio.configure(next);
    setSettings(next);
    try {
      localStorage.setItem("lane-shift.settings", JSON.stringify(next));
    } catch {
      /* Settings still work for this run if local storage is disabled. */
    }
    if (next.sound) tone();
  };
  const fullscreen = () => {
    const operation = document.fullscreenElement
      ? document.exitFullscreen()
      : document.documentElement.requestFullscreen();
    void operation.catch(() => setNotice("当前窗口不支持全屏，可使用 F11。"));
  };
  const open = (next: Panel) => {
    if (settings.sound) tone(520, 0.045);
    setPanel(next);
    setNotice("");
    if (next === "records")
      void api
        .records()
        .then(setRecords)
        .catch((reason) => setNotice(String(reason)));
  };
  const menu = () => {
    replayRequest.current += 1;
    setReplayLoading(false);
    driving.stop();
    setReplay(null);
    setReplayPlaying(false);
    setPanel("menu");
    setCompletedRounds([]);
  };
  const start = (selected: Track | null = track, seed?: number) => {
    if (!sceneReady) {
      setNotice("道路画面尚未就绪，请等待加载或重试画面。");
      return false;
    }
    if (!selected) {
      setNotice("道路尚未加载，请重试连接或重新运行 Start-Game.cmd。");
      return false;
    }
    replayRequest.current += 1;
    setReplayLoading(false);
    setTrackId(selected.id);
    setPanel(null);
    setReplay(null);
    setReplayPlaying(false);
    setNotice("");
    if (settings.sound) {
      gameAudio.unlock();
      gameAudio.configure(settings);
    }
    void driving.start({
      mode: "duel",
      track_id: selected.id,
      policy: "v3_expert",
      seed,
      ai_level: "expert",
      vehicle: settings.vehicle ?? "sport",
      practice: false,
    });
    return true;
  };
  const beginChallenge = (selected: Track | null = track, seed?: number) => {
    if (start(selected, seed)) {
      if (selected) setChallengeStartId(selected.id);
      setCompletedRounds([]);
    }
  };

  const showReplay = async (id: string, time = 0, training = false) => {
    const request = ++replayRequest.current;
    setReplayLoading(true);
    setNotice("");
    try {
      const content = await (training
        ? api.trainingReplay(id)
        : api.replay(id));
      if (request !== replayRequest.current) return;
      if (training || driving.phase !== "finished") driving.stop();
      setPanel(null);
      setReplay(content);
      setReplayIndex(frameBefore(content.frames, Math.max(0, time - 3)));
      setReplayRate(1);
      setReplayPlaying(true);
    } catch (reason) {
      if (request === replayRequest.current)
        setNotice(reason instanceof Error ? reason.message : "无法读取回放");
    } finally {
      if (request === replayRequest.current) setReplayLoading(false);
    }
  };
  const exitReplay = () => {
    const training = Boolean(replay?.comparison);
    setReplay(null);
    setReplayPlaying(false);
    if (training) open("training");
    else if (driving.phase === "finished") setPanel(null);
    else open("records");
  };
  useEffect(() => {
    if (!replay || !replayPlaying) return;
    if (replayIndex >= replay.frames.length - 1) return;
    const timer = window.setTimeout(
      () => {
        const next = replayIndex + 1;
        setReplayIndex(next);
        if (next >= replay.frames.length - 1) setReplayPlaying(false);
      },
      Math.max(
        1,
        ((frameTime(replay.frames[replayIndex + 1]) -
          frameTime(replay.frames[replayIndex])) *
          1000) /
          replayRate,
      ),
    );
    return () => window.clearTimeout(timer);
  }, [replay, replayPlaying, replayRate, replayIndex]);

  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      if (
        replay &&
        sceneReady &&
        event.target instanceof HTMLElement &&
        !event.target.closest(
          "input,select,textarea,button,a,[contenteditable]",
        )
      ) {
        if (event.key === " ") {
          event.preventDefault();
          if (replayIndex === replay.frames.length - 1) setReplayIndex(0);
          setReplayPlaying((value) => !value);
          return;
        }
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
          event.preventDefault();
          const time =
            frameTime(replay.frames[replayIndex]) +
            (event.key === "ArrowRight" ? 1 : -1);
          setReplayIndex(frameBefore(replay.frames, Math.max(0, time)));
          setReplayPlaying(false);
          return;
        }
      }
      if (event.key === "Escape") {
        event.preventDefault();
        if (replayLoading) {
          replayRequest.current += 1;
          setReplayLoading(false);
          return;
        }
        if (replay) {
          exitReplay();
          return;
        }
        if (panel === "settings" && driving.phase === "paused") {
          setPanel(null);
          return;
        }
        if (driving.phase === "running" || driving.phase === "countdown")
          driving.pause();
        else if (driving.phase === "paused" && !panel) driving.resume();
        else if (panel && panel !== "menu") setPanel(returnPanel);
        return;
      }
    }
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  });

  const error = notice || driving.error;
  const nextTrack = challengeTracks[completedRounds.length + 1];
  const continueChallenge = () => {
    if (!driving.session?.done || !nextTrack) return;
    if (start(nextTrack, driving.session.seed))
      setCompletedRounds((rounds) => [...rounds, driving.session!]);
  };

  return (
    <div
      className={`lane-game ${!active ? "in-menu" : ""} ${settings.reducedMotion ? "reduced-motion" : ""}`}
      onPointerDownCapture={() => {
        if (settings.sound) {
          gameAudio.unlock();
          gameAudio.configure(settings);
          gameAudio.music(
            replay
              ? replayPlaying
              : driving.phase === "running" || driving.phase === "idle",
            settings,
          );
        }
      }}
      onKeyDownCapture={() => {
        if (settings.sound) {
          gameAudio.unlock();
          gameAudio.configure(settings);
        }
      }}
    >
      <Suspense fallback={<div className="game-scene" />}>
        <RoadScene
          session={sceneSession ?? null}
          active={active}
          theme={sceneSession?.track.theme ?? track?.theme ?? "coast"}
          settings={settings}
          playbackRate={replay ? replayRate : 1}
          replaying={Boolean(replay)}
          onReadyChange={sceneReadinessChanged}
          animate={
            replay ? replayPlaying : driving.phase === "running" || !active
          }
        />
      </Suspense>
      {!active && <div className="menu-shade" />}
      {panel === "menu" && (
        <div className="title-screen">
          <div className="title-top">
            <span className="game-monogram">LANE SHIFT</span>
            <button
              className="game-icon-button"
              aria-label="全屏显示"
              onClick={fullscreen}
            >
              <Icon name="expand" />
            </button>
          </div>
          <div className="title-content">
            <span className="title-overline">人机对决</span>
            <h1>变道之间</h1>
            <div className="title-chinese">三车道驾驶挑战</div>
            <p className="title-claim">
              与高手电脑同起点出发，在限时内安全完成行程。
            </p>
            <nav className="title-menu" aria-label="游戏主菜单">
              <button
                className="title-start"
                disabled={
                  !sceneReady ||
                  !catalog?.ai_levels?.find((item) => item.id === "expert")
                    ?.available
                }
                onClick={() =>
                  beginChallenge(catalog?.tracks[0] ?? null, 531124)
                }
              >
                <strong>开始人机对决</strong>
                <small>{!sceneReady ? "加载道路…" : "高手 · 三关连赛"}</small>
                <Icon name="play" />
              </button>
              <button
                onClick={() => {
                  setReturnPanel("menu");
                  open("setup");
                }}
                disabled={!catalog}
              >
                <strong>选择起始路线</strong>
                <Icon name="car" size={18} />
              </button>
              <details className="title-more">
                <summary>更多选项</summary>
                <button
                  onClick={() => {
                    setReturnPanel("menu");
                    open("records");
                  }}
                >
                  驾驶记录
                </button>
                <button
                  onClick={() => {
                    setReturnPanel("menu");
                    open("settings");
                  }}
                >
                  设置
                </button>
                <button onClick={() => open("training")} disabled={!catalog}>
                  训练成果
                </button>
              </details>
            </nav>
          </div>
          <div className="title-bottom">
            <span>← → 换道　↑ ↓ 调整车速　Esc 暂停</span>
            <span>{catalog ? `v${catalog.version}` : "正在连接"}</span>
          </div>
          <div className="title-road-label">
            <span>本次挑战</span>
            <strong>三关连赛</strong>
            <small>慢车编队 / 交织车流 / 连续高压</small>
          </div>
        </div>
      )}
      {panel === "setup" && catalog && track && (
        <Modal
          title="赛前准备"
          eyebrow="选择比赛"
          onBack={() => setPanel("menu")}
        >
          <Setup
            catalog={catalog}
            track={track}
            onTracks={() => {
              setReturnPanel("setup");
              open("levels");
            }}
            start={() => beginChallenge()}
          />
        </Modal>
      )}
      {panel === "training" && catalog && (
        <Modal
          title="训练成果"
          eyebrow="强化学习"
          onBack={() => setPanel("menu")}
          wide
        >
          <ModelShowcase
            tab={trainingTab}
            setTab={setTrainingTab}
            training={catalog.training}
            onReplay={(id) => void showReplay(id, 0, true)}
            onPlay={() =>
              beginChallenge(
                catalog.tracks.find((item) => item.id === "pressure") ?? null,
                531124,
              )
            }
          />
        </Modal>
      )}
      {panel === "levels" && catalog && (
        <Modal
          title="选择路线"
          eyebrow="三种路况"
          onBack={() => setPanel(returnPanel)}
          wide
        >
          <TrackList
            tracks={catalog.tracks}
            selected={trackId}
            choose={(selected) => {
              setTrackId(selected.id);
              setPanel("setup");
            }}
            records={records}
          />
        </Modal>
      )}
      {panel === "settings" && (
        <Modal
          title="设置"
          eyebrow="声音与画面"
          onBack={() =>
            setPanel(driving.phase === "paused" ? null : returnPanel)
          }
        >
          <SettingsPanel
            settings={settings}
            change={changeSettings}
            fullscreen={fullscreen}
          />
        </Modal>
      )}
      {panel === "records" && (
        <Modal
          title="驾驶记录"
          eyebrow="最近比赛"
          onBack={() => setPanel("menu")}
          wide
        >
          <RecordList records={records} replay={(id) => void showReplay(id)} />
        </Modal>
      )}
      {sceneSession && (
        <Hud
          session={sceneSession}
          pause={replay ? exitReplay : driving.pause}
          replay={Boolean(replay)}
          comparison={replay?.comparison}
          trafficPreview={settings.trafficPreview !== false}
          challenge={
            !replay
              ? {
                  round: completedRounds.length + 1,
                  total: challengeTracks.length,
                  ...matchScore,
                }
              : undefined
          }
        />
      )}
      {driving.phase === "countdown" && (
        <div className="countdown-screen">
          <span>准备出发</span>
          <strong key={driving.countdown}>
            {Math.max(1, driving.countdown)}
          </strong>
          <p>← → 换道 / ↑ ↓ 调速</p>
        </div>
      )}
      {driving.phase === "running" &&
        driving.session?.mode !== "ai" &&
        !driving.session?.player_done && (
          <div className="driving-buttons">
            <span>驾驶控制</span>
            {[
              [0, "←", "左换道"],
              [4, "↓", "减速"],
              [3, "↑", "加速"],
              [2, "→", "右换道"],
            ].map(([action, label, text]) => (
              <button
                key={action}
                aria-label={String(text)}
                className={
                  controls.pressed.includes(Number(action)) ? "is-pressed" : ""
                }
                onPointerDown={(event) => {
                  event.preventDefault();
                  event.currentTarget.setPointerCapture(event.pointerId);
                  controls.press(`pointer-${event.pointerId}`, Number(action));
                }}
                onPointerUp={(event) =>
                  controls.release(`pointer-${event.pointerId}`)
                }
                onPointerCancel={(event) =>
                  controls.release(`pointer-${event.pointerId}`)
                }
                onLostPointerCapture={(event) =>
                  controls.release(`pointer-${event.pointerId}`)
                }
                onClick={(event) => {
                  if (event.detail === 0) driving.action(Number(action));
                }}
              >
                <strong>{label}</strong>
                <small>{text}</small>
              </button>
            ))}
          </div>
        )}
      {driving.phase === "running" &&
        driving.session?.player_done &&
        !driving.session.done && (
          <div className="spectator-note">
            <span>你的行程已结束，对手仍在驾驶</span>
            <button onClick={() => void driving.finish()}>跳到结算 →</button>
          </div>
        )}
      {driving.phase === "paused" && !panel && (
        <Modal title="游戏暂停" eyebrow="暂停中" onBack={driving.resume}>
          <div className="pause-menu">
            <button className="game-primary" onClick={driving.resume}>
              继续驾驶 <Icon name="play" />
            </button>
            <button
              className="game-secondary"
              onClick={() =>
                start(driving.session?.track ?? track, driving.session?.seed)
              }
            >
              重新开始本局
            </button>
            <button
              className="game-secondary"
              onClick={() => setPanel("settings")}
            >
              设置
            </button>
            <button className="game-text-button" onClick={menu}>
              返回主菜单
            </button>
          </div>
        </Modal>
      )}
      {driving.phase === "finished" && driving.session && !panel && !replay && (
        <Results
          session={driving.session}
          rounds={[...completedRounds, driving.session]}
          totalRounds={challengeTracks.length}
          retry={() =>
            start(driving.session?.track ?? track, driving.session?.seed)
          }
          fresh={() => start(driving.session?.track ?? track)}
          menu={menu}
          replay={(time) => void showReplay(driving.session!.session_id, time)}
          next={nextTrack ? continueChallenge : undefined}
        />
      )}
      {(driving.phase === "loading" || replayLoading) && (
        <div className="game-loading">
          <div className="loading-ring" />
          <strong>{replayLoading ? "读取行程" : "准备道路"}</strong>
          <span>稍等片刻，即将出发</span>
        </div>
      )}
      {replay && (
        <>
          <div className="replay-events" aria-label="回放精彩时刻">
            {markers
              .filter((marker) => marker.kind !== "overtake")
              .concat(
                markers
                  .filter((marker) => marker.kind === "overtake")
                  .slice(0, 5),
              )
              .sort((a, b) => a.time - b.time)
              .map((marker, index) => (
                <button
                  key={`${marker.index}-${index}`}
                  className={marker.kind}
                  disabled={!sceneReady}
                  onClick={() => {
                    setReplayIndex(
                      frameBefore(replay.frames, Math.max(0, marker.time - 3)),
                    );
                    setReplayPlaying(true);
                  }}
                >
                  <span>
                    {marker.kind === "collision"
                      ? "!"
                      : marker.kind === "finish"
                        ? "✓"
                        : "↗"}
                  </span>
                  {marker.label}
                  <small>{marker.time.toFixed(1)}s</small>
                </button>
              ))}
          </div>
          <div className="replay-controller">
            <button
              className="game-icon-button"
              aria-label={replayPlaying ? "暂停回放" : "播放回放"}
              title="空格暂停或继续；左右键逐秒查看（光标不在控件上时）"
              disabled={!sceneReady}
              onClick={() => {
                if (replayIndex === replay.frames.length - 1) setReplayIndex(0);
                setReplayPlaying((p) => !p);
              }}
            >
              <Icon name={replayPlaying ? "pause" : "play"} />
            </button>
            <span>
              {Math.max(
                replay.frames[replayIndex].frame.time_s,
                replay.frames[replayIndex].rival?.frame.time_s ?? 0,
              ).toFixed(1)}
              s
            </span>
            <input
              aria-label="回放进度"
              type="range"
              min={0}
              max={replay.frames.length - 1}
              value={replayIndex}
              onChange={(e) => {
                setReplayIndex(Number(e.target.value));
                setReplayPlaying(false);
              }}
            />
            <select
              aria-label="回放倍速"
              value={replayRate}
              onChange={(e) => setReplayRate(Number(e.target.value))}
            >
              <option value={0.5}>0.5×</option>
              <option value={1}>1×</option>
              <option value={2}>2×</option>
              <option value={4}>4×</option>
            </select>
          </div>
        </>
      )}
      {error && (
        <div className="game-notice" role="alert">
          <span>{error}</span>
          {!catalog ? (
            <button onClick={() => void load()}>重试</button>
          ) : driving.phase === "idle" && !panel ? (
            <button onClick={() => setPanel("setup")}>返回</button>
          ) : (
            <button
              onClick={() => {
                setNotice("");
                if (driving.error) menu();
              }}
            >
              关闭
            </button>
          )}
        </div>
      )}
    </div>
  );
}
