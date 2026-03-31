# /api/v1/query

查询 telemetry 数据的简单 HTTP API（DB 必须启用）。

参数（GET QueryString）：
- `tenant` (optional)
- `limit` (optional, default 100)
- `offset` (optional, default 0)
- `cursor` (optional) — 支持数字 id 或 opaque token（base64 JSON `{ "last_id": <id> }`），用于 cursor 分页
- `source` (optional) — 精确匹配 `source` 字段
- `payload_key` (optional) — 仅返回包含该 key 的 JSON payload 记录（在 server-side 或 Python 端过滤）
- `since` / `until` (optional) — ISO8601 时间字符串；若 `ts` 可解析为 datetime，会使用解析后的 `ts_dt` 列进行范围过滤

响应 JSON:
```
{
  "total": <int>,
  "limit": <int>,
  "offset": <int>,
  "items": [ { id, tenant, received_at, source, timestamp, payload }, ... ],
  "next_cursor": <opaque token or id or null>
}
```

说明：
- 如果 DB 未启用，则返回 404 `{"detail":"DB not enabled"}`。
- `next_cursor` 为 base64 编码的 JSON（`{"last_id":N}`），客户端应直接将其作为 `cursor` 传回以加载下一页。
- 对于生产环境，建议将 `payload` 存为 JSONB（Postgres）或使用 ClickHouse，优化过滤与索引。