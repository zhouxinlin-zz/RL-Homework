import { defineConfig } from '@playwright/test';
import path from 'node:path';
const root = path.resolve(import.meta.dirname, '..');
export default defineConfig({
  testDir: './e2e',
  timeout: 90000,
  expect: { timeout: 15000 },
  workers: 1,
  reporter: 'list',
  outputDir: '../artifacts/browser-tests',
  use: { baseURL: 'http://127.0.0.1:8766', channel: 'msedge', headless: true, viewport: { width: 1440, height: 900 }, screenshot: 'only-on-failure' },
  webServer: {
    command: '".venv/Scripts/python.exe" -m uvicorn server.app:app --host 127.0.0.1 --port 8766',
    cwd: root,
    url: 'http://127.0.0.1:8766/api/game/catalog',
    reuseExistingServer: false,
    timeout: 60000,
    env: { LANE_SHIFT_DATA_DIR: path.join(root, 'artifacts/browser-test-data') },
  },
});
