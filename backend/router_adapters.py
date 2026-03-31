"""Router vendor adapter abstractions and lightweight stubs.

Provide a simple plugin interface for sending/removing blackhole routes
and for vendor-specific implementations. These are minimal stubs intended
for PoC and will be extended to perform real API/ExaBGP interactions.
"""
from typing import Optional, Dict
import json
import logging


class RouterAdapterError(Exception):
    pass


class BaseRouterAdapter:
    """Abstract base adapter.

    Subclasses should implement `send_blackhole` and `remove_blackhole`.
    """

    def __init__(self, name: str, config: Optional[Dict] = None):
        self.name = name
        self.config = config or {}

    def send_blackhole(self, prefix: str, community: Optional[str] = None) -> bool:
        """Install a blackhole for `prefix` (e.g. via BGP community or router API).

        Return True on success, raise RouterAdapterError on failure.
        """
        raise NotImplementedError()

    def remove_blackhole(self, prefix: str) -> bool:
        """Remove a previously-installed blackhole for `prefix`."""
        raise NotImplementedError()

    def check_connectivity(self) -> bool:
        """Optional: check API/SSH connectivity to device or controller."""
        return True


class CiscoIOSAdapter(BaseRouterAdapter):
    """Lightweight Cisco IOS adapter (stub).

    Real implementation could use Netmiko/Paramiko/RESTCONF or ExaBGP.
    """

    def send_blackhole(self, prefix: str, community: Optional[str] = None) -> bool:
        # TODO: implement Netmiko/RESTCONF call
        # For PoC, just log to config and return True
        return True

    def remove_blackhole(self, prefix: str) -> bool:
        # TODO: implement removal
        return True


class JuniperAdapter(BaseRouterAdapter):
    def send_blackhole(self, prefix: str, community: Optional[str] = None) -> bool:
        # TODO: implement Junos RPC / Netconf actions
        return True

    def remove_blackhole(self, prefix: str) -> bool:
        return True


class ExaBGPAdapter(BaseRouterAdapter):
    """Adapter that speaks to an ExaBGP control-plane instance.

    Expected config keys: endpoint (http/socket), api_key, etc.
    """

    def _http_post(self, endpoint: str, payload: dict, timeout: int = 5, retries: int = 2, api_key: Optional[str] = None) -> bool:
        import urllib.request, urllib.error
        data = json.dumps(payload).encode()
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        req = urllib.request.Request(endpoint, data=data, headers=headers)
        last_exc = None
        for attempt in range(retries + 1):
            try:
                self._logger.debug('HTTP post attempt %d -> %s payload=%s', attempt, endpoint, payload)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    ok = getattr(resp, 'status', 200) == 200
                    self._logger.info('HTTP post result: %s %s', endpoint, ok)
                    return ok
            except Exception as e:
                last_exc = e
                self._logger.warning('HTTP post failed attempt %d: %s', attempt, e)
        self._logger.error('HTTP post all retries failed: %s', last_exc)
        raise RouterAdapterError(f'HTTP post failed: {last_exc}')

    def _tcp_send(self, host: str, port: int, payload: dict, timeout: int = 5, retries: int = 2, api_key: Optional[str] = None) -> bool:
        import socket
        if api_key:
            payload = dict(payload)
            payload['api_key'] = api_key
        data = (json.dumps(payload) + '\n').encode()
        last_exc = None
        for attempt in range(retries + 1):
            try:
                self._logger.debug('TCP send attempt %d -> %s:%s payload=%s', attempt, host, port, payload)
                with socket.create_connection((host, int(port)), timeout=timeout) as s:
                    s.sendall(data)
                    # try to receive a short response (non-blocking)
                    try:
                        s.settimeout(1.0)
                        resp = s.recv(4096)
                        self._logger.info('TCP recv: %s', resp[:200])
                        return True
                    except Exception:
                        return True
            except Exception as e:
                last_exc = e
                self._logger.warning('TCP send failed attempt %d: %s', attempt, e)
        self._logger.error('TCP send all retries failed: %s', last_exc)
        raise RouterAdapterError(f'TCP send failed: {last_exc}')

    def send_blackhole(self, prefix: str, community: Optional[str] = None) -> bool:
        cfg = self.config if isinstance(self.config, dict) else {}
        # per-instance logger
        if not hasattr(self, '_logger'):
            self._logger = logging.getLogger(f'router_adapters.ExaBGPAdapter.{self.name}')
        self._logger.debug('send_blackhole called prefix=%s community=%s cfg=%s', prefix, community, cfg)
        api_key = cfg.get('api_key')
        payload = {'action': 'announce', 'prefix': prefix}
        if community:
            payload['community'] = community
        # prefer tcp socket if configured
        if cfg.get('tcp_host') and cfg.get('tcp_port'):
            try:
                return self._tcp_send(cfg['tcp_host'], cfg['tcp_port'], payload, timeout=cfg.get('timeout', 5), retries=cfg.get('retries', 2), api_key=api_key)
            except RouterAdapterError:
                # fallback to HTTP
                pass
        endpoint = cfg.get('endpoint') or 'http://127.0.0.1:9000/exabgp'
        try:
            return self._http_post(endpoint, payload, timeout=cfg.get('timeout', 5), retries=cfg.get('retries', 2), api_key=api_key)
        except RouterAdapterError:
            return False

    def remove_blackhole(self, prefix: str) -> bool:
        cfg = self.config if isinstance(self.config, dict) else {}
        if not hasattr(self, '_logger'):
            self._logger = logging.getLogger(f'router_adapters.ExaBGPAdapter.{self.name}')
        api_key = cfg.get('api_key')
        payload = {'action': 'withdraw', 'prefix': prefix}
        if cfg.get('tcp_host') and cfg.get('tcp_port'):
            try:
                return self._tcp_send(cfg['tcp_host'], cfg['tcp_port'], payload, timeout=cfg.get('timeout', 5), retries=cfg.get('retries', 2), api_key=api_key)
            except RouterAdapterError:
                pass
        endpoint = cfg.get('endpoint') or 'http://127.0.0.1:9000/exabgp'
        try:
            return self._http_post(endpoint, payload, timeout=cfg.get('timeout', 5), retries=cfg.get('retries', 2), api_key=api_key)
        except RouterAdapterError:
            return False


__all__ = [
    "BaseRouterAdapter",
    "CiscoIOSAdapter",
    "JuniperAdapter",
    "ExaBGPAdapter",
    "RouterAdapterError",
]
