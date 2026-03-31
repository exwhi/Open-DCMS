# Open-DCMS — MVP Scaffold

简介：本仓库包含 Open-DCMS MVP 的最小可运行脚手架：一个 FastAPI 后端、一个轻量采集 Agent、以及 Kubernetes 清单示例。

快速开始（在有 Docker 与 kubectl 的环境）：

构建后端镜像（推荐在 Python 3.11 环境运行 FastAPI）：

```bash
# 使用 backend 目录中的 Dockerfile（基于 python:3.11）构建镜像
docker build -t open-dcms-backend:local ./backend
```

构建 Agent（可选）：

```bash
docker build -t open-dcms-agent:local -f agent/Dockerfile ./agent
```

在 Kubernetes 中部署（示例）:

```bash
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/agent-daemonset.yaml
```

本地使用 Docker 运行完整 FastAPI（避免本地 Python 3.12 兼容问题）：

```bash
# 构建并运行后端容器（将使用 backend/app/main_fastapi.py）
docker build -t open-dcms-backend:local ./backend
docker run -p 8000:8000 -e OPEN_DCMS_API_KEY=dev-secret open-dcms-backend:local uvicorn backend.app.main_fastapi:app --host 0.0.0.0 --port 8000
```

本地快速运行（无需 Docker）：

```bash
# 后端
pip install -r backend/requirements.txt
uvicorn app.main:app --reload --port 8000 --app-dir backend

# 采集端
pip install -r agent/requirements.txt
python agent/agent.py --server http://localhost:8000 --tenant demo
```

更多设计文档见 `docs/architecture.md`。

查询 API 与前端导出
------------------

项目提供一个简单的查询接口 `/api/v1/query`，支持按 `tenant`、`source`、时间范围 `since`/`until`、以及 `limit` 分页查询。查询返回 `items`、`total` 和 `next_cursor`（用于翻页）。

在前端：
- `QueryView` 组件提供查询表单并支持“导出 CSV”按钮，能将当前查询结果导出为 CSV 文件。
- `RoomView` 在拉取最新状态后会自动请求最近的 5 条 telemetry 作为预览，并提供“导出 预览 CSV”按钮以便快速保存示例数据。

参见文档：`docs/query_api.md`，里面有参数与 next_cursor 的示例。
