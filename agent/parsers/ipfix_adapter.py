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


def parse_ipfix(data: bytes) -> Optional[List[dict]]:
    """Try to parse IPFIX/v9 payload using an available library.

    Returns a list of normalized records on success, otherwise None.
    """
    if not data:
        return None

    # Try pyfixbuf first
    try:
        import pyfixbuf
    except Exception:
        pyfixbuf = None

    if pyfixbuf is not None:
        try:
            # Best-effort: many installations expose a collector/decoder API;
            # we attempt to use common-friendly interfaces and fall back on
            # returning None if the concrete API differs.
            if hasattr(pyfixbuf, 'IPFIXDecoder'):
                dec = pyfixbuf.IPFIXDecoder()
                dec.feed(data)
                out = []
                for rec in dec.records():
                    # attempt to map fields; library-specific keys vary
                    d = {k: getattr(rec, k, None) for k in ('src', 'dst', 'src_port', 'dst_port')}
                    out.append(d)
                return out or None
            # fallback to generic decode function if present
            if hasattr(pyfixbuf, 'decode'):
                decoded = pyfixbuf.decode(data)
                return decoded if isinstance(decoded, list) and decoded else None
        except Exception:
            pass

    # Try ipfix package
    try:
        import ipfix
    except Exception:
        ipfix = None

    if ipfix is not None:
        try:
            # best-effort parsing calls; actual API depends on package
            if hasattr(ipfix, 'IpfixParser'):
                parser = ipfix.IpfixParser()
                msgs = parser.parse(data)
                out = []
                for m in msgs:
                    # normalize common fields if present
                    rec = {}
                    for k in ('sourceIPv4Address', 'destinationIPv4Address', 'sourceTransportPort', 'destinationTransportPort'):
                        if k in m:
                            rec[k] = m[k]
                    out.append(rec)
                return out or None
            if hasattr(ipfix, 'parse'):
                p = ipfix.parse(data)
                return p if isinstance(p, list) and p else None
        except Exception:
            pass

    return None
