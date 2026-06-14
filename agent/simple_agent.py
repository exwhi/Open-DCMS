"""Enhanced simple agent

Features:
- Local JSONL cache for unsent events (断点续传)
- Batch send + retries with exponential backoff
- Optional mTLS client cert and CA verification

Usage example:
  python agent/simple_agent.py --tenant demo --api-url http://localhost:8000/api/v1/ingest --api-key dev-secret
  python agent/simple_agent.py --tenant demo --api-url https://ingest.example.com/api/v1/ingest --api-key prod-key --cert client.crt --key client.key --ca ca.crt
"""

import argparse
import json
import time
import os
import tempfile
from datetime import datetime
from typing import List

try:
    import requests
except Exception:
    requests = None


def load_cache(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    items = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                continue
    return items


def append_to_cache(path: str, obj: dict):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def write_cache_atomic(path: str, items: List[dict]):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d or '.', prefix='.cache-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + '\n')
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def flush_cache(path: str, api_url: str, headers: dict, cert: tuple, verify: str or bool, batch_size: int = 10, retries: int = 3, backoff: float = 1.0) -> bool:
    """Attempt to send cached events in FIFO order. Returns True if all sent or False if some remain."""
    if requests is None:
        print('requests not installed; cannot flush cache')
        return False
    items = load_cache(path)
    if not items:
        return True

    remaining = items[:]
    sent_any = False
    while remaining:
        batch = remaining[:batch_size]
        payload = batch
        ok = False
        attempt = 0
        while attempt <= retries:
            try:
                r = requests.post(api_url, json=payload[0] if len(payload) == 1 else {'batch': payload}, headers=headers, timeout=10, cert=cert, verify=verify)
                if 200 <= r.status_code < 300:
                    ok = True
                    break
                else:
                    # treat 4xx as permanent failure for this batch
                    if 400 <= r.status_code < 500:
                        print('permanent failure for batch, status', r.status_code, r.text)
                        ok = True  # drop bad payload
                        break
            except Exception as e:
                print('flush attempt error:', e)
            attempt += 1
            time.sleep(backoff * (2 ** (attempt - 1)))

        if ok:
            # remove sent batch
            remaining = remaining[len(batch):]
            sent_any = True
        else:
            # failure — stop and leave remaining in cache
            break

    if remaining:
        write_cache_atomic(path, remaining)
        return False
    else:
        # remove cache file
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
        return True


def make_event(tenant: str, source: str, payload: dict) -> dict:
    return {
        'tenant_id': tenant,
        'source': source,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'payload': payload,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--tenant', required=True)
    p.add_argument('--source', default='simple-agent')
    p.add_argument('--api-url', default='http://localhost:8000/api/v1/ingest')
    p.add_argument('--api-key', default='dev-secret')
    p.add_argument('--cert', help='path to client cert (PEM) for mTLS')
    p.add_argument('--key', help='path to client key (PEM) for mTLS')
    p.add_argument('--ca', help='path to CA bundle to verify server cert')
    p.add_argument('--cache-file', default='.agent_cache/events.jsonl')
    p.add_argument('--batch-size', type=int, default=10)
    p.add_argument('--retries', type=int, default=3)
    p.add_argument('--backoff', type=float, default=1.0)
    p.add_argument('--interval', type=int, default=30, help='seconds between collection cycles')
    p.add_argument('--collector', choices=['fake','netflow','sflow'], default='fake', help='which collector to run')
    p.add_argument('--listen-host', default='0.0.0.0', help='collector listen host for flow protocols')
    p.add_argument('--listen-port', type=int, default=6343, help='collector listen port for sFlow/NetFlow (default 6343)')
    args = p.parse_args()

    cert = None
    if args.cert and args.key:
        cert = (args.cert, args.key)

    verify = True
    if args.ca:
        verify = args.ca
    # if no CA and api-url is https, default requests behavior (True) will verify using system CAs

    headers = {'X-Api-Key': args.api_key, 'Content-Type': 'application/json'}

    # run loop: collect -> append to cache -> flush cache (background)
    stop = False

    import signal

    def handle_term(signum, frame):
        nonlocal stop
        print('received signal, stopping...')
        stop = True

    signal.signal(signal.SIGINT, handle_term)
    try:
        signal.signal(signal.SIGTERM, handle_term)
    except Exception:
        pass

    # if collector is netflow/sflow, we may run a background listener (skeleton)
    collector_mode = args.collector
    from agent import collectors

    # start a background flush thread that periodically tries to send cache
    import threading

    def periodic_flush():
        while not stop:
            try:
                flush_cache(args.cache_file, args.api_url, headers=headers, cert=cert, verify=verify, batch_size=args.batch_size, retries=args.retries, backoff=args.backoff)
            except Exception as e:
                print('periodic flush error:', e)
            time.sleep(max(5, args.interval // 2))

    t_flush = threading.Thread(target=periodic_flush, daemon=True)
    t_flush.start()

    print('agent starting: collector=%s interval=%s' % (collector_mode, args.interval))

    # If collector needs a listener, start it (non-blocking skeleton)
    listener = None
    if collector_mode in ('netflow', 'sflow'):
        try:
            listener = collectors.start_listener(mode=collector_mode, host=args.listen_host, port=args.listen_port, callback=lambda ev: append_to_cache(args.cache_file, ev))
            print('started listener for', collector_mode, 'on', args.listen_host, args.listen_port)
        except Exception as e:
            print('failed to start listener:', e)

    # main sampling loop for periodic pulls (or to create synthetic events)
    while not stop:
        try:
            events = []
            if collector_mode == 'fake':
                payload = {'prefixes': ['198.51.100.0/24'], 'asn': 65000, 'sample_time': datetime.utcnow().isoformat() + 'Z'}
                events = [make_event(args.tenant, args.source, payload)]
            else:
                # collectors.collect_* should return list of payload dicts
                try:
                    if collector_mode == 'netflow':
                        collected = collectors.collect_netflow_once()
                    else:
                        collected = collectors.collect_sflow_once()
                    events = [make_event(args.tenant, args.source, p) for p in collected]
                except Exception as e:
                    print('collector error:', e)

            for ev in events:
                append_to_cache(args.cache_file, ev)

            # give background flush time, then sleep until next cycle
            time.sleep(args.interval)
        except Exception as e:
            print('main loop error:', e)
            time.sleep(max(1, args.interval))

    print('agent stopping, waiting for flush thread...')
    try:
        t_flush.join(timeout=5)
    except Exception:
        pass


if __name__ == '__main__':
    main()
