"""DB-backed 多租户与 RBAC 实现（PoC 级）。

功能：
- 在 `backend.db` 中使用 `TenantModel` / `UserModel` / `RefreshToken` 表
- 密码使用 PBKDF2-HMAC-SHA256 存储（简单实现，生产请使用成熟库）
- 使用 `backend.auth_jwt` 生成 access token（JWT）并在 DB 中存储 refresh token
"""
from typing import Optional, List
import os
import hashlib
import binascii
from datetime import datetime, timedelta

from backend import db
from backend import auth_jwt
from dataclasses import dataclass


@dataclass
class LegacyTenant:
    id: str
    name: str


@dataclass
class LegacyUser:
    id: str
    username: str
    tenant_id: str
    roles: list


_JWT_SECRET = os.getenv('OPEN_DCMS_JWT_SECRET', 'dev-secret')
_ACCESS_EXPIRES = int(os.getenv('OPEN_DCMS_JWT_EXP', '3600'))
_REFRESH_EXPIRES_DAYS = int(os.getenv('OPEN_DCMS_REFRESH_DAYS', '7'))


def _hash_password(password: str, salt: Optional[bytes] = None) -> (str, str):
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return binascii.hexlify(dk).decode(), binascii.hexlify(salt).decode()


def _verify_password(stored_hash: str, stored_salt: str, password: str) -> bool:
    salt = binascii.unhexlify(stored_salt)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return binascii.hexlify(dk).decode() == stored_hash


def create_tenant(name: str) -> str:
    """Create tenant in DB and return tenant id string."""
    tid = db.create_tenant_db(name)
    return tid


def create_tenant_obj(name: str):
    """Compatibility helper: create tenant and return LegacyTenant object."""
    tid = db.create_tenant_db(name)
    return LegacyTenant(id=tid, name=name)


def create_user(tenant_id: str, username: str, password: Optional[str] = None, roles: Optional[List[str]] = None) -> str:
    """Create user in DB and return user id string."""
    roles_s = ','.join(roles) if roles else ''
    password_hash = None
    password_salt = None
    if password:
        password_hash, password_salt = _hash_password(password)
    uid = db.create_user_db(tenant_id, username, password_hash=password_hash, password_salt=password_salt, roles=roles_s)
    return uid


def create_user_obj(tenant_id: str, username: str, password: Optional[str] = None, roles: Optional[List[str]] = None):
    """Compatibility helper: create user and return LegacyUser object."""
    uid = create_user(tenant_id, username, password=password, roles=roles)
    return LegacyUser(id=uid, username=username, tenant_id=tenant_id, roles=roles or [])


def issue_token(tenant_id: str, username: str) -> str:
    # compatibility wrapper for PoC tests: issue an access JWT for existing user
    row = db.get_user_db(tenant_id, username)
    if not row:
        raise KeyError('user not found')
    toks = issue_tokens_for_user(row.id)
    return toks['access_token']


def get_user_from_token(token: str) -> Optional[LegacyUser]:
    payload = get_user_from_access_token(token)
    if not payload:
        return None
    return LegacyUser(id=payload.get('user_id'), username=payload.get('sub'), tenant_id=payload.get('tenant'), roles=payload.get('roles', []))


def authenticate_user(tenant_id: str, username: str, password: str) -> Optional[str]:
    row = db.get_user_db(tenant_id, username)
    if not row:
        return None
    if row.password_hash and row.password_salt:
        if _verify_password(row.password_hash, row.password_salt, password):
            return row.id
        return None
    # if no password stored, deny
    return None


def issue_tokens_for_user(user_id: str) -> dict:
    # lookup user
    dbs = db.SessionLocal()
    try:
        u = dbs.query(db.UserModel).filter(db.UserModel.id == user_id).first()
        if not u:
            raise KeyError('user not found')
        roles = u.roles.split(',') if u.roles else []
        payload = {'sub': u.username, 'tenant': u.tenant_id, 'user_id': u.id, 'roles': roles}
        access = auth_jwt.create_token(payload, _JWT_SECRET, expires_in=_ACCESS_EXPIRES)
        # create refresh token
        refresh = str(hashlib.sha256(os.urandom(32)).hexdigest())
        expires_at = datetime.utcnow() + timedelta(days=_REFRESH_EXPIRES_DAYS)
        db.store_refresh_token(refresh, u.id, expires_at=expires_at)
        return {'access_token': access, 'refresh_token': refresh, 'token_type': 'bearer'}
    finally:
        dbs.close()


def refresh_access_token(refresh_token: str) -> Optional[dict]:
    rt = db.validate_refresh_token_db(refresh_token)
    if not rt:
        return None
    # find user
    dbs = db.SessionLocal()
    try:
        u = dbs.query(db.UserModel).filter(db.UserModel.id == rt.user_id).first()
        if not u:
            return None
        roles = u.roles.split(',') if u.roles else []
        payload = {'sub': u.username, 'tenant': u.tenant_id, 'user_id': u.id, 'roles': roles}
        access = auth_jwt.create_token(payload, _JWT_SECRET, expires_in=_ACCESS_EXPIRES)
        return {'access_token': access, 'token_type': 'bearer'}
    finally:
        dbs.close()


def revoke_refresh_token(token: str) -> bool:
    return db.revoke_refresh_token_db(token)


def set_user_password(tenant_id: str, username: str, new_password: str) -> bool:
    """Set or reset a user's password (store PBKDF2 hash). Returns True if updated."""
    row = db.get_user_db(tenant_id, username)
    if not row:
        return False
    new_hash, new_salt = _hash_password(new_password)
    ds = db.SessionLocal()
    try:
        user = ds.query(db.UserModel).filter(db.UserModel.id == row.id).first()
        if not user:
            return False
        user.password_hash = new_hash
        user.password_salt = new_salt
        ds.add(user)
        ds.commit()
        return True
    finally:
        ds.close()


def get_user_from_access_token(token: str):
    try:
        payload = auth_jwt.verify_token(token, _JWT_SECRET)
        return payload
    except Exception:
        return None


def require_role(role: str):
    def decorator(fn):
        def wrapper(token: str, *args, **kwargs):
            payload = get_user_from_access_token(token)
            if not payload:
                raise PermissionError('invalid token')
            roles = payload.get('roles', [])
            if role not in roles:
                raise PermissionError('insufficient role')
            return fn(token, *args, **kwargs)

        wrapper.__name__ = fn.__name__
        return wrapper

    return decorator


def clear_stores():
    # helper for tests: drop created tenants/users/refresh tokens
    dbs = db.SessionLocal()
    try:
        dbs.query(db.RefreshToken).delete()
        dbs.query(db.UserModel).delete()
        dbs.query(db.TenantModel).delete()
        dbs.commit()
    finally:
        dbs.close()
import os
import json
import uuid
from threading import Lock

USE_DB = os.getenv("OPEN_DCMS_DB_URL") is not None
_lock = Lock()

if USE_DB:
    from . import db


def list_keys(tenant=None):
    if USE_DB:
        return db.list_api_keys(tenant)
    KEY_FILE = os.getenv("OPEN_DCMS_KEY_FILE", ".data/api_keys.json")
    try:
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    if tenant:
        return data.get(tenant, [])
    return data


def create_key(tenant: str):
    if USE_DB:
        db.init_db()
        return db.create_api_key(tenant)
    KEY_FILE = os.getenv("OPEN_DCMS_KEY_FILE", ".data/api_keys.json")
    with _lock:
        try:
            with open(KEY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        k = str(uuid.uuid4())
        data.setdefault(tenant, []).append(k)
        os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
        with open(KEY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return k


def validate_key(api_key: str, tenant: str):
    if not api_key:
        return False
    if USE_DB:
        return db.validate_api_key(api_key, tenant)
    KEY_FILE = os.getenv("OPEN_DCMS_KEY_FILE", ".data/api_keys.json")
    try:
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    vals = data.get(tenant, [])
    return api_key in vals
