import argparse
import time
import requests
import socket
import json
import os
import uuid
import logging
from pathlib import Path

from agent.queue_manager import PersistentQueue

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Legacy JSONL queue (deprecated, kept for backward compatibility)
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


def try_send(url, headers, payload, ca_cert=None, client_cert=None, client_key=None, max_attempts=5):
    """Send payload with optional mTLS.
    
    Args:
        url: Target URL
        headers: HTTP headers
        payload: Payload dict
        ca_cert: Path to CA certificate for verification (None = default)
        client_cert: Path to client certificate for mTLS
        client_key: Path to client key for mTLS
        max_attempts: Max retry attempts
    """
    for attempt in range(1, max_attempts + 1):
        try:
            kwargs = {
                'json': payload,
                'headers': headers,
                'timeout': 10,
                'verify': ca_cert if ca_cert else True,  # Use custom CA or default
            }
            
            # Add client certificate if provided
            if client_cert and client_key:
                kwargs['cert'] = (client_cert, client_key)
            
            r = requests.post(url, **kwargs)
            if r.status_code == 200:
                logger.info(f"sent ok id={payload.get('id')}")
                return True
            else:
                logger.warning(f"send failed status={r.status_code} id={payload.get('id')}")
        except requests.exceptions.SSLError as e:
            logger.error(f"SSL/mTLS error attempt={attempt} id={payload.get('id')}: {e}")
        except Exception as e:
            logger.error(f"send exception attempt={attempt} id={payload.get('id')} error={e}")
        
        backoff = min(2 ** attempt, 30)
        time.sleep(backoff)
    return False


def flush_queue(queue_manager: PersistentQueue, server, api_key, ca_cert=None, client_cert=None, client_key=None):
    """Flush pending queue items.
    
    Args:
        queue_manager: PersistentQueue instance
        server: Server URL
        api_key: API key
        ca_cert: Path to CA certificate
        client_cert: Path to client certificate
        client_key: Path to client key
    """
    url = server.rstrip("/") + "/api/v1/ingest"
    headers = {"X-API-Key": api_key}
    
    payloads = queue_manager.dequeue(max_items=100)
    if not payloads:
        return
    
    logger.info(f"flushing {len(payloads)} queued items")
    for payload in payloads:
        db_id = payload.pop('_db_id', None)
        payload_id = payload.get('id')
        
        ok = try_send(url, headers, payload, ca_cert=ca_cert, client_cert=client_cert, client_key=client_key)
        if ok:
            queue_manager.mark_sent(payload_id)
        elif db_id:
            queue_manager.mark_failed(db_id, f"HTTP error or timeout")
    
    # Cleanup old sent records
    queue_manager.cleanup_old(days=7)


def run(server, tenant, api_key, interval=10, queue_db=None, ca_cert=None, client_cert=None, client_key=None):
    """Run agent with persistent queue and optional mTLS.
    
    Args:
        server: Server URL
        tenant: Tenant ID
        api_key: API key
        interval: Collection interval (seconds)
        queue_db: Path to queue database (defaults to ~/.cache/open-dcms-agent/queue.db)
        ca_cert: Path to CA certificate for verification
        client_cert: Path to client certificate for mTLS
        client_key: Path to client key for mTLS
    """
    url = server.rstrip("/") + "/api/v1/ingest"
    headers = {"X-API-Key": api_key}
    
    # Initialize queue manager
    queue_manager = PersistentQueue(db_path=queue_db)

    # Flush any pending items first
    flush_queue(queue_manager, server, api_key, ca_cert=ca_cert, client_cert=client_cert, client_key=client_key)
    
    # Load plugins dynamically
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
            
            ok = try_send(url, headers, payload, ca_cert=ca_cert, client_cert=client_cert, client_key=client_key)
            if not ok:
                logger.info("appending to local queue")
                queue_manager.enqueue(payload)
            
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("stopping agent, flushing queue")
        flush_queue(queue_manager, server, api_key, ca_cert=ca_cert, client_cert=client_cert, client_key=client_key)
        # Print queue stats before exit
        stats = queue_manager.get_stats()
        logger.info(f"Final queue stats: {stats}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Open-DCMS Agent with persistent queue and mTLS support")
    p.add_argument("--server", required=True, help="Server URL (e.g., https://dcms.example.com)")
    p.add_argument("--tenant", required=True, help="Tenant ID")
    p.add_argument("--api-key", default="dev-secret", help="API key")
    p.add_argument("--interval", type=int, default=10, help="Collection interval (seconds)")
    p.add_argument("--queue-db", default=None, help="Path to queue database (defaults to ~/.cache/open-dcms-agent/queue.db)")
    p.add_argument("--ca-cert", default=None, help="Path to CA certificate for HTTPS verification")
    p.add_argument("--client-cert", default=None, help="Path to client certificate for mTLS")
    p.add_argument("--client-key", default=None, help="Path to client key for mTLS")
    args = p.parse_args()
    run(
        args.server, 
        args.tenant, 
        args.api_key, 
        args.interval,
        queue_db=args.queue_db,
        ca_cert=args.ca_cert,
        client_cert=args.client_cert,
        client_key=args.client_key,
    )
