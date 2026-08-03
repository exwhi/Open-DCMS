import os
import sys
import pytest


# ensure workspace root is on sys.path so `import agent.plugins` works
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import importlib
plugin_loader = importlib.import_module('agent.plugins')


def test_list_plugins():
    names = plugin_loader.list_available_plugins()
    assert isinstance(names, list)


@pytest.mark.parametrize('name', ['exabgp_adapter', 'cisco_adapter', 'juniper_adapter', 'huawei_adapter'])
def test_adapter_send_blackhole(name):
    adapter = plugin_loader.get_adapter(name)
    # should expose send_blackhole
    assert hasattr(adapter, 'send_blackhole')
    ok = adapter.send_blackhole('198.51.100.0/24', action='add', community='65000:666')
    assert ok in (True, False)
