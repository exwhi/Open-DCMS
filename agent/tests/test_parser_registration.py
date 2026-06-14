import socket
import time
from agent import collectors


def test_register_parser_and_listener():
    port = 0
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()

    events = []

    def cb(ev):
        events.append(ev)

    # register a simple parser that returns a fixed record
    def my_parser(data: bytes):
        return [{'prefixes': ['10.0.0.0/24'], 'asn': 65001, 'sample_time': '2020-01-01T00:00:00Z'}]

    collectors.register_parser('netflow', my_parser)
    t = collectors.start_listener('netflow', '127.0.0.1', port, cb)
    time.sleep(0.1)
    s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s2.sendto(b'xxx', ('127.0.0.1', port))
    s2.close()

    timeout = 2.0
    start = time.time()
    while time.time() - start < timeout and not events:
        time.sleep(0.05)

    assert events, 'no events from registered parser'
    assert events[0]['prefixes'][0] == '10.0.0.0/24'
