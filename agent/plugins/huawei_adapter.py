"""Example Huawei adapter skeleton (CLI/REST).
"""
import os


class RouterAdapter:
    def __init__(self):
        self.host = os.getenv('HUAWEI_API_HOST')

    def send_blackhole(self, prefix: str, action: str = 'add', community: str = None) -> bool:
        print('[huawei_adapter] simulate', {'prefix': prefix, 'action': action, 'community': community})
        return True
