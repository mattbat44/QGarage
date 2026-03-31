import contextlib
import json
import os
from pathlib import Path
from typing import Optional

from qgis.core import QgsApplication
from qgis.gui import QgisInterface
from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .core.app_registry import AppEntry, AppRegistry
from .core.logger import log_error
from .core.settings import get_uv_executable
from .core.uv_bridge import UvBridge
from .processing.processing_provider import QGarageProcessingProvider
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
        self.processing_provider: Optional[QGarageProcessingProvider] = None
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

        # Register Processing provider
        if self.registry is not None:
            self._register_processing_provider(icon_path=icon_path)

    def unload(self):
        """Called by QGIS when the plugin is unloaded."""
        # Unregister Processing provider
        self._remove_processing_provider()

        if self.registry is not None:
            try:
                self.registry.unload_all()
            except RuntimeError:
                # QGIS teardown can invalidate wrapped objects before plugin unload.
                pass
            self.registry = None

        if self.dock is not None and not sip.isdeleted(self.dock):
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        else:
            self.dock = None

        if self.action is not None and not sip.isdeleted(self.action):
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("&QGarage", self.action)
            self.action.deleteLater()
            self.action = None
        else:
            self.action = None

        self.uv_bridge = None

    def _provider_is_alive(self) -> bool:
        provider = self.processing_provider
        if provider is None:
            return False
        try:
            return not sip.isdeleted(provider)
        except Exception:
            return False

    def _remove_processing_provider(self) -> None:
        if not self._provider_is_alive():
            self.processing_provider = None
            return

        try:
            QgsApplication.processingRegistry().removeProvider(self.processing_provider)
        except RuntimeError:
            # Provider can already be deleted by QGIS teardown order.
            pass
        finally:
            self.processing_provider = None

    def _register_processing_provider(self, icon_path: str | None = None) -> None:
        if self.registry is None:
            self.processing_provider = None
            return

        # Always clear the existing local reference first.
        self._remove_processing_provider()

        registry = QgsApplication.processingRegistry()

        # If QGIS already has a stale provider with this id, remove it.
        existing = None
        if hasattr(registry, "providerById"):
            try:
                existing = registry.providerById("qgarage")
            except Exception:
                existing = None
        if existing is not None:
            with contextlib.suppress(Exception):
                registry.removeProvider(existing)

        provider = QGarageProcessingProvider(self.registry, icon_path=icon_path)
        added = False
        try:
            added = bool(registry.addProvider(provider))
        except RuntimeError as e:
            log_error(f"Failed to add Processing provider: {e}")

        if added:
            self.processing_provider = provider
            return

        # Fallback for registry implementations without providerById support.
        if hasattr(registry, "providers"):
            try:
                for existing_provider in list(registry.providers()):
                    try:
                        if existing_provider.id() == "qgarage":
                            registry.removeProvider(existing_provider)
                    except Exception:
                        continue
                if registry.addProvider(provider):
                    self.processing_provider = provider
                    return
            except Exception:
                pass

        self.processing_provider = None
        log_error("Could not register QGarage Processing provider")

    def _toggle_dock(self, checked: bool):
        if self.dock is not None:
            self.dock.setVisible(checked)

    def _on_install_requested(self):
        dialog = InstallDialog(APPS_DIR, self.iface.mainWindow())
        dialog.app_installed.connect(self._on_app_installed)
        dialog.exec()

    def _on_app_installed(self, item_id: str, is_toolbox: bool):
        """Called when an app or toolbox is successfully installed via the dialog."""
        if self.registry is None or self.dock is None:
            return

        if is_toolbox:
            # Handle toolbox installation
            # If the toolbox already exists, remove it first
            if item_id in self.registry.toolbox_entries:
                # Remove all apps in the toolbox first
                toolbox_entry = self.registry.toolbox_entries[item_id]
                for app_id in list(toolbox_entry.app_entries.keys()):
                    self.registry.remove_app(app_id)

            # Re-discover to pick up the new/updated toolbox
            self.registry.discover()
            self.dock.refresh_cards()
        else:
            # Handle single app installation
            # If the app already exists, unload it and remove its card first
            if item_id in self.registry.entries:
                self.registry.remove_app(item_id)
                self.dock.remove_card(item_id)

            # Read app_meta and register
            meta_file = APPS_DIR / item_id / "app_meta.json"
            if not meta_file.exists():
                return
            with open(meta_file, encoding="utf-8") as f:
                app_meta = json.load(f)
            entry = AppEntry(APPS_DIR / item_id, app_meta)
            self.registry.register_entry(entry)
            self.registry.load_app(item_id)
            self.dock.add_card(entry)

        # Ensure provider is present and refreshed after install/reinstall.
        self._refresh_processing_provider()

    def _on_new_app_requested(self):
        dialog = ScaffoldDialog(APPS_DIR, self.iface.mainWindow())
        dialog.app_created.connect(lambda app_id: self._on_app_installed(app_id, False))
        dialog.exec()

    def _refresh_processing_provider(self) -> None:
        if self.registry is None:
            self.processing_provider = None
            return

        if not self._provider_is_alive():
            self._register_processing_provider()
            return

        try:
            self.processing_provider.refreshAlgorithms()
        except RuntimeError:
            # Wrapped provider can become invalid after plugin reload cycles.
            self.processing_provider = None
            self._register_processing_provider()
