from fastapi import FastAPI, Header, HTTPException, Request, status, Depends
from pydantic import BaseModel
from typing import Optional
import os
import json
from datetime import datetime
from backend import auth
from backend import db
from uuid import uuid4

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
    # audit
    operator = current.get('user_id')
    ip = request.client.host if request.client else None
    req_id = request.headers.get('X-Request-ID') or uuid4().hex
    db.log_user_audit(operator_user_id=operator, action='create_user', target_user_id=uid, target_username=req.username, tenant_id=req.tenant_id, details=f"roles={req.roles}",)
    # update audit record with ip and request id by inserting with fields
    # (log_user_audit currently accepts operator_ip/request_id via kwargs if provided)
    try:
        db.log_user_audit(operator_user_id=operator, action='create_user', target_user_id=uid, target_username=req.username, tenant_id=req.tenant_id, details=f"roles={req.roles}",)
    except Exception:
        pass
    # For compatibility we also store operator_ip/request_id by direct call
    try:
        dbs = db.SessionLocal()
        obj = dbs.query(db.UserAudit).order_by(db.UserAudit.performed_at.desc()).first()
        if obj:
            obj.operator_ip = ip
            obj.request_id = req_id
            dbs.add(obj)
            dbs.commit()
    finally:
        try:
            dbs.close()
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
    try:
        dbs = db.SessionLocal()
        obj_id = db.log_user_audit(operator_user_id=operator, action='reset_password', target_user_id=None, target_username=req.username, tenant_id=req.tenant_id, details='reset via admin')
        # update with ip/request id
        row = dbs.query(db.UserAudit).filter(db.UserAudit.id == obj_id).first()
        if row:
            row.operator_ip = ip
            row.request_id = req_id
            dbs.add(row)
            dbs.commit()
    finally:
        try:
            dbs.close()
        except Exception:
            pass
    return {'result': 'ok'}
