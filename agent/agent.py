import argparse
import time
import requests
import socket
import json
import os
import uuid
from pathlib import Path


QUEUE_FILE = Path(".agent_queue.jsonl")


def sample_payload(plugins=None):
    data = {}
    if plugins:
        for p in plugins:
            try:
                part = p.collect()
                if isinstance(part, dict):
                    data.update(part)
            except Exception:
                continue
    # fallback defaults
    if not data:
        data = {
            "asn": "AS12345",
            "export_util": {"eth0": {"bps_in": 12345, "bps_out": 54321}},
            "env": {"temp": 27.5, "humidity": 45},
        }
    return data


def append_queue(record: dict):
    with QUEUE_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_queue():
    if not QUEUE_FILE.exists():
        return []
    items = []
    with QUEUE_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                continue
    return items


def rewrite_queue(items):
    if not items:
        try:
            QUEUE_FILE.unlink()
        except Exception:
            pass
        return
    tmp = QUEUE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(QUEUE_FILE)


def try_send(url, headers, payload, max_attempts=5):
    for attempt in range(1, max_attempts + 1):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=10)
            if r.status_code == 200:
                print(f"sent ok id={payload.get('id')}")
                return True
            else:
                print(f"send failed status={r.status_code} id={payload.get('id')}")
        except Exception as e:
            print(f"send exception attempt={attempt} id={payload.get('id')} error={e}")
        backoff = min(2 ** attempt, 30)
        time.sleep(backoff)
    return False


def flush_queue(server, api_key):
    url = server.rstrip("/") + "/api/v1/ingest"
    headers = {"X-API-Key": api_key}
    items = load_queue()
    if not items:
        return
    remaining = []
    print(f"flushing {len(items)} queued items")
    for it in items:
        ok = try_send(url, headers, it)
        if not ok:
            remaining.append(it)
    rewrite_queue(remaining)


def run(server, tenant, api_key, interval=10):
    url = server.rstrip("/") + "/api/v1/ingest"
    headers = {"X-API-Key": api_key}

    # flush any pending items first
    flush_queue(server, api_key)
    # load plugins dynamically
    try:
        from agent.plugins import load_plugins
        plugins = load_plugins()
    except Exception:
        plugins = []

    try:
        while True:
            payload = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant,
                "source": socket.gethostname(),
                "timestamp": time.time(),
                "payload": sample_payload(plugins=plugins),
            }
            ok = try_send(url, headers, payload)
            if not ok:
                print("appending to local queue")
                append_queue(payload)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("stopping agent, flushing queue")
        flush_queue(server, api_key)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--server", required=True)
    p.add_argument("--tenant", required=True)
    p.add_argument("--api-key", default="dev-secret")
    p.add_argument("--interval", type=int, default=10)
    args = p.parse_args()
    run(args.server, args.tenant, args.api_key, args.interval)
