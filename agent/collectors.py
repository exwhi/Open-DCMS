"""Collectors with optional sFlow/NetFlow parsing.

This module attempts to use available parser libraries (python-sflow, pyflowtools, etc.).
If parsing libraries are missing, it will fall back to a lightweight UDP listener that
can be replaced with real parsing logic.

start_listener(mode, host, port, callback) -> starts a background UDP listener and
invokes `callback(event_dict)` for each parsed event.
"""
from datetime import datetime
import threading
import time
from typing import Callable, List, Optional, Iterable
from agent.parsers.adapter_utils import normalize_record
import socket
import importlib
import struct

_listener_threads: List[threading.Thread] = []


def _find_parser_for_mode(mode: str):
    """Try to find a parser callable for given mode.

    Returns a callable `parser(data: bytes) -> Iterable[dict]` or None.
    """
    # prefer local adapters
    try:
        from agent.parsers import (
            python_sflow_adapter,
            pyflowtools_adapter,
            flowtools_adapter,
            sflow_adapter,
        )
    except Exception:
        python_sflow_adapter = pyflowtools_adapter = flowtools_adapter = sflow_adapter = None

    if mode == 'sflow' and python_sflow_adapter:
        p = python_sflow_adapter()
        if p:
            return p
    if mode == 'sflow' and sflow_adapter:
        p = sflow_adapter()
        if p:
            return p

    if mode == 'netflow' and pyflowtools_adapter:
        p = pyflowtools_adapter()
        if p:
            return p
    if mode == 'netflow' and flowtools_adapter:
        p = flowtools_adapter()
        if p:
            return p

    # fallback discovery
    candidates = []
    if mode == 'sflow':
        candidates = ['sflow', 'python_sflow', 'pysflow']
    elif mode == 'netflow':
        candidates = ['pyflowtools', 'flowtools', 'netflow', 'python_netflow']

    for name in candidates:
        try:
            mod = importlib.import_module(name)
        except Exception:
            continue

        for attr in ('parse', 'decode', 'decode_datagram', 'parse_packet'):
            parser = getattr(mod, attr, None)
            if callable(parser):
                return parser

        for cname in ('SFlowDecoder', 'NetflowDecoder', 'SFlow', 'NetFlow', 'SFlowParser', 'NetflowParser'):
            cls = getattr(mod, cname, None)
            if cls:
                try:
                    inst = cls()
                except Exception:
                    inst = cls
                if hasattr(inst, 'decode') and callable(getattr(inst, 'decode')):
                    return getattr(inst, 'decode')
                if hasattr(inst, 'parse') and callable(getattr(inst, 'parse')):
                    return getattr(inst, 'parse')

        if name == 'python_sflow':
            parser = getattr(mod, 'SFlowDatagram', None)
            if parser and hasattr(parser, 'decode'):
                return getattr(parser, 'decode')
        if name == 'pyflowtools':
            parser = getattr(mod, 'NetflowParser', None) or getattr(mod, 'parse_datagram', None)
            if parser:
                return parser

    return None


def start_listener(mode: str, host: str, port: int, callback: Callable[[dict], None]):
    """Start a UDP listener and attempt to parse incoming flow packets.

    If a parser library is available, parsed events will be delivered to `callback`.
    Otherwise a simple fallback (no-op) listener runs.
    Returns a thread object.
    """
    # check for a registered parser first
    reg = get_registered_parser(mode)
    if reg:
        parser = reg
    else:
        parser = _find_parser_for_mode(mode)
    if parser:
        try:
            name = getattr(parser, '__module__', None) or getattr(parser, '__name__', None)
        except Exception:
            name = None
        print(f'collectors: using parser {name} for mode {mode}')
    else:
        print(f'collectors: no parser library found for {mode}; listener will run but not parse payloads')

    def _udp_worker():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.settimeout(2.0)
        while True:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                time.sleep(0.1)
                continue
            except Exception as e:
                print('listener socket error:', e)
                break

            # if we have a parser callable, try to decode
            if parser:
                try:
                    parsed = parser(data)
                    if not parsed:
                        continue
                    if isinstance(parsed, dict):
                        items = [parsed]
                    else:
                        items = list(parsed)
                    for p in items:
                        if not isinstance(p, dict):
                            continue
                        ev = normalize_record(p)
                        try:
                            callback(ev)
                        except Exception:
                            pass
                    continue
                except Exception as e:
                    print('parser error:', e)

            # fallback: attempt minimal heuristic extraction for NetFlow v5 (best-effort)
            try:
                recs = _netflow_v5_fallback(data)
                if recs:
                    for p in recs:
                        try:
                            callback(p)
                        except Exception:
                            pass
                    continue
            except Exception:
                pass

            # if we reach here and no parser, provide a simulated event minimal
            try:
                ev = {'prefixes': None, 'asn': None, 'sample_time': datetime.utcnow().isoformat() + 'Z', 'raw': data.hex()[:256]}
                callback(ev)
            except Exception:
                pass

    t = threading.Thread(target=_udp_worker, daemon=True)
    t.start()
    _listener_threads.append(t)
    return t


def register_parser(mode: str, parser_callable: Callable[[bytes], Iterable[dict]]):
    """Allow runtime registration of a parser callable for a mode (e.g., 'sflow' or 'netflow').

    The callable should accept raw bytes and return an iterable of dicts.
    """
    # simple registry attached to the module
    global _registered_parsers
    try:
        _registered_parsers
    except NameError:
        _registered_parsers = {}
    _registered_parsers[mode] = parser_callable


def get_registered_parser(mode: str) -> Optional[Callable[[bytes], Iterable[dict]]]:
    try:
        return _registered_parsers.get(mode)
    except Exception:
        return None


def collect_netflow_once() -> List[dict]:
    """Placeholder for NetFlow polling collector; real implementation should query a collector or parse stored packets."""
    return [{
        'prefixes': ['198.51.100.0/24'],
        'asn': 65000,
        'sample_time': datetime.utcnow().isoformat() + 'Z'
    }]


def collect_sflow_once() -> List[dict]:
    """Placeholder for sFlow polling collector."""
    return [{
        'prefixes': ['192.0.2.0/24'],
        'asn': 64497,
        'sample_time': datetime.utcnow().isoformat() + 'Z'
    }]


def _netflow_v5_fallback(data: bytes) -> Optional[List[dict]]:
    """Best-effort NetFlow v5 parser that returns list of event dicts or None.

    This is intentionally lightweight: it only extracts the source IP from
    each flow record and returns a /24 prefix based on the source.
    """
    if len(data) < 24:
        return None
    try:
        ver = struct.unpack('!H', data[:2])[0]
    except Exception:
        return None
    if ver != 5 or len(data) < 24:
        return None
    try:
        count = struct.unpack('!H', data[2:4])[0]
        recs: List[dict] = []
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
