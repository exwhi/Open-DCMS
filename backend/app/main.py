from fastapi import FastAPI, Header, HTTPException, Request
import os
import json
from datetime import datetime

app = FastAPI(title="Open-DCMS Ingest API (minimal)")

API_KEY = os.getenv("OPEN_DCMS_API_KEY", "dev-secret")
DATA_DIR = os.getenv("OPEN_DCMS_DATA_DIR", ".data")
os.makedirs(DATA_DIR, exist_ok=True)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/ingest")
async def ingest(request: Request, x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")
    body = await request.json()
    tenant = body.get("tenant_id") or "default"
    fname = os.path.join(DATA_DIR, f"{tenant}.jsonl")
    record = {
        "received_at": datetime.utcnow().isoformat() + "Z",
        "source": body.get("source"),
        "timestamp": body.get("timestamp"),
        "payload": body.get("payload"),
    }
    with open(fname, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"result": "stored", "tenant": tenant}
