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
from typing import Callable, List, Optional
import socket
import importlib
import struct

_listener_threads: List[threading.Thread] = []


def _find_parser_for_mode(mode: str):
    """Try to find a parser module and parser callable for given mode.

    Returns (module, parser_callable) or (None, None).
    The parser_callable should accept raw bytes and return a list of payload dicts.
    """
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

        # common possible parser names
        for attr in ('parse', 'decode', 'decode_datagram', 'parse_packet'):
            parser = getattr(mod, attr, None)
            if callable(parser):
                return mod, parser

        # some libraries expose a Decoder class or named API
        for cname in ('SFlowDecoder', 'NetflowDecoder', 'SFlow', 'NetFlow', 'SFlowParser', 'NetflowParser'):
            cls = getattr(mod, cname, None)
            if cls:
                # try to instantiate if possible and use decode/parse
                try:
                    inst = cls()
                except Exception:
                    inst = cls
                if hasattr(inst, 'decode') and callable(getattr(inst, 'decode')):
                    return mod, getattr(inst, 'decode')
                if hasattr(inst, 'parse') and callable(getattr(inst, 'parse')):
                    return mod, getattr(inst, 'parse')

        # special-case adapters for known libs
        if name == 'python_sflow':
            # python_sflow exposes an SFlowDatagram.decode API
            parser = getattr(mod, 'SFlowDatagram', None)
            if parser and hasattr(parser, 'decode'):
                return mod, getattr(parser, 'decode')
        if name == 'pyflowtools':
            # pyflowtools provides a parser module with decode functions
            parser = getattr(mod, 'NetflowParser', None) or getattr(mod, 'parse_datagram', None)
            if parser:
                return mod, parser

    return None, None


def start_listener(mode: str, host: str, port: int, callback: Callable[[dict], None]):
    """Start a UDP listener and attempt to parse incoming flow packets.

    If a parser library is available, parsed events will be delivered to `callback`.
    Otherwise a simple fallback (no-op) listener runs.
    Returns a thread object.
    """
    mod, parser = _find_parser_for_mode(mode)
    if mod and parser:
        print(f'collectors: using parser module {mod.__name__} for mode {mode}')
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
                    # parser may return single record or list
                    if parsed is None:
                        continue
                    if isinstance(parsed, dict):
                        items = [parsed]
                    else:
                        items = list(parsed)
                    for p in items:
                        # normalize basic fields
                        ev = {
                            'prefixes': p.get('prefixes') if isinstance(p, dict) and 'prefixes' in p else p.get('prefix') if isinstance(p, dict) else None,
                            'asn': p.get('asn') if isinstance(p, dict) else None,
                            'sample_time': p.get('sample_time') if isinstance(p, dict) and 'sample_time' in p else datetime.utcnow().isoformat() + 'Z',
                            'raw': None,
                        }
                        try:
                            callback(ev)
                        except Exception:
                            pass
                    continue
                except Exception as e:
                    print('parser error:', e)

            # fallback: attempt minimal heuristic extraction for NetFlow v5 (best-effort)
            try:
                # NetFlow v5 header version (first 2 bytes)
                if len(data) >= 2:
                    ver = struct.unpack('!H', data[:2])[0]
                    if ver == 5 and len(data) >= 24:
                        # header: count at offset 2
                        count = struct.unpack('!H', data[2:4])[0]
                        # records follow; each 48 bytes
                        recs = []
                        offset = 24
                        for i in range(count):
                            if offset + 48 <= len(data):
                                # src addr at offset 0, dst addr at 4
                                src = socket.inet_ntoa(data[offset:offset+4])
                                dst = socket.inet_ntoa(data[offset+4:offset+8])
                                # create simple event using src as prefix/24
                                try:
                                    prefix = src + '/24'
                                except Exception:
                                    prefix = None
                                recs.append({'prefixes': [prefix] if prefix else None, 'asn': None, 'sample_time': datetime.utcnow().isoformat() + 'Z'})
                            offset += 48
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
