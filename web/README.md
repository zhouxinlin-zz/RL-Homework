# 前端开发

React 19、TypeScript 和 Three.js。菜单、对决和回放由 React 管理；道路使用单个 WebGLRenderer 绘制两个视口。仿真和模型推理由 FastAPI 服务提供。

## 启动开发服务

在项目根目录启动后端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8765
```

另开终端进入 `web/`：

```powershell
npm ci
npm run dev
```

Vite 将 `/api` 请求转发到 `127.0.0.1:8765`。车型从 `public/models/` 加载，不需要外部素材服务。普通运行方式见[项目说明](../README.md)。

## 构建与检查

```powershell
npm test
npm run lint
npm run build
npx playwright test
npx playwright test --config playwright.audio.config.ts
```

- `npm test`：输入、会话生命周期、赛程和回放等逻辑测试。
- `npm run lint`：Oxlint 静态检查。
- `npm run build`：TypeScript 检查、Vite 构建，并生成内容哈希清单。
- Playwright：在 Edge 中测试三关对决、暂停、回放、训练页面、渲染与键盘操作。
- 音频测试：检查真实 Web Audio 输出在驾驶、暂停和关闭音效时的变化。

浏览器测试会启动独立后端，分别使用 8766 和 8768 端口，存档写入测试目录。截图在 `artifacts/browser-previews/`，不覆盖文档中提交的图片。

`dist/` 随仓库提交。修改源码、素材或依赖后重新构建，再一起提交构建文件；启动器通过 `dist/build-info.json` 判断构建是否匹配源码。

## 代码入口

`src/main.tsx` 直接加载 `src/game/GameApp.tsx`。共享状态类型在 `src/game/types.ts`，服务请求集中在 `api.ts`，驾驶请求生命周期在 `useDriving.ts`。渲染器和车辆素材的释放由 `RoadScene.tsx` 与 `scene/` 管理。

界面只显示服务器返回的驾驶状态和成绩。涉及规则和指标的修改应同步检查 Python 环境及冻结评估记录。
