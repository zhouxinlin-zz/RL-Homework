import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import type { GameSession, Settings, Theme, WorldFrame } from "./types";
import { CarLibrary } from "./scene/assets";
import { DrivingView } from "./scene/DrivingView";

type Props = {
  session: GameSession | null;
  theme: Theme;
  settings: Settings;
  active: boolean;
  playbackRate?: number;
  replaying?: boolean;
  animate?: boolean;
  onReadyChange: (ready: boolean) => void;
};

function attractFrame(time: number): WorldFrame {
  const distance = time * 19;
  return {
    step: Math.floor(time * 5),
    time_s: time,
    action: 1,
    reward: 0,
    ego_id: 0,
    target_lane: 1,
    vehicles: [
      {
        id: 0,
        x: distance,
        y: 4,
        speed: 25,
        heading: 0,
        length: 4.6,
        width: 1.9,
        crashed: false,
      },
      ...Array.from({ length: 10 }, (_, index) => ({
        id: index + 1,
        x:
          distance +
          ((((index * 23 - time * (1 + (index % 3))) % 230) + 230) % 230) -
          24,
        y: (index % 3) * 4,
        speed: 19,
        heading: 0,
        length: index % 4 === 0 ? 8 : 4.6,
        width: index % 4 === 0 ? 2.3 : 1.85,
        crashed: false,
        kind: index % 4 === 0 ? "truck" : index % 3 === 0 ? "suv" : "sedan",
      })),
    ],
  };
}

export default function RoadScene(props: Props) {
  const host = useRef<HTMLDivElement>(null);
  const latest = useRef(props);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    latest.current = props;
  }, [props]);
  useEffect(() => {
    const element = host.current!;
    latest.current.onReadyChange(false);
    delete element.dataset.rendered;
    const library = new CarLibrary();
    let renderer: THREE.WebGLRenderer | undefined;
    let views: DrivingView[] = [];
    let theme: Theme | undefined;
    let sessionId = "";
    let disposed = false;
    let contextFailed = false;
    let raf = 0;
    let width = 0,
      height = 0,
      last = 0,
      menuTime = 0;
    let frames = 0,
      sampledAt = 0;
    const contextLost = (event: Event) => {
      event.preventDefault();
      contextFailed = true;
      setError("画面连接中断，比赛已暂停。可以尝试重新加载画面。");
      latest.current.onReadyChange(false);
      cancelAnimationFrame(raf);
    };
    const initialize = async () => {
      try {
        renderer = new THREE.WebGLRenderer({
          antialias: true,
          powerPreference: "high-performance",
        });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.05;
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        renderer.domElement.addEventListener("webglcontextlost", contextLost);
        element.appendChild(renderer.domElement);
        await library.load();
        if (disposed) {
          library.dispose();
          return;
        }
        if (contextFailed) return;
        element.dataset.engine = "three";
        setError("");
        const render = (now: number) => {
          if (disposed || contextFailed || !renderer) return;
          if (document.hidden) {
            last = now;
            raf = requestAnimationFrame(render);
            return;
          }
          const p = latest.current;
          const duel = p.active && Boolean(p.session?.rival);
          const selectedTheme = !p.active ? "coast" : p.theme;
          const count = duel ? 2 : 1;
          if (theme !== selectedTheme || views.length !== count) {
            views.forEach((view) => view.dispose());
            views = Array.from(
              { length: count },
              () => new DrivingView(library, selectedTheme),
            );
            theme = selectedTheme;
            sessionId = "";
          }
          const nextWidth = element.clientWidth,
            nextHeight = element.clientHeight;
          if (width !== nextWidth || height !== nextHeight) {
            width = nextWidth;
            height = nextHeight;
            renderer.setSize(width, height, false);
          }
          const dt = Math.min(0.05, (now - last) / 1000);
          last = now;
          if (p.animate && !document.hidden && !p.settings.reducedMotion)
            menuTime += dt;
          const id = p.active ? (p.session?.session_id ?? "loading") : "menu";
          const reset = sessionId !== id;
          const menuFrame =
            !p.active || !p.session ? attractFrame(menuTime) : null;
          renderer.setScissorTest(true);
          views.forEach((view, index) => {
            const frame =
              menuFrame ??
              (index === 1 ? p.session!.rival!.frame : p.session!.frame);
            view.setFrame(
              frame,
              now,
              p.playbackRate ?? 1,
              Boolean(p.replaying),
              reset,
            );
            const viewportWidth =
              index === count - 1
                ? width - Math.floor(width / count) * index
                : Math.floor(width / count);
            view.render(
              now,
              p.settings,
              index === 1,
              !p.active,
              Boolean(p.animate) && !menuFrame,
              viewportWidth / Math.max(1, height),
            );
            renderer!.setViewport(
              Math.floor(width / count) * index,
              0,
              viewportWidth,
              height,
            );
            renderer!.setScissor(
              Math.floor(width / count) * index,
              0,
              viewportWidth,
              height,
            );
            renderer!.render(view.scene, view.camera);
          });
          sessionId = id;
          element.dataset.rendered = "true";
          if (frames === 0 && sampledAt === 0)
            latest.current.onReadyChange(true);
          frames++;
          if (now - sampledAt >= 1000) {
            element.dataset.fps = String(
              Math.round((frames * 1000) / (now - sampledAt)),
            );
            frames = 0;
            sampledAt = now;
          }
          raf = requestAnimationFrame(render);
        };
        raf = requestAnimationFrame(render);
      } catch (reason) {
        library.dispose();
        if (!disposed) {
          latest.current.onReadyChange(false);
          setError(
            `画面加载失败：${reason instanceof Error ? reason.message : "请刷新重试"}`,
          );
        }
      }
    };
    void initialize();
    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      views.forEach((view) => view.dispose());
      library.dispose();
      if (renderer) {
        renderer.domElement.removeEventListener(
          "webglcontextlost",
          contextLost,
        );
        renderer.dispose();
        renderer.forceContextLoss();
        renderer.domElement.remove();
      }
    };
  }, [attempt]);
  return (
    <>
      <div
        ref={host}
        className="game-scene"
        role="img"
        aria-label="高速公路驾驶游戏画面"
      />
      {error && (
        <div className="game-notice" role="alert">
          <span>{error}</span>
          <button
            onClick={() => {
              setError("");
              setAttempt((value) => value + 1);
            }}
          >
            重试画面
          </button>
        </div>
      )}
    </>
  );
}
