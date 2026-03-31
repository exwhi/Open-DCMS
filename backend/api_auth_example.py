"""示例：将 JWT 与 FastAPI 集成的最小路由（示例用途）。

该文件为示例，依赖 FastAPI；运行前请确保已安装 `fastapi` 与 `uvicorn`。
"""
try:
    from fastapi import FastAPI, Depends
    from fastapi.responses import JSONResponse
except Exception:
    # FastAPI 不存在时，保持文件可导入但不可运行
    FastAPI = None

from .auth_jwt import create_token, verify_token, get_current_user


def make_app(secret: str = "dev-secret"):
    if FastAPI is None:
        raise RuntimeError("FastAPI 未安装")
    app = FastAPI()

    @app.post('/token')
    def token_endpoint(username: str, tenant_id: str):
        payload = {"sub": username, "tenant": tenant_id, "roles": ["admin"]}
        t = create_token(payload, secret, expires_in=3600)
        return {"access_token": t, "token_type": "bearer"}

    @app.get('/whoami')
    def whoami(current=Depends(get_current_user(secret))):
        return JSONResponse(current)

    return app
