"""Example Juniper adapter skeleton (NETCONF/CLI).
"""
import os


class RouterAdapter:
    def __init__(self):
        self.host = os.getenv('JUNIPER_API_HOST')

    def send_blackhole(self, prefix: str, action: str = 'add', community: str = None) -> bool:
        print('[juniper_adapter] simulate', {'prefix': prefix, 'action': action, 'community': community})
        return True
