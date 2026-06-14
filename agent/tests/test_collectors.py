import socket
import struct
import time
from agent import collectors


def test_netflow_v5_fallback():
    # build minimal NetFlow v5 packet: header (24 bytes) + one 48-byte record
    version = 5
    count = 1
    sys_uptime = 0
    unix_secs = 0
    unix_nsecs = 0
    flow_sequence = 0
    engine_type = 0
    engine_id = 0
    sampling_interval = 0

    header = struct.pack('!HHIIIIBBH', version, count, sys_uptime, unix_secs, unix_nsecs, flow_sequence, engine_type, engine_id, sampling_interval)
    # record: 48 bytes, put source IP at start
    src_ip = '198.51.100.5'
    rec = socket.inet_aton(src_ip) + bytes(44)
    pkt = header + rec

    recs = collectors._netflow_v5_fallback(pkt)
    assert recs is not None
    assert isinstance(recs, list)
    assert len(recs) == 1
    assert recs[0]['prefixes'][0] == '198.51.100.0/24'


def find_free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_start_listener_no_parser_udp_raw_event():
    port = find_free_udp_port()
    events = []

    def cb(ev):
        events.append(ev)

    t = collectors.start_listener('bogus-mode', '127.0.0.1', port, cb)
    # give the listener a moment to start
    time.sleep(0.1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    payload = b'hello-world'
    s.sendto(payload, ('127.0.0.1', port))
    s.close()

    # wait for callback
    timeout = 2.0
    start = time.time()
    while time.time() - start < timeout and not events:
        time.sleep(0.05)

    assert events, 'no events received from listener'
    ev = events[0]
    assert 'raw' in ev or 'prefixes' in ev
    if 'raw' in ev:
        assert ev['raw'].startswith(payload.hex()[:6])
