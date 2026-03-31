#!/usr/bin/env python3
import time
import json
import os
import sys
# ensure project root is on sys.path so `backend` package imports work
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)
from backend import router_adapters as rad

adapter = rad.ExaBGPAdapter('exabgp', config={'endpoint': 'http://127.0.0.1:9000/exabgp'})
prefix = '198.51.100.0/25'

print('Sending announce for', prefix)
ok = adapter.send_blackhole(prefix)
print('Adapter send_blackhole ->', ok)

print('Appending action to .data/blackholes.jsonl (file log)')
os.makedirs('.data', exist_ok=True)
lf = os.path.join('.data', 'blackholes.jsonl')
entry = {'time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'prefix': prefix, 'action': 'add', 'adapter': 'exabgp', 'result': ok, 'detail': 'poc_send', 'operator': 'tester'}
with open(lf, 'a', encoding='utf-8') as f:
    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
print('Wrote to', lf)

# wait a bit for ExaBGP server to write
time.sleep(0.5)
logpath = os.path.join('backend', 'exabgp_poc.log')
if os.path.exists(logpath):
    print('\n--- ExaBGP PoC log (tail) ---')
    with open(logpath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for ln in lines[-10:]:
        print(ln.strip())
else:
    print('ExaBGP PoC log not found at', logpath)

# Now withdraw
print('\nSending withdraw for', prefix)
ok2 = adapter.remove_blackhole(prefix)
print('Adapter remove_blackhole ->', ok2)
lf = os.path.join('.data', 'blackholes.jsonl')
entry2 = {'time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'prefix': prefix, 'action': 'remove', 'adapter': 'exabgp', 'result': ok2, 'detail': 'poc_withdraw', 'operator': 'tester'}
with open(lf, 'a', encoding='utf-8') as f:
    f.write(json.dumps(entry2, ensure_ascii=False) + '\n')
print('Appended withdraw entry to', lf)

# show latest DB blackhole entries for this prefix
print('\nTail of .data/blackholes.jsonl:')
try:
    if os.path.exists(lf):
        with open(lf, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for ln in lines[-10:]:
            print(ln.strip())
    else:
        print('No file', lf)
except Exception as e:
    print('Failed to read file log:', e)
