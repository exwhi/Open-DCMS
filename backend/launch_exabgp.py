#!/usr/bin/env python3
import subprocess, os
p = subprocess.Popen(['python','backend/exabgp_poc_server.py'], cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
print('Launched exabgp_poc_server.py pid=', p.pid)
