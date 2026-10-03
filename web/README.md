# LANE SHIFT 前端

这是课程项目的游戏界面。React 与 TypeScript 管理菜单、对决、操作、回放和设置；PixiJS 绘制道路与车辆；所有可玩车流、AI 动作与得分来自本地 FastAPI 服务。主入口为同起点人机对决，三条新版编队车流关卡在前，经典路线收进次级列表。

普通玩家请在项目根目录双击 `Start-Game.cmd`。前端开发时可分别启动后端和 Vite：

```powershell
# 项目根目录
.\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8765

# 另一个终端进入 web 目录
npm ci
npm run dev
```

`npm run build` 生成后端直接托管的 `dist/`；`npm test` 验证交互逻辑；`npm run lint` 检查代码；`npm run test:e2e` 使用隔离的测试后端和真实浏览器检查对决、回放及移动端操作；`npx playwright test --config playwright.audio.config.ts` 检查音频输出、暂停静音和设置。主项目介绍、模型协议及安装步骤见 [根目录 README](../README.md)。
