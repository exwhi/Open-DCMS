"""Example Cisco adapter using NETCONF/RESTCONF placeholders.

This is an adapter skeleton. For production integrate with ncclient (NETCONF) or requests for RESTCONF.
"""
import os


class RouterAdapter:
    def __init__(self):
        self.host = os.getenv('CISCO_API_HOST')
        self.user = os.getenv('CISCO_API_USER')
        self.password = os.getenv('CISCO_API_PASS')

    def send_blackhole(self, prefix: str, action: str = 'add', community: str = None) -> bool:
        # TODO: implement NETCONF/RESTCONF interaction
        print('[cisco_adapter] simulate', {'prefix': prefix, 'action': action, 'community': community})
        return True
