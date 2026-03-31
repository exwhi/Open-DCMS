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
