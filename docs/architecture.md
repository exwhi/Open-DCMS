## Open-DCMS 架构草案（MVP）

概要：基于先前企划书与决策，本 MVP 采用以下技术栈：

- 后端：Python + FastAPI（REST API，易于扩展分析流程）
- 部署：Kubernetes（用户选择），提供 Deployment/Service 示例
- 时序/存储建议：PostgreSQL + TimescaleDB（元数据 + 小规模时序）、ClickHouse（海量流量日志）
- 缓存/队列：Redis（缓存与短期队列）
- 采集端：轻量 Python Agent（可扩展为 Telegraf/Exporter）
- DDoS 控制链路：ExaBGP / Router API（后续模块）

组件清单：

- Agent：采集 ASN、sFlow/NetFlow（或上游采样）、环境数据，支持本地缓存与增量上传
- Ingest API：接收采集端数据，按租户分发到持久层与分析队列
- 存储层：关系型存储 + 时序数据库 + ClickHouse 日志仓库
- 分析/检测：流量聚合、异常检测（阈值/ML），触发告警与黑洞指令
- 控制层：路由器下发接口（ExaBGP/厂商 API）
- 前端：Vue3 + ECharts/Leaflet，显示 DCIM 视图与流量

下一步：实现 `Ingest API` 与 `Agent` 的最小交互协议（JSON over HTTPS + API Key / mTLS）。
