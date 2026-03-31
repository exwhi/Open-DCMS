#!/usr/bin/env python3
"""Simple ExaBGP PoC simulator: accepts POST /exabgp with JSON {action, prefix, community}
and writes received events to `exabgp_poc.log` for inspection.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

LOGFILE = 'backend/exabgp_poc.log'

class Handler(BaseHTTPRequestHandler):
    def _set_json(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('content-length', 0))
        body = self.rfile.read(length) if length else b''
        try:
            obj = json.loads(body.decode() or '{}')
        except Exception:
            obj = {'raw': body.decode(errors='ignore')}
        # record to log
        with open(LOGFILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'path': self.path, 'body': obj}) + '\n')
        self._set_json()
        self.wfile.write(json.dumps({'status':'ok'}).encode())

    def log_message(self, format, *args):
        # quiet stdout logs
        return

if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', 9000), Handler)
    print('ExaBGP PoC server listening on http://127.0.0.1:9000')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
        print('ExaBGP PoC server stopped')
