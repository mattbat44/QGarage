import json
import os
from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.gui import QgisInterface

from .core.app_registry import AppEntry, AppRegistry
from .core.logger import log_error
from .core.settings import get_uv_executable
from .core.uv_bridge import UvBridge
from .ui.dashboard_dock import DashboardDock
from .ui.install_dialog import InstallDialog
from .ui.scaffold_dialog import ScaffoldDialog

PLUGIN_DIR = os.path.dirname(__file__)
APPS_DIR = Path(PLUGIN_DIR) / "apps"


class QGaragePlugin:
    """Main QGIS plugin class for QGarage."""

    def __init__(self, iface: QgisInterface):
        self.iface = iface
        self.dock: Optional[DashboardDock] = None
        self.action: Optional[QAction] = None
        self.registry: Optional[AppRegistry] = None
        self.uv_bridge: Optional[UvBridge] = None

    def initGui(self):
        """Called by QGIS when the plugin is loaded."""
        icon_path = os.path.join(PLUGIN_DIR, "icon.svg")
        self.action = QAction(
            QIcon(icon_path),
            "QGarage Dashboard",
            self.iface.mainWindow(),
        )
        self.action.setCheckable(True)
        self.action.triggered.connect(self._toggle_dock)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&QGarage", self.action)

        # Initialize core
        try:
            self.uv_bridge = UvBridge(get_uv_executable())
        except RuntimeError as e:
            log_error(f"uv not available: {e}")
            self.uv_bridge = None

        if self.uv_bridge is not None:
            self.registry = AppRegistry(APPS_DIR, self.uv_bridge)
            self.registry.discover()
            self.registry.load_all()

        # Create dashboard and wire up
        self.dock = DashboardDock(self.iface)
        if self.registry is not None:
            self.dock.set_registry(self.registry)
        self.dock.install_requested.connect(self._on_install_requested)
        self.dock.new_app_requested.connect(self._on_new_app_requested)
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.setVisible(False)
        self.dock.visibilityChanged.connect(self.action.setChecked)

    def unload(self):
        """Called by QGIS when the plugin is unloaded."""
        if self.registry is not None:
            self.registry.unload_all()
            self.registry = None

        if self.dock is not None:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None

        if self.action is not None:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("&QGarage", self.action)
            self.action.deleteLater()
            self.action = None

        self.uv_bridge = None

    def _toggle_dock(self, checked: bool):
        if self.dock is not None:
            self.dock.setVisible(checked)

    def _on_install_requested(self):
        dialog = InstallDialog(APPS_DIR, self.iface.mainWindow())
        dialog.app_installed.connect(self._on_app_installed)
        dialog.exec()

    def _on_app_installed(self, app_id: str):
        """Called when an app is successfully installed via the dialog."""
        if self.registry is None or self.dock is None:
            return

        # If the app already exists, unload it and remove its card first
        if app_id in self.registry.entries:
            self.registry.remove_app(app_id)
            self.dock.remove_card(app_id)

        # Read app_meta and register
        meta_file = APPS_DIR / app_id / "app_meta.json"
        if not meta_file.exists():
            return
        with open(meta_file, encoding="utf-8") as f:
            app_meta = json.load(f)
        entry = AppEntry(APPS_DIR / app_id, app_meta)
        self.registry.register_entry(entry)
        self.registry.load_app(app_id)
        self.dock.add_card(entry)

    def _on_new_app_requested(self):
        dialog = ScaffoldDialog(APPS_DIR, self.iface.mainWindow())
        dialog.app_created.connect(self._on_app_installed)
        dialog.exec()
