import { lazy, Suspense } from "react";
import GameApp from "./game/GameApp";

const ExperimentView = lazy(() => import("./App"));

export default function ShellApp() {
  return window.location.pathname === "/research" ? (
    <Suspense fallback={<p>加载实验档案…</p>}>
      <ExperimentView
        onBack={() => {
          window.location.href = "/";
        }}
      />
    </Suspense>
  ) : (
    <GameApp />
  );
}
