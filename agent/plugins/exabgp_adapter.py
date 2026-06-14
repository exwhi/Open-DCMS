"""Example adapter that speaks to an ExaBGP HTTP API or simulates commands.

Configuration via environment variables:
- EXABGP_HTTP_URL: e.g. http://127.0.0.1:9999
"""
import os
import requests


class RouterAdapter:
    def __init__(self):
        self.url = os.getenv('EXABGP_HTTP_URL')

    def send_blackhole(self, prefix: str, action: str = 'add', community: str = None) -> bool:
        payload = {'prefix': prefix, 'action': action, 'community': community}
        # If ExaBGP HTTP API provided, POST to it; otherwise just print
        if self.url:
            try:
                r = requests.post(self.url, json=payload, timeout=5)
                if 200 <= r.status_code < 300:
                    return True
                # if remote returns a JSON with 'ok' field, treat as success
                try:
                    jr = r.json()
                    if jr.get('ok'):
                        return True
                except Exception:
                    pass
                return False
            except Exception:
                return False
        else:
            print('[exabgp_adapter] simulate', payload)
            return True
