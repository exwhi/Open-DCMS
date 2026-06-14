"""NetFlow / IPFIX minimal parsers.

This module implements a small NetFlow v5 parser and a safe fallback
for NetFlow v9 / IPFIX (returns raw payload with metadata). The
implementation focuses on being robust and returning a normalized
list of dict records suitable for the agent pipeline.
"""
from typing import List, Optional
import struct
import socket
import datetime


def parse_datagram(data: bytes) -> List[dict]:
    """Parse an incoming UDP datagram and return list of records.

    Detects NetFlow v5 and parses records. For v9/IPFIX (or unknown)
    it returns a single raw record with metadata so callers can
    gracefully handle lack of template parsing.
    """
    if not data:
        return []

    # try v5
    v5 = _parse_netflow_v5(data)
    if v5:
        return v5

    # detect versions 9 (NetFlow v9) and 10 (IPFIX) and return raw fallback
    try:
        ver = struct.unpack('!H', data[:2])[0]
    except Exception:
        ver = None

    ts = datetime.datetime.utcnow().isoformat() + 'Z'
    if ver in (9, 10):
        return [{'raw': data.hex(), 'length': len(data), 'version': ver, 'note': 'v9/ipfix-unparsed', 'sample_time': ts}]

    # unknown/other: return safe raw record
    return [{'raw': data.hex(), 'length': len(data), 'sample_time': ts}]


def _parse_netflow_v5(data: bytes) -> Optional[List[dict]]:
    """Minimal NetFlow v5 parser.

    Returns None if data is not v5 or cannot be parsed.
    The parser extracts a few useful fields (src/dst/src_port/dst_port,
    a /24 prefix heuristic and sample_time).
    """
    # NetFlow v5 header is 24 bytes
    if len(data) < 24:
        return None
    try:
        ver, count = struct.unpack('!HH', data[:4])
    except Exception:
        return None
    if ver != 5:
        return None

    # safe limit: do not attempt to parse ridiculously large counts
    if count <= 0 or count > 512:
        return None

    # header contains unix_secs at bytes 8..12 in many exporters; we'll
    # use UTC now as a fallback if extraction fails
    try:
        unix_secs = struct.unpack('!I', data[8:12])[0]
        sample_time = datetime.datetime.utcfromtimestamp(unix_secs).isoformat() + 'Z'
    except Exception:
        sample_time = datetime.datetime.utcnow().isoformat() + 'Z'

    recs: List[dict] = []
    offset = 24
    record_len = 48
    for i in range(count):
        if offset + record_len > len(data):
            break
        chunk = data[offset:offset+record_len]
        try:
            src = socket.inet_ntoa(chunk[0:4])
            dst = socket.inet_ntoa(chunk[4:8])
        except Exception:
            src = None
            dst = None

        # ports are at offsets 32..33 and 34..35 within the 48-byte record
        try:
            src_port = struct.unpack('!H', chunk[32:34])[0]
        except Exception:
            src_port = None
        try:
            dst_port = struct.unpack('!H', chunk[34:36])[0]
        except Exception:
            dst_port = None

        prefix = None
        if src:
            parts = src.split('.')
            if len(parts) == 4:
                prefix = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"

        recs.append({'prefixes': [prefix] if prefix else None,
                     'asn': None,
                     'sample_time': sample_time,
                     'src': src,
                     'dst': dst,
                     'src_port': src_port,
                     'dst_port': dst_port,
                     'raw': chunk.hex()})

        offset += record_len

    return recs if recs else None
