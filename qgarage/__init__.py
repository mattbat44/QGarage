from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys
from pathlib import Path

# Alias the active plugin package as `qgarage` so bundled apps that import
# `qgarage.core.*` continue to work even when this plugin is installed under a
# side-by-side test folder such as `qgarage_test`.
_current_package = __name__
_root_package_name = _current_package.split(".")[0]

if _root_package_name != "qgarage":
    # Running as qgarage_test or similar - set up module aliasing
    sys.modules.setdefault("qgarage", sys.modules[_current_package])

    class _QGarageAliasingFinder:
        """Meta path finder that redirects qgarage.* imports to the actual package."""

        def find_spec(self, fullname, path, target=None):
            if fullname == "qgarage" or fullname.startswith("qgarage."):
                # Check if already loaded under the aliased name
                if fullname in sys.modules:
                    return None  # Already handled

                # Translate to actual package name
                actual_name = _root_package_name + fullname[len("qgarage") :]

                # Try to import the actual module
                try:
                    actual_module = importlib.import_module(actual_name)
                    # Alias it
                    sys.modules[fullname] = actual_module
                    return None  # Signal that we've handled it
                except ImportError:
                    return None  # Not found
            return None  # Not a qgarage import

    # Install the finder if not already installed
    if not any(isinstance(f, _QGarageAliasingFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _QGarageAliasingFinder())
else:
    # Running as qgarage - no aliasing needed
    sys.modules.setdefault("qgarage", sys.modules[_current_package])


def classFactory(iface):
    """QGIS plugin entry point."""
    from .plugin import QGaragePlugin

    plugin = QGaragePlugin(iface)
    plugin.PLUGIN_DIR = str(Path(__file__).resolve().parent)
    plugin.APPS_DIR = Path(plugin.PLUGIN_DIR) / "apps"
    return plugin
