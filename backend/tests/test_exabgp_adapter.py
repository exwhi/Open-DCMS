import unittest
import threading
import time
import socket
import importlib


class SimpleHandler:
    # minimal handler for socket based test (echo server)
    def __init__(self, conn, addr, store):
        self.conn = conn
        self.addr = addr
        self.store = store

    def handle(self):
        try:
            data = self.conn.recv(4096)
            if data:
                self.store.append(data.decode(errors='ignore'))
                # send simple HTTP 200 for HTTP-style tests
                if data.startswith(b'POST'):
                    resp = b'HTTP/1.1 200 OK\r\nContent-Length: 13\r\n\r\n{"status":"ok"}'
                    try:
                        self.conn.sendall(resp)
                    except Exception:
                        pass
        finally:
            try:
                self.conn.close()
            except Exception:
                pass


def start_tcp_server(host='127.0.0.1'):
    s = socket.socket()
    s.bind((host, 0))
    s.listen(5)
    port = s.getsockname()[1]
    store = []

    def accept_loop():
        while True:
            try:
                conn, addr = s.accept()
            except Exception:
                break
            h = SimpleHandler(conn, addr, store)
            threading.Thread(target=h.handle, daemon=True).start()

    t = threading.Thread(target=accept_loop, daemon=True)
    t.start()
    return s, port, store


class TestExaBGPAdapter(unittest.TestCase):
    def test_http_post(self):
        # start a simple TCP listener that responds to HTTP POSTs
        sock, port, store = start_tcp_server()
        try:
            from backend.router_adapters import ExaBGPAdapter
            adapter = ExaBGPAdapter('exabgp', config={'endpoint': f'http://127.0.0.1:{port}/exabgp'})
            ok = adapter.send_blackhole('198.51.100.0/25')
            self.assertTrue(ok)
            ok2 = adapter.remove_blackhole('198.51.100.0/25')
            self.assertTrue(ok2)
            # ensure store received something
            time.sleep(0.1)
            self.assertTrue(len(store) >= 1)
        finally:
            try:
                sock.close()
            except Exception:
                pass


if __name__ == '__main__':
    unittest.main()
