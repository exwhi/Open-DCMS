from agent.parsers.adapter_utils import normalize_record


def test_normalize_basic_fields():
    rec = {
        'prefix': '203.0.113.0/24',
        'origin_as': 64500,
        'timestamp': '2021-01-01T00:00:00Z',
        'ipv4_src': '203.0.113.5',
        'ipv4_dst': '198.51.100.6',
        'l4_src_port': 12345,
        'l4_dst_port': 80,
    }
    out = normalize_record(rec)
    assert out['prefixes'] == ['203.0.113.0/24']
    assert out['asn'] == 64500
    assert out['sample_time'] == '2021-01-01T00:00:00Z'
    assert out['src'] == '203.0.113.5'
    assert out['dst'] == '198.51.100.6'
    assert out['src_port'] == 12345
    assert out['dst_port'] == 80


def test_normalize_non_dict():
    out = normalize_record('not-a-dict')
    assert out['prefixes'] is None
    assert out['asn'] is None
