#!/usr/bin/env python3
"""Dev sandbox TCP server for ExaBGP adapter.

Listens for JSON-per-line messages on a TCP port. If `api_key` is configured,
it will validate incoming messages contain matching `api_key` field. Received
messages are appended to `backend/exabgp_sandbox.log`.

Provides `start_server(host='127.0.0.1', port=0, api_key=None)` which returns
the server instance and the chosen port. Call `server.shutdown()` to stop.
"""
import json
import socketserver
import threading
import os
from typing import Optional, Tuple


LOGFILE = os.path.join('backend', 'exabgp_sandbox.log')


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        data = self.rfile.readline()
        if not data:
            return
        try:
            obj = json.loads(data.decode(errors='ignore'))
        except Exception:
            obj = {'raw': data.decode(errors='ignore')}

        # validate api_key if server has attribute
        server_api_key = getattr(self.server, 'api_key', None)
        ok = True
        if server_api_key:
            if obj.get('api_key') != server_api_key:
                ok = False

        with open(LOGFILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'ok': ok, 'body': obj}) + '\n')

        # respond minimally
        try:
            if ok:
                self.wfile.write(b'OK\n')
            else:
                self.wfile.write(b'ERR\n')
        except Exception:
            pass


class ThreadedTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def start_server(host: str = '127.0.0.1', port: int = 0, api_key: Optional[str] = None) -> Tuple[ThreadedTCPServer, int, threading.Thread]:
    srv = ThreadedTCPServer((host, port), Handler)
    srv.api_key = api_key
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, srv.server_address[1], t


if __name__ == '__main__':
    srv, port, t = start_server()
    print('ExaBGP sandbox listening on', port)
    try:
        t.join()
    except KeyboardInterrupt:
        srv.shutdown()
        print('stopped')
