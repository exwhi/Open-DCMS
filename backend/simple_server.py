import http.server
import socketserver
import json
import os
from urllib.parse import urlparse

PORT = 8000
API_KEY = os.getenv("OPEN_DCMS_API_KEY", "dev-secret")
DATA_DIR = os.getenv("OPEN_DCMS_DATA_DIR", ".data")
os.makedirs(DATA_DIR, exist_ok=True)


class Handler(http.server.BaseHTTPRequestHandler):
    def _set_headers(self, code=200):
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def do_GET(self):
        if self.path == '/health':
            self._set_headers()
            self.wfile.write(json.dumps({'status':'ok'}).encode())
            return
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != '/api/v1/ingest':
            self.send_error(404)
            return
        key = self.headers.get('X-API-Key')
        if key != API_KEY:
            self._set_headers(401)
            self.wfile.write(json.dumps({'detail':'invalid api key'}).encode())
            return
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length)
        try:
            obj = json.loads(raw)
        except Exception:
            self.send_error(400)
            return
        tenant = obj.get('tenant_id','default')
        fname = os.path.join(DATA_DIR, f"{tenant}.jsonl")
        record = {
            'received_at': __import__('datetime').datetime.utcnow().isoformat()+'Z',
            'source': obj.get('source'),
            'timestamp': obj.get('timestamp'),
            'payload': obj.get('payload')
        }
        with open(fname,'a',encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False)+'\n')
        self._set_headers(200)
        self.wfile.write(json.dumps({'result':'stored','tenant':tenant}).encode())


if __name__ == '__main__':
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"Serving simple ingest on port {PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        httpd.server_close()
