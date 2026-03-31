"""Lightweight wrapper around optional `radix` (py-radix) to build an index
from a list of (prefix, asn, source) tuples and perform LPM searches.

This module is purposely independent of the DB layer so it can be
unit-tested without `sqlalchemy` installed.
"""
from typing import List, Tuple, Optional

try:
    import radix
except Exception:
    try:
        from backend import simple_radix as radix
    except Exception:
        radix = None


def build_index(pairs: List[Tuple[str, int, Optional[str]]]):
    """Build and return a radix.Radix index containing the given (prefix, asn, source) pairs.

    Raises RuntimeError if `radix` is not available.
    """
    if radix is None:
        raise RuntimeError('radix package not available')
    r = radix.Radix()
    for prefix, asn, source in pairs:
        try:
            node = r.add(prefix)
            node.data['asn'] = asn
            if source is not None:
                node.data['source'] = source
        except Exception:
            # ignore malformed prefixes
            continue
    return r


def lpm_search(index, ip_str: str):
    """Perform longest-prefix-match on `ip_str` using the provided radix index.

    Returns dict {'prefix', 'asn', 'source'} or None.
    """
    if radix is None:
        raise RuntimeError('radix package not available')
    node = index.search_best(ip_str)
    if not node:
        return None
    return {'prefix': node.prefix, 'asn': node.data.get('asn'), 'source': node.data.get('source')}
