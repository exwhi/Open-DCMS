"""Parser adapters for flow protocols.

This package exposes small adapter callables that conform to the project's
internal parser interface:

    def parse_datagram(data: bytes) -> Iterable[dict]

Adapters should return an iterable of event dicts or None on failure.

Adapters attempt to import the underlying third-party library lazily; if the
library is not present the adapter will be None.
"""
from typing import Optional, Callable


def python_sflow_adapter() -> Optional[Callable[[bytes], list]]:
    try:
        import python_sflow
    except Exception:
        return None

    # python_sflow exposes SFlowDatagram.decode that returns objects; wrap
    def _parse(data: bytes):
        try:
            datagram = python_sflow.SFlowDatagram.decode(data)
            # datagram may contain samples; produce minimal normalized dicts
            results = []
            for s in getattr(datagram, 'samples', []) or []:
                # best-effort extraction
                r = {}
                if hasattr(s, 'samples'):
                    # nested structure; skip deep probing here
                    pass
                # expose raw sample time / placeholders
                r['sample_time'] = getattr(datagram, 'timestamp', None)
                results.append(r)
            return results
        except Exception:
            return None

    return _parse


def pyflowtools_adapter() -> Optional[Callable[[bytes], list]]:
    try:
        import pyflowtools
    except Exception:
        return None

    def _parse(data: bytes):
        try:
            # pyflowtools may provide a NetflowParser or parse_datagram
            parser = getattr(pyflowtools, 'NetflowParser', None) or getattr(pyflowtools, 'parse_datagram', None)
            if callable(parser):
                return parser(data)
            # if parser is a class
            if parser:
                inst = parser()
                if hasattr(inst, 'parse'):
                    return inst.parse(data)
            return None
        except Exception:
            return None

    return _parse


def flowtools_adapter() -> Optional[Callable[[bytes], list]]:
    try:
        import flowtools
    except Exception:
        return None

    def _parse(data: bytes):
        try:
            # flowtools may expose a decode or parser method
            parser = getattr(flowtools, 'parse_datagram', None) or getattr(flowtools, 'NetflowParser', None)
            if callable(parser):
                return parser(data)
            if parser:
                inst = parser()
                if hasattr(inst, 'parse'):
                    return inst.parse(data)
            return None
        except Exception:
            return None

    return _parse


def sflow_adapter() -> Optional[Callable[[bytes], list]]:
    try:
        import sflow
    except Exception:
        return None

    def _parse(data: bytes):
        try:
            # best-effort: try decode functions
            fn = getattr(sflow, 'decode', None) or getattr(sflow, 'parse_datagram', None)
            if callable(fn):
                return fn(data)
            return None
        except Exception:
            return None

    return _parse


def netflow_ipfix_adapter() -> Optional[Callable[[bytes], list]]:
    try:
        from agent.parsers import netflow_ipfix
    except Exception:
        return None

    def _parse(data: bytes):
        try:
            return netflow_ipfix.parse_datagram(data)
        except Exception:
            return None

    return _parse
