from fastapi import FastAPI, Header, HTTPException, Request, status, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
import os
import json
from datetime import datetime
from backend import auth
from backend import db
from uuid import uuid4
import asyncio


class ConnectionManager:
    def __init__(self):
        # tenant_id -> set of websockets
        self._conns = {}
        self._lock = asyncio.Lock()

    async def connect(self, tenant: str, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._conns.setdefault(tenant, set()).add(ws)

    async def disconnect(self, tenant: str, ws: WebSocket):
        async with self._lock:
            conns = self._conns.get(tenant)
            if conns and ws in conns:
                conns.remove(ws)

    async def broadcast(self, tenant: str, message: str):
        async with self._lock:
            conns = list(self._conns.get(tenant, []))
        for ws in conns:
            try:
                await ws.send_text(message)
            except Exception:
                # ignore send errors; cleanup happens on disconnect
                pass


manager = ConnectionManager()

app = FastAPI(title="Open-DCMS Ingest API")

API_KEY = os.getenv("OPEN_DCMS_API_KEY", "dev-secret")
DATA_DIR = os.getenv("OPEN_DCMS_DATA_DIR", ".data")
os.makedirs(DATA_DIR, exist_ok=True)


class IngestPayload(BaseModel):
    tenant_id: str
    source: str
    timestamp: Optional[float]
    payload: dict


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/ingest")
async def ingest(item: IngestPayload, x_api_key: Optional[str] = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")

    tenant = item.tenant_id or "default"
    fname = os.path.join(DATA_DIR, f"{tenant}.jsonl")
    record = {
        "received_at": datetime.utcnow().isoformat() + "Z",
        "source": item.source,
        "timestamp": item.timestamp,
        "payload": item.payload,
    }
    with open(fname, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Broadcast to any WebSocket subscribers for this tenant
    try:
        # fire-and-forget broadcast
        asyncio.create_task(manager.broadcast(tenant, json.dumps(record, ensure_ascii=False)))
    except Exception:
        pass

    return {"result": "stored", "tenant": tenant}


# --- Auth endpoints (token / refresh / protected examples) ---


class TokenRequest(BaseModel):
    tenant_id: str
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2:
        return None
    if parts[0].lower() != 'bearer':
        return None
    return parts[1]


@app.post('/token')
def token(req: TokenRequest):
    # authenticate using DB-backed auth
    uid = auth.authenticate_user(req.tenant_id, req.username, req.password)
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid credentials')
    toks = auth.issue_tokens_for_user(uid)
    return toks


@app.post('/refresh')
def refresh(req: RefreshRequest):
    out = auth.refresh_access_token(req.refresh_token)
    if not out:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid refresh token')
    return out


def get_current_user_from_header(authorization: Optional[str] = Header(None)):
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='missing token')
    payload = auth.get_user_from_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid token')
    return payload


@app.get('/whoami')
def whoami(current=Depends(get_current_user_from_header)):
    return current


@app.get('/admin-only')
def admin_only(current=Depends(get_current_user_from_header)):
    roles = current.get('roles', [])
    if 'admin' not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='admin role required')
    return {'ok': True, 'user': current.get('sub')}


class CreateUserRequest(BaseModel):
    tenant_id: str
    username: str
    password: str
    roles: Optional[list] = None


class ResetPasswordRequest(BaseModel):
    tenant_id: str
    username: str
    new_password: str


@app.post('/users')
def create_user_endpoint(req: CreateUserRequest, request: Request, current=Depends(get_current_user_from_header)):
    # require admin role and tenant match
    roles = current.get('roles', [])
    if 'admin' not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='admin role required')
    # tenant isolation: admin can only create users in their tenant
    if current.get('tenant') != req.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='cannot create user for other tenant')
    uid = auth.create_user(req.tenant_id, req.username, password=req.password, roles=req.roles)
    # audit: record operator, ip, request id, user agent and request path
    operator = current.get('user_id')
    ip = request.client.host if request.client else None
    req_id = request.headers.get('X-Request-ID') or uuid4().hex
    user_agent = request.headers.get('user-agent')
    path = str(request.url.path)
    try:
        db.log_user_audit(operator_user_id=operator, action='create_user', target_user_id=uid, target_username=req.username, tenant_id=req.tenant_id, details=f"roles={req.roles}", operator_ip=ip, request_id=req_id, user_agent=user_agent, request_path=path)
    except Exception:
        pass
    return {'user_id': uid, 'username': req.username, 'tenant': req.tenant_id}


@app.post('/users/reset-password')
def reset_password_endpoint(req: ResetPasswordRequest, request: Request, current=Depends(get_current_user_from_header)):
    roles = current.get('roles', [])
    if 'admin' not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='admin role required')
    if current.get('tenant') != req.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='cannot reset user for other tenant')
    ok = auth.set_user_password(req.tenant_id, req.username, req.new_password)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='user not found')
    operator = current.get('user_id')
    ip = request.client.host if request.client else None
    req_id = request.headers.get('X-Request-ID') or uuid4().hex
    user_agent = request.headers.get('user-agent')
    path = str(request.url.path)
    try:
        db.log_user_audit(operator_user_id=operator, action='reset_password', target_user_id=None, target_username=req.username, tenant_id=req.tenant_id, details='reset via admin', operator_ip=ip, request_id=req_id, user_agent=user_agent, request_path=path)
    except Exception:
        pass
    return {'result': 'ok'}



@app.get('/users/audit')
def get_user_audit(tenant_id: str, limit: int = 50, cursor: Optional[str] = None, current=Depends(get_current_user_from_header)):
    # require admin role and tenant match
    roles = current.get('roles', [])
    if 'admin' not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='admin role required')
    if current.get('tenant') != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='cannot list audit for other tenant')
    res = db.list_user_audit(tenant_id=tenant_id, limit=limit, cursor=cursor)
    return res


@app.websocket('/ws/telemetry/{tenant_id}')
async def websocket_telemetry(websocket: WebSocket, tenant_id: str):
    """Simple WebSocket endpoint to stream ingest events for a tenant."""
    await manager.connect(tenant_id, websocket)
    try:
        while True:
            # keep the connection alive; echo pings
            data = await websocket.receive_text()
            # clients may send 'ping' to keep connection alive; ignore payload
            if data == 'ping':
                await websocket.send_text('pong')
    except WebSocketDisconnect:
        await manager.disconnect(tenant_id, websocket)
    except Exception:
        try:
            await manager.disconnect(tenant_id, websocket)
        except Exception:
            pass
