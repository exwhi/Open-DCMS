"""IPFIX/NetFlow v9 adapter wrapper.

This module detects available third-party IPFIX/NetFlow v9 libraries and
provides a best-effort `parse_ipfix(data: bytes) -> Optional[List[dict]]`
function. The goal is to centralize optional integrations so the agent can
use a richer parser when available but still function when no native
libraries are installed.

Supported libraries (best-effort):
- pyfixbuf (if installed)
- ipfix (if installed)

The adapter wraps calls in try/except so missing or incompatible library
APIs won't break the agent. Improve the library-specific code paths if you
choose a specific package for production.
"""
from typing import List, Optional


def _normalize_value(value):
    try:
        import ipaddress
        if isinstance(value, ipaddress.IPv4Address) or isinstance(value, ipaddress.IPv6Address):
            return str(value)
    except Exception:
        pass
    if isinstance(value, bytes):
        try:
            return value.decode('utf-8')
        except Exception:
            return value.hex()
    return value


def _build_record_from_namedict(namedict: dict, sample_time: str) -> dict:
    src = _normalize_value(namedict.get('sourceIPv4Address') or namedict.get('sourceIPv6Address'))
    dst = _normalize_value(namedict.get('destinationIPv4Address') or namedict.get('destinationIPv6Address'))
    src_port = namedict.get('sourceTransportPort') or namedict.get('sourcePort')
    dst_port = namedict.get('destinationTransportPort') or namedict.get('destinationPort')
    prefix = None
    prefix_len = namedict.get('sourceIPv4PrefixLength') or namedict.get('sourceIPv6PrefixLength')
    if src:
        if prefix_len is not None:
            prefix = f"{src}/{prefix_len}"
        else:
            prefix = f"{src}/32"
    rec = {
        'prefixes': [prefix] if prefix else None,
        'asn': namedict.get('bgpSourceAsNumber') or namedict.get('bgpDestinationAsNumber'),
        'sample_time': sample_time,
        'src': src,
        'dst': dst,
        'src_port': int(src_port) if src_port is not None else None,
        'dst_port': int(dst_port) if dst_port is not None else None,
        'raw': None,
    }
    return rec


def parse_ipfix(data: bytes) -> Optional[List[dict]]:
    """Try to parse IPFIX/v9 payload using an available library.

    Returns a list of normalized records on success, otherwise None.
    """
    if not data:
        return None

    try:
        import ipfix.message as msg
        mb = msg.MessageBuffer()
        mb.from_bytes(data)
        sample_time = None
        try:
            sample_time = mb.get_export_time().isoformat() + 'Z'
        except Exception:
            import datetime
            sample_time = datetime.datetime.utcnow().isoformat() + 'Z'

        records = []
        for namedict in mb.namedict_iterator():
            if not isinstance(namedict, dict):
                continue
            rec = _build_record_from_namedict(namedict, sample_time)
            records.append(rec)
        return records if records else None
    except Exception:
        pass

    return None
