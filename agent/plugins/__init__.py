"""Plugin loader for router/vendor adapters.

Adapters should implement a `RouterAdapter` class with method:
  - send_blackhole(prefix: str, action: str, community: str=None) -> bool

Plugins placed under `agent/plugins` can be discovered by name.
"""
from importlib import import_module
from typing import Dict, Any
import pkgutil
import os


def list_available_plugins() -> list:
    pkg_dir = os.path.dirname(__file__)
    names = []
    for _, name, ispkg in pkgutil.iter_modules([pkg_dir]):
        if not ispkg and name != '__init__':
            names.append(name)
    return names


def load_plugin(name: str):
    modname = f'agent.plugins.{name}'
    mod = import_module(modname)
    return mod


def get_adapter(name: str):
    mod = load_plugin(name)
    if hasattr(mod, 'RouterAdapter'):
        return mod.RouterAdapter()
    raise ImportError(f'plugin {name} has no RouterAdapter')
import pkgutil
import importlib
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent


def load_plugins():
    plugins = []
    for finder, name, ispkg in pkgutil.iter_modules([str(PLUGIN_DIR)]):
        try:
            mod = importlib.import_module(f"agent.plugins.{name}")
            if hasattr(mod, "collect") and callable(mod.collect):
                plugins.append(mod)
        except Exception:
            continue
    return plugins
