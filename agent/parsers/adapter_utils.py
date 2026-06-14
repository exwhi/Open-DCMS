from typing import Dict, Any
from datetime import datetime


def normalize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize various parser outputs to a stable event dict.

    Fields produced: `prefixes`, `asn`, `sample_time`, `src`, `dst`, `src_port`, `dst_port`, `raw`.
    """
    out = {
        'prefixes': None,
        'asn': None,
        'sample_time': None,
        'src': None,
        'dst': None,
        'src_port': None,
        'dst_port': None,
        'raw': None,
    }
    if not isinstance(rec, dict):
        return out

    # prefixes: accept list or single
    if 'prefixes' in rec and rec['prefixes']:
        out['prefixes'] = rec['prefixes']
    elif 'prefix' in rec and rec['prefix']:
        out['prefixes'] = [rec['prefix']]

    # asn
    out['asn'] = rec.get('asn') or rec.get('origin_as')

    # sample_time
    st = rec.get('sample_time') or rec.get('timestamp')
    if st:
        out['sample_time'] = st
    else:
        out['sample_time'] = datetime.utcnow().isoformat() + 'Z'

    out['src'] = rec.get('src') or rec.get('src_ip') or rec.get('ipv4_src')
    out['dst'] = rec.get('dst') or rec.get('dst_ip') or rec.get('ipv4_dst')
    out['src_port'] = rec.get('src_port') or rec.get('l4_src_port')
    out['dst_port'] = rec.get('dst_port') or rec.get('l4_dst_port')
    out['raw'] = rec.get('raw')
    return out
