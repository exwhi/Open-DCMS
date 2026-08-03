import io
import time
import struct
from agent.parsers.netflow_ipfix import parse_datagram


def _build_v5_packet(src='1.2.3.4', dst='5.6.7.8', src_port=1234, dst_port=80):
    # header: version(2) count(2) sys_uptime(4) unix_secs(4) unix_nsecs(4) flow_sequence(4) engine_type(1) engine_id(1) sampling_interval(2)
    version = 5
    count = 1
    sys_uptime = 0
    unix_secs = int(time.time())
    unix_nsecs = 0
    flow_sequence = 0
    engine_type = 0
    engine_id = 0
    sampling_interval = 0
    header = struct.pack('!HHIIIIBBH', version, count, sys_uptime, unix_secs, unix_nsecs, flow_sequence, engine_type, engine_id, sampling_interval)

    # record: 48 bytes. We'll put src at 0, dst at 4, and ports at 32/34
    rec = bytearray(48)
    rec[0:4] = bytes(map(int, src.split('.')))
    rec[4:8] = bytes(map(int, dst.split('.')))
    rec[32:34] = struct.pack('!H', src_port)
    rec[34:36] = struct.pack('!H', dst_port)

    return header + bytes(rec)


def _build_ipfix_packet():
    import ipfix.ie as ie
    import ipfix.message as msg
    import ipfix.template as tmpl
    import ipfix.types as types

    ie.use_iana_default()

    specs = [
        'sourceIPv4Address(0)/4',
        'destinationIPv4Address(0)/4',
        'sourceTransportPort(0)/2',
        'destinationTransportPort(0)/2',
    ]
    tpl = tmpl.for_specs(256, *specs)
    mb = msg.MessageBuffer()
    mb.begin_export(odid=0)
    mb.add_template(tpl)
    mb.export_new_set(256)
    mb.export_namedict({
        'sourceIPv4Address': types.ip_address('1.2.3.4'),
        'destinationIPv4Address': types.ip_address('5.6.7.8'),
        'sourceTransportPort': 1234,
        'destinationTransportPort': 80,
    })
    buf = io.BytesIO()
    mb.write_message(buf)
    return buf.getvalue()


def test_parse_v5_basic():
    pkt = _build_v5_packet()
    recs = parse_datagram(pkt)
    assert isinstance(recs, list)
    assert len(recs) == 1
    r = recs[0]
    assert r['src'] == '1.2.3.4'
    assert r['dst'] == '5.6.7.8'
    assert r['src_port'] == 1234
    assert r['dst_port'] == 80
    assert r['prefixes'][0].endswith('.0/24')


def test_fallback_for_v9_ipfix():
    # build a fake v9 header (version 9) with some payload
    data = struct.pack('!H', 9) + b'hello world'
    recs = parse_datagram(data)
    assert len(recs) == 1
    assert recs[0]['version'] == 9


def test_parse_ipfix_v10_with_ipfix_lib():
    pkt = _build_ipfix_packet()
    recs = parse_datagram(pkt)
    assert isinstance(recs, list)
    assert len(recs) == 1
    r = recs[0]
    assert r['src'] == '1.2.3.4'
    assert r['dst'] == '5.6.7.8'
    assert r['src_port'] == 1234
    assert r['dst_port'] == 80
    assert r['prefixes'] == ['1.2.3.4/32']