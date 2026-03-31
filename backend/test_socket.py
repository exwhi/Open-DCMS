#!/usr/bin/env python3
import socket
s = socket.socket()
s.settimeout(2)
try:
    s.connect(('127.0.0.1', 9000))
    print('connected')
except Exception as e:
    print('error', repr(e))
finally:
    s.close()
