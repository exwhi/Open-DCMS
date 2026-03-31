ExaBGP Adapter (生产级指南)
=================================

配置要点
 - `endpoint`: HTTP URL（例如 `http://127.0.0.1:9000/exabgp`）作为回退通道
 - `tcp_host` / `tcp_port`: 优先使用 TCP socket 直接发送 JSON 行（更低延迟、可用作 Unix socket 替代）
 - `timeout`: 秒，HTTP/TCP 超时（默认 5）
 - `retries`: 重试次数（默认 2）

示例
```
from backend.router_adapters import ExaBGPAdapter
adapter = ExaBGPAdapter('exabgp', config={'tcp_host':'127.0.0.1','tcp_port':9000,'timeout':5,'retries':2})
adapter.send_blackhole('198.51.100.0/25')
adapter.remove_blackhole('198.51.100.0/25')
```

测试
 - 本仓库包含 `backend/exabgp_poc_server.py`，可作为本地测试端点。
 - 也可运行 `python -m unittest discover backend/tests -v` 来运行适配器单元测试。

安全/生产注意事项
 - 在生产中使用前请先在沙箱中验证命令/控制通道，避免误下发。
 - 添加认证（API key / mTLS）并限制速率。
 - 保持审计日志并支持 revert（仓库中已有审计模型）。
