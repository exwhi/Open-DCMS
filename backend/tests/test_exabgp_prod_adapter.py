import time
import os
from backend.router_adapters import ExaBGPAdapter
from backend.exabgp_sandbox import start_server


def test_exabgp_prod_tcp_flow(tmp_path):
    # start sandbox with api_key
    api_key = 'test-key-123'
    srv, port, thread = start_server('127.0.0.1', 0, api_key=api_key)
    logfile = os.path.join('backend', 'exabgp_sandbox.log')
    try:
        # ensure log file cleared
        try:
            os.remove(logfile)
        except Exception:
            pass

        adapter = ExaBGPAdapter('exabgp', config={'tcp_host': '127.0.0.1', 'tcp_port': port, 'retries': 1, 'timeout': 1, 'api_key': api_key})
        assert adapter.send_blackhole('198.51.100.0/25') is True
        assert adapter.remove_blackhole('198.51.100.0/25') is True

        # allow writes to flush
        time.sleep(0.1)
        assert os.path.exists(logfile)
        with open(logfile, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        assert len(lines) >= 2
    finally:
        try:
            srv.shutdown()
        except Exception:
            pass
