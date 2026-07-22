from __future__ import annotations

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
from qgis.PyQt.QtWidgets import QAction, QMessageBox

from .core.app_update import (
    get_install_source,
    record_update_check,
    should_check_for_updates,
)
from .core.app_registry import AppEntry, AppRegistry
from .core.logger import log_error, log_info
from .core.settings import get_pixi_executable, get_uv_executable
from .core.uv_bridge import UvBridge
from .processing.processing_provider import QGarageProcessingProvider
from .ui.dashboard_dock import DashboardDock
from .ui.install_dialog import InstallDialog
from .ui.scaffold_dialog import ScaffoldDialog
from .workers.app_update_worker import AppUpdateWorker
from .workers.env_setup_worker import EnvSetupWorker
from .workers.install_tool_worker import InstallToolWorker
from .workers.update_check_worker import UpdateCheckWorker

PLUGIN_DIR = os.path.dirname(__file__)
APPS_HOME_DIRNAME = ".garage"


def get_managed_apps_dir() -> Path:
    """Return the stable managed app directory in the user's home folder."""
    return Path.home() / APPS_HOME_DIRNAME


APPS_DIR = get_managed_apps_dir()


class QGaragePlugin:
    """Main QGIS plugin class for QGarage."""

    def __init__(self, iface: QgisInterface):
        self.iface = iface
        self.dock: Optional[DashboardDock] = None
        self.action: Optional[QAction] = None
        self.registry: Optional[AppRegistry] = None
        self.processing_provider: Optional[QGarageProcessingProvider] = None
        self.uv_bridge: Optional[UvBridge] = None
        self.pixi_bridge = None
        self._env_workers: dict[str, EnvSetupWorker] = {}
        self._update_check_workers: dict[str, UpdateCheckWorker] = {}
        self._update_workers: dict[str, AppUpdateWorker] = {}
        # One active tool-install worker at a time (uv or pixi)
        self._install_tool_worker: Optional[InstallToolWorker] = None

    def initGui(self):
        """Called by QGIS when the plugin is loaded."""
        plugin_dir = getattr(self, "PLUGIN_DIR", PLUGIN_DIR)
        apps_dir = getattr(self, "APPS_DIR", APPS_DIR)
        try:
            apps_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log_error(
                f"Managed apps directory initialization failed for '{apps_dir}' "
                f"({type(exc).__name__}): {exc}"
            )
            # Most common failures: permission denied, read-only filesystem, or
            # non-directory path collisions at the target location.
            QMessageBox.critical(
                self.iface.mainWindow(),
                "QGarage setup error",
                f"QGarage could not create or access its managed app directory:\n"
                f"{apps_dir}\n\nError: {exc}\n\n"
                "Check folder permissions and ensure the path is not an existing file.",
            )
            return
        icon_path = os.path.join(plugin_dir, "icon.svg")
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

        try:
            from .core.pixi_bridge import PixiBridge

            self.pixi_bridge = PixiBridge(get_pixi_executable())
        except RuntimeError as e:
            log_error(f"pixi not available: {e}")
            self.pixi_bridge = None

        if self.uv_bridge is not None or self.pixi_bridge is not None:
            self.registry = AppRegistry(apps_dir, self.uv_bridge, self.pixi_bridge)
            self.registry.discover()

        # Create dashboard and wire up
        self.dock = DashboardDock(self.iface)
        if self.registry is not None:
            self.dock.set_registry(self.registry)
            for entry in self.registry.iter_entries():
                self._prepare_app_environment_async(entry)
        self.dock.install_requested.connect(self._on_install_requested)
        self.dock.new_app_requested.connect(self._on_new_app_requested)
        self.dock.refresh_app_requested.connect(self._on_refresh_app_requested)
        self.dock.check_updates_requested.connect(self._on_check_updates_requested)
        self.dock.update_app_requested.connect(self._on_update_app_requested)
        self.dock.global_refresh_requested.connect(self._on_global_refresh)
        self.dock.status_bar.uv_install_requested.connect(
            lambda: self._on_tool_install_requested("uv")
        )
        self.dock.status_bar.pixi_install_requested.connect(
            lambda: self._on_tool_install_requested("pixi")
        )
        self._update_status_bar()
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.setVisible(False)
        self.dock.visibilityChanged.connect(self.action.setChecked)
        self.dock.visibilityChanged.connect(self._on_dock_visibility_changed)

        # Register Processing provider
        if self.registry is not None:
            self._register_processing_provider(icon_path=icon_path)
            self._check_for_app_updates()

    def unload(self):
        """Called by QGIS when the plugin is unloaded."""
        self._stop_env_workers()

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
            with contextlib.suppress(Exception):
                self.dock.set_registry(None)
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
        self.pixi_bridge = None
        self._env_workers.clear()
        for worker in self._update_check_workers.values():
            with contextlib.suppress(Exception):
                worker.quit()
                worker.wait()
        self._update_check_workers.clear()
        for worker in self._update_workers.values():
            with contextlib.suppress(Exception):
                worker.quit()
                worker.wait()
        self._update_workers.clear()
        if self._install_tool_worker is not None:
            with contextlib.suppress(Exception):
                self._install_tool_worker.quit()
                self._install_tool_worker.wait()
            self._install_tool_worker = None
        log_info("Plugin unload completed", "plugin")

    def _stop_env_workers(self) -> None:
        for app_id, worker in list(self._env_workers.items()):
            try:
                if hasattr(worker, "setup_finished"):
                    with contextlib.suppress(Exception):
                        worker.setup_finished.disconnect(self._on_env_setup_finished)
                with contextlib.suppress(Exception):
                    worker.finished.disconnect(worker.deleteLater)
                with contextlib.suppress(Exception):
                    worker.quit()
                worker.wait()
            except RuntimeError:
                continue
            finally:
                self._env_workers.pop(app_id, None)

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
        except Exception as exc:
            log_error(f"Failed to remove Processing provider cleanly: {exc}")
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
                    if existing_provider.id() == "qgarage":
                        registry.removeProvider(existing_provider)
                if registry.addProvider(provider):
                    self.processing_provider = provider
                    return
            except Exception as e:
                return ValueError(f"Incurred error: {e}")

        self.processing_provider = None
        log_error("Could not register QGarage Processing provider")

    def _toggle_dock(self, checked: bool):
        if self.dock is not None:
            self.dock.setVisible(checked)

    def _on_install_requested(self):
        apps_dir = getattr(self, "APPS_DIR", APPS_DIR)
        dialog = InstallDialog(apps_dir, self.iface.mainWindow())
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
            self._refresh_processing_provider()
            toolbox_entry = self.registry.toolbox_entries.get(item_id)
            if toolbox_entry is not None:
                for app_entry in toolbox_entry.app_entries.values():
                    self._prepare_app_environment_async(app_entry)
                    self._maybe_check_for_app_updates(app_entry)
        else:
            # Handle single app installation
            # If the app already exists, unload it and remove its card first
            if item_id in self.registry.entries:
                self._env_workers.pop(item_id, None)
                self.dock.remove_card(item_id)
                self.registry.remove_app(item_id)

            # Read app_meta and register
            apps_dir = getattr(self, "APPS_DIR", APPS_DIR)
            meta_file = apps_dir / item_id / "app_meta.json"
            if not meta_file.exists():
                return
            with open(meta_file, encoding="utf-8") as f:
                app_meta = json.load(f)
            entry = AppEntry(apps_dir / item_id, app_meta)
            self.registry.register_entry(entry)
            self.dock.add_card(entry)
            self._prepare_app_environment_async(entry)
            self._maybe_check_for_app_updates(entry)

    def _prepare_app_environment_async(
        self, entry: AppEntry, *, clean: bool = False
    ) -> None:
        if self.registry is None or self.dock is None:
            return

        entry.health.reset()
        from .core.app_state import AppState

        entry.health.state = AppState.INSTALLING
        self.dock.update_card_state(entry.app_id)

        existing = self._env_workers.pop(entry.app_id, None)
        if existing is not None:
            existing.quit()
            existing.wait()

        try:
            bridge = self.registry.get_bridge_for_app(entry.app_dir)
        except Exception as exc:
            entry.health.record_error(str(exc))
            self.dock.update_card_state(entry.app_id)
            return

        worker = EnvSetupWorker(
            entry.app_id,
            entry.app_dir,
            bridge,
            parent=self.dock,
            clean=clean,
        )
        worker.setup_finished.connect(self._on_env_setup_finished)
        worker.finished.connect(worker.deleteLater)
        self._env_workers[entry.app_id] = worker
        worker.start()

    def _on_env_setup_finished(
        self, app_id: str, success: bool, error_text: str
    ) -> None:
        if self.registry is None or self.dock is None:
            self._env_workers.pop(app_id, None)
            return

        self._env_workers.pop(app_id, None)
        entry = self.registry.entries.get(app_id)
        if entry is None:
            return

        if success:
            self.registry.load_app(app_id)
            self._refresh_processing_provider()
        else:
            entry.health.record_error(error_text)
            log_error(f"Environment setup failed for {app_id}: {error_text}")

        self.dock.update_card_state(app_id)

    def _on_refresh_app_requested(self, app_id: str) -> None:
        """Wipe the cached env for *app_id* then rebuild it from scratch."""
        if self.registry is None or self.dock is None:
            return
        entry = self.registry.entries.get(app_id)
        if entry is None:
            return

        self._close_app_if_open(app_id)

        self.registry.unload_app(app_id)
        # clean=True tells EnvSetupWorker to delete .venv / .pixi before reinstalling
        self._prepare_app_environment_async(entry, clean=True)
        self.dock.update_card_state(app_id)

    def _on_check_updates_requested(self, app_id: str) -> None:
        if self.registry is None:
            return
        entry = self.registry.entries.get(app_id)
        if entry is None:
            return
        self._maybe_check_for_app_updates(entry, force=True)

    def _on_update_app_requested(self, app_id: str) -> None:
        if self.registry is None or self.dock is None:
            return
        if app_id in self._update_workers:
            return

        entry = self.registry.entries.get(app_id)
        if entry is None:
            return

        self._close_app_if_open(app_id)

        self.registry.unload_app(app_id)
        entry.health.reset()
        from .core.app_state import AppState

        entry.health.state = AppState.INSTALLING
        self.dock.update_card_state(app_id)

        worker = AppUpdateWorker(
            app_id,
            entry.app_dir,
            entry.app_meta,
            parent=self.dock,
        )
        worker.update_finished.connect(self._on_app_update_finished)
        worker.finished.connect(worker.deleteLater)
        self._update_workers[app_id] = worker
        worker.start()

    def _on_app_update_finished(
        self,
        app_id: str,
        success: bool,
        requirements_changed: bool,
        pixi_changed: bool,
        error_text: str,
    ) -> None:
        if self.registry is None or self.dock is None:
            self._update_workers.pop(app_id, None)
            return

        self._update_workers.pop(app_id, None)
        entry = self.registry.entries.get(app_id)
        if entry is None:
            return

        if not success:
            entry.health.record_error(error_text)
            self.dock.update_card_state(app_id)
            return

        meta_file = entry.app_dir / "app_meta.json"
        try:
            with open(meta_file, encoding="utf-8") as f:
                entry.app_meta = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            entry.health.record_error(f"Updated app metadata could not be loaded: {exc}")
            self.dock.update_card_state(app_id)
            return
        entry.update_available = False
        entry.available_version = None
        entry.checking_updates = False
        self.dock.refresh_cards()

        if requirements_changed or pixi_changed:
            self._prepare_app_environment_async(entry)
            return

        self.registry.load_app(app_id)
        self._refresh_processing_provider()
        self.dock.update_card_state(app_id)

    def _on_global_refresh(self) -> None:
        """Reload the entire QGarage plugin — equivalent to Plugin Reloader.

        Locates the plugin's own entry in ``qgis.utils.plugins`` so that it
        works regardless of the exact installed folder name.
        """
        try:
            import qgis.utils as _qu

            plugin_name: Optional[str] = None
            for name, obj in _qu.plugins.items():
                if obj is self:
                    plugin_name = name
                    break

            if plugin_name:
                log_info(f"Global refresh: reloading plugin '{plugin_name}'", "plugin")
                _qu.reloadPlugin(plugin_name)
            else:
                # Fallback: re-discover without a full module reload
                log_info(
                    "Global refresh: plugin name not found, doing soft refresh",
                    "plugin",
                )
                self._soft_refresh()
        except Exception as exc:
            log_error(f"Global refresh failed: {exc}")

    def _soft_refresh(self) -> None:
        """Re-discover and reload all apps without a full module reload."""
        if self.registry is None or self.dock is None:
            return
        self._stop_env_workers()
        self.registry.unload_all()
        self.registry.discover()
        self.dock.refresh_cards()
        for entry in self.registry.iter_entries():
            self._prepare_app_environment_async(entry)
        self._check_for_app_updates(force=True)

    def _on_dock_visibility_changed(self, visible: bool) -> None:
        if visible:
            self._check_for_app_updates()

    def _close_app_if_open(self, app_id: str) -> None:
        """Close the currently hosted app when it matches ``app_id``."""
        if self.dock is not None and app_id == self.dock.current_app_id:
            self.dock.close_current_app()

    def _check_for_app_updates(self, *, force: bool = False) -> None:
        if self.registry is None:
            return
        for entry in self.registry.iter_entries():
            self._maybe_check_for_app_updates(entry, force=force)

    def _maybe_check_for_app_updates(
        self, entry: AppEntry, *, force: bool = False
    ) -> None:
        if self.dock is None:
            return
        if get_install_source(entry.app_meta) is None:
            entry.checking_updates = False
            entry.update_available = False
            entry.available_version = None
            self.dock.update_card_state(entry.app_id)
            return
        if entry.app_id in self._update_check_workers:
            return
        if not should_check_for_updates(entry.app_id, force=force):
            return

        entry.checking_updates = True
        self.dock.update_card_state(entry.app_id)

        worker = UpdateCheckWorker(entry.app_id, entry.app_meta, parent=self.dock)
        worker.check_finished.connect(self._on_update_check_finished)
        worker.finished.connect(worker.deleteLater)
        self._update_check_workers[entry.app_id] = worker
        worker.start()

    def _on_update_check_finished(
        self, app_id: str, available: bool, available_version: str
    ) -> None:
        record_update_check(app_id)
        worker = self._update_check_workers.pop(app_id, None)
        if worker is not None:
            with contextlib.suppress(Exception):
                worker.check_finished.disconnect(self._on_update_check_finished)

        if self.registry is None or self.dock is None:
            return

        entry = self.registry.entries.get(app_id)
        if entry is None:
            return

        entry.checking_updates = False
        entry.update_available = available
        entry.available_version = available_version or None
        self.dock.update_card_state(app_id)

    # ------------------------------------------------------------------
    # Tool installation (uv / pixi)
    # ------------------------------------------------------------------

    def _on_tool_install_requested(self, tool: str) -> None:
        """Ask the user for consent, then install the tool in a background thread."""
        if self.dock is None:
            return

        if tool == "uv":
            install_url = "https://docs.astral.sh/uv/"
            install_cmd_display = (
                "Linux/macOS: curl -LsSf https://astral.sh/uv/install.sh | sh\n"
                "Windows    : irm https://astral.sh/uv/install.ps1 | iex"
            )
        else:
            install_url = "https://pixi.sh"
            install_cmd_display = (
                "Linux/macOS: curl -fsSL https://pixi.sh/install.sh | bash\n"
                "Windows    : iwr -useb https://pixi.sh/install.ps1 | iex"
            )

        msg = QMessageBox(self.iface.mainWindow())
        msg.setWindowTitle(f"Install {tool}?")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setText(
            f"<b>{tool}</b> was not found on your system.\n\n"
            "QGarage can install it now using the official installer script "
            f"from <a href='{install_url}'>{install_url}</a>."
        )
        msg.setDetailedText(
            f"The following command will be run:\n\n{install_cmd_display}"
        )
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        self._run_tool_install(tool)

    def _run_tool_install(self, tool: str) -> None:
        """Launch InstallToolWorker for *tool*."""
        if self._install_tool_worker is not None:
            # A previous install is still running
            return

        worker = InstallToolWorker(tool, parent=self.dock)
        worker.install_finished.connect(self._on_tool_install_finished)
        worker.finished.connect(worker.deleteLater)
        self._install_tool_worker = worker
        worker.start()
        log_info(f"Started {tool} installation worker", "plugin")

    def _on_tool_install_finished(
        self, tool: str, success: bool, error_text: str
    ) -> None:
        self._install_tool_worker = None

        if not success:
            log_error(f"{tool} installation failed: {error_text}")
            QMessageBox.critical(
                self.iface.mainWindow() if self.iface else None,
                f"Install {tool} failed",
                f"Could not install {tool}:\n\n{error_text}\n\n"
                "Please install it manually and restart QGIS.",
            )
            return

        log_info(f"{tool} installed successfully", "plugin")

        # Re-attempt to create the bridge for the newly installed tool
        if tool == "uv" and self.uv_bridge is None:
            try:
                self.uv_bridge = UvBridge(get_uv_executable())
            except RuntimeError as e:
                log_error(f"uv still not available after install: {e}")
        elif tool == "pixi" and self.pixi_bridge is None:
            try:
                from .core.pixi_bridge import PixiBridge

                self.pixi_bridge = PixiBridge(get_pixi_executable())
            except RuntimeError as e:
                log_error(f"pixi still not available after install: {e}")

        # Update status bar indicators
        self._update_status_bar()

        # If we now have at least one bridge, ensure the registry exists
        if self.registry is None and (
            self.uv_bridge is not None or self.pixi_bridge is not None
        ):
            apps_dir = getattr(self, "APPS_DIR", APPS_DIR)
            self.registry = AppRegistry(apps_dir, self.uv_bridge, self.pixi_bridge)
            self.registry.discover()
            if self.dock is not None:
                self.dock.set_registry(self.registry)
                for entry in self.registry.iter_entries():
                    self._prepare_app_environment_async(entry)
            self._register_processing_provider()
        elif self.registry is not None:
            # Update the registry's bridge references
            self.registry.uv_bridge = self.uv_bridge
            self.registry.pixi_bridge = self.pixi_bridge

        QMessageBox.information(
            self.iface.mainWindow() if self.iface else None,
            f"{tool} installed",
            f"{tool} was installed successfully.\n\n"
            "Apps that require this tool are now available.",
        )

    def _update_status_bar(self) -> None:
        """Sync the dock's status bar with current bridge availability."""
        if self.dock is None:
            return
        self.dock.status_bar.set_uv_connected(self.uv_bridge is not None)
        self.dock.status_bar.set_pixi_connected(self.pixi_bridge is not None)

    def _on_new_app_requested(self):
        apps_dir = getattr(self, "APPS_DIR", APPS_DIR)
        dialog = ScaffoldDialog(apps_dir, self.iface.mainWindow())
        dialog.app_created.connect(self._on_app_scaffolded)
        dialog.exec()

    def _on_app_scaffolded(self, app_id: str, install_now: bool):
        if install_now:
            self._on_app_installed(app_id, False)

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
