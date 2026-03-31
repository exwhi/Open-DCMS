#!/usr/bin/env python3
import socket
import json
body = json.dumps({'raw':'ping'})
req = f"POST /exabgp HTTP/1.1\r\nHost: 127.0.0.1:9000\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n{body}"

s = socket.socket()
s.settimeout(3)
try:
    s.connect(('127.0.0.1', 9000))
    s.sendall(req.encode())
    data = s.recv(4096)
    print('recv:', data.decode(errors='replace'))
except Exception as e:
    print('error', e)
finally:
    s.close()
