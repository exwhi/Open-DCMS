#!/usr/bin/env python3
"""Simple sFlow/NetFlow-like simulator that POSTs flow samples to the local ingest API.

Usage: python backend/flow_simulator.py [count] [interval_seconds]

This script does not require extra packages; it uses urllib.
"""
import sys
import time
import json
import random
import urllib.request

COUNT = int(sys.argv[1]) if len(sys.argv) > 1 else 10
INTERVAL = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
INGEST_URL = 'http://127.0.0.1:8000/api/v1/ingest'

TENANT = 'default'

PREFIXES = [
    '198.51.100.0/24',
    '203.0.113.0/24',
    '198.51.100.0/25',
    '2001:db8::/64',
]

print('Simulating', COUNT, 'flow samples ->', INGEST_URL)
for i in range(COUNT):
    src = '198.51.%d.%d' % (random.randint(0, 255), random.randint(1, 254))
    dst = '203.0.%d.%d' % (random.randint(0, 255), random.randint(1, 254))
    prefix = random.choice(PREFIXES)
    bytes_seen = random.randint(100, 500000)
    payload = {
        'src_ip': src,
        'dst_ip': dst,
        'bytes': bytes_seen,
        'prefix': prefix,
        # include a guessed ASN for some samples
        'asn': 64500 + random.randint(1, 10) if random.random() < 0.6 else None,
        'sample_id': i,
    }
    record = {
        'tenant_id': TENANT,
        'source': 'flow-sim',
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'payload': payload,
    }
    data = json.dumps(record).encode()
    req = urllib.request.Request(INGEST_URL, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            print(i, '->', resp.status)
    except Exception as e:
        print(i, 'error', e)
    time.sleep(INTERVAL)
print('Done')
