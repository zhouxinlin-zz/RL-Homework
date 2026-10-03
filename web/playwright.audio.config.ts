import { defineConfig } from "@playwright/test";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const externalURL = process.env.LANE_SHIFT_AUDIO_URL;

export default defineConfig({
  testDir: "./audio-e2e",
  timeout: 45000,
  expect: { timeout: 10000 },
  workers: 1,
  reporter: "list",
  outputDir: "../artifacts/audio-tests/run",
  use: {
    baseURL: externalURL ?? "http://127.0.0.1:8768",
    channel: "msedge",
    headless: true,
    viewport: { width: 1440, height: 900 },
  },
  webServer: externalURL
    ? undefined
    : {
        command:
          '".venv/Scripts/python.exe" -m uvicorn server.app:app --host 127.0.0.1 --port 8768',
        cwd: root,
        url: "http://127.0.0.1:8768/api/game/catalog",
        reuseExistingServer: false,
        timeout: 60000,
        env: {
          LANE_SHIFT_DATA_DIR: path.join(root, "artifacts/audio-test-data"),
        },
      },
});
