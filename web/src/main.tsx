import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import GameApp from "./game/GameApp";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <GameApp />
  </StrictMode>,
);
