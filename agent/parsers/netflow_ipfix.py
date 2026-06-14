"""Placeholder IPFIX/NetFlow v9 parser stub.

This module provides a minimal API `parse_datagram(data: bytes) -> List[dict]`
that can be expanded to parse templates (v9) or IPFIX messages.
"""
from typing import List


def parse_datagram(data: bytes) -> List[dict]:
    # very small placeholder: return a raw hex and length
    # Try NetFlow v5 parsing first
    v5 = _parse_netflow_v5(data)
    if v5:
        return v5

    # Placeholder for v9/IPFIX: return raw record for now
    return [{'raw': data.hex(), 'length': len(data), 'sample_time': datetime.utcnow().isoformat() + 'Z'}]


def _parse_netflow_v5(data: bytes) -> Optional[List[dict]]:
    if len(data) < 24:
        return None
    try:
        ver = struct.unpack('!H', data[:2])[0]
    except Exception:
        return None
    if ver != 5:
        return None
    try:
        count = struct.unpack('!H', data[2:4])[0]
        recs = []
        offset = 24
        for i in range(count):
            if offset + 48 <= len(data):
                try:
                    src = socket.inet_ntoa(data[offset:offset+4])
                    dst = socket.inet_ntoa(data[offset+4:offset+8])
                    src_port = struct.unpack('!H', data[offset+32:offset+34])[0]
                    dst_port = struct.unpack('!H', data[offset+34:offset+36])[0]
                    prefix = src.rsplit('.', 1)[0] + '.0/24'
                except Exception:
                    prefix = None
                recs.append({'prefixes': [prefix] if prefix else None, 'asn': None, 'sample_time': datetime.utcnow().isoformat() + 'Z', 'src': src if 'src' in locals() else None, 'dst': dst if 'dst' in locals() else None, 'src_port': src_port if 'src_port' in locals() else None, 'dst_port': dst_port if 'dst_port' in locals() else None})
            offset += 48
        return recs if recs else None
    except Exception:
        return None
