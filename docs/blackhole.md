# Blackhole API

简要说明与示例

## 概述

系统提供管理员接口用于向路由器/ExaBGP 下发/撤销黑洞（RTBH）及审计日志查询与回滚。

所有管理接口需要在请求头中提供 `X-Admin-Key`，其值为环境变量 `OPEN_DCMS_ADMIN_API_KEY`（默认 `admin-secret`）。

## 接口

- POST `/api/v1/blackhole`
  - body: `{ "prefix": "203.0.113.0/24", "action": "add"|"remove", "adapter": "exabgp", "community": "65000:666" }`
  - 返回: `{ "result": true, "detail": "ok db_id=1" }`

- GET `/api/v1/blackhole/logs?limit=100&prefix=203.0.113.0/24`
  - 返回审计日志: `{ "logs": [ {id, prefix, action, adapter, community, result, detail, operator, performed_at}, ... ] }`

- POST `/api/v1/blackhole/revert`
  - body: `{ "id": <log_id> }` - 对指定日志执行反向操作（add ↔ remove）并生成新日志
  - 返回: `{ "result": true, "detail": "ok", "log_id": 2 }`

## curl 示例

下发黑洞：

```bash
curl -X POST http://localhost:8001/api/v1/blackhole \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: admin-secret" \
  -d '{"prefix":"203.0.113.0/24","action":"add","adapter":"exabgp","community":"65000:666"}'
```

查询日志：

```bash
curl -H "X-Admin-Key: admin-secret" "http://localhost:8001/api/v1/blackhole/logs?limit=50"
```

回滚操作：

```bash
curl -X POST http://localhost:8001/api/v1/blackhole/revert \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: admin-secret" \
  -d '{"id":1}'
```
