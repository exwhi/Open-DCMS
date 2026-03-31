#!/usr/bin/env python3
import urllib.request, json
try:
    data = json.dumps({'test':'ping'}).encode()
    req = urllib.request.Request('http://127.0.0.1:9000/exabgp', data=data, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=3) as r:
        print('status', r.status)
        print('body', r.read().decode())
except Exception as e:
    print('error', repr(e))
