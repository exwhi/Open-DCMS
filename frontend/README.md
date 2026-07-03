快速启动前端（需要 Node.js >=16）

1. 进入前端目录并安装依赖：

```bash
cd frontend
npm install
```

2. 启动开发服务器：

```bash
npm run dev
```

页面地址通常为 `http://localhost:5173`。

说明：这是一个最小 DCIM 演示视图；后续我可以将其对接后端 API 动态渲染机房/机柜/服务器状态。

WebSocket Telemetry Demo
------------------------

You can use the included static demo page to connect to the backend WebSocket telemetry endpoint and view realtime messages.

1. Start the backend (FastAPI) server, for example:

```bash
# from repo root
uvicorn backend.app.main_fastapi:app --reload --port 8000
```

2. Open `frontend/ws_demo.html` in a browser and set the WS URL to `ws://localhost:8000/ws/telemetry/<tenant>` (for example `demo`).

3. Click Connect and watch incoming telemetry as ingest calls are made.

