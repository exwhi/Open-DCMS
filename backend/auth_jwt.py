"""轻量级 JWT 实现（HMAC-SHA256），用于将 `backend/auth.py` 的 PoC token 升级为可在 FastAPI 中使用的 JWT。

不依赖外部库，供开发/测试使用；生产请使用成熟库（PyJWT / python-jose）并妥善管理密钥。
"""
from __future__ import annotations
import json
import base64
import hmac
import hashlib
import time
from typing import Dict, Any


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    rem = len(s) % 4
    if rem:
        s += "=" * (4 - rem)
    return base64.urlsafe_b64decode(s.encode("ascii"))


def _sign(msg: bytes, secret: bytes) -> bytes:
    return hmac.new(secret, msg, hashlib.sha256).digest()


def create_token(payload: Dict[str, Any], secret: str, expires_in: int = 3600) -> str:
    now = int(time.time())
    body = dict(payload)
    body.setdefault("iat", now)
    body.setdefault("exp", now + expires_in)

    header = {"alg": "HS256", "typ": "JWT"}
    header_b = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b = _b64url_encode(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b}.{payload_b}".encode("ascii")
    sig = _b64url_encode(_sign(signing_input, secret.encode("utf-8")))
    return f"{header_b}.{payload_b}.{sig}"


class InvalidToken(Exception):
    pass


def verify_token(token: str, secret: str) -> Dict[str, Any]:
    try:
        header_b, payload_b, sig_b = token.split(".")
    except ValueError:
        raise InvalidToken("token format")

    signing_input = f"{header_b}.{payload_b}".encode("ascii")
    expected_sig = _b64url_encode(_sign(signing_input, secret.encode("utf-8")))
    if not hmac.compare_digest(expected_sig, sig_b):
        raise InvalidToken("invalid signature")

    payload_json = _b64url_decode(payload_b)
    try:
        payload = json.loads(payload_json)
    except Exception:
        raise InvalidToken("invalid payload")

    exp = payload.get("exp")
    if exp is None or int(time.time()) > int(exp):
        raise InvalidToken("token expired")

    return payload


# Optional FastAPI helper (if FastAPI is present in environment)
try:
    from fastapi import Depends, HTTPException, status
    from fastapi.security import OAuth2PasswordBearer

    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

    def get_current_user(secret: str):
        def _dep(token: str = Depends(oauth2_scheme)):
            try:
                payload = verify_token(token, secret)
                return payload
            except InvalidToken:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        return _dep

except Exception:
    oauth2_scheme = None
