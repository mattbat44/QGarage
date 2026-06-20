import sys
from pathlib import Path

# Alias the active plugin package as `qgarage` so bundled apps that import
# `qgarage.core.*` continue to work even when this plugin is installed under a
# side-by-side test folder such as `qgarage_test`.
sys.modules.setdefault("qgarage", sys.modules[__name__])


def classFactory(iface):
    """QGIS plugin entry point."""
    from .plugin import QGaragePlugin

    plugin = QGaragePlugin(iface)
    plugin.PLUGIN_DIR = str(Path(__file__).resolve().parent)
    plugin.APPS_DIR = Path(plugin.PLUGIN_DIR) / "apps"
    return plugin
