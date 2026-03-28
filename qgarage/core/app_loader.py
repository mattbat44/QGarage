import importlib
import importlib.util
import logging
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .base_app import BaseApp

from .app_state import AppHealth, AppState
from .uv_bridge import SysPathContext, UvBridge

logger = logging.getLogger("qgarage.app_loader")


class AppLoader:
    """Loads app modules dynamically with full fault isolation."""

    def __init__(self, uv_bridge: UvBridge):
        self.uv_bridge = uv_bridge
        self._loaded_modules: dict[str, object] = {}

    def load_app(
        self, app_dir: Path, app_meta: dict, health: AppHealth
    ) -> Optional["BaseApp"]:
        """Attempt to load an app. Returns a BaseApp instance or None on failure.

        The entire load sequence is wrapped in try/except so a single broken
        app can never crash the QGarage dashboard.
        """
        app_id = app_meta["id"]
        health.state = AppState.LOADING

        try:
            site_packages = self.uv_bridge.get_site_packages(app_dir)

            with SysPathContext(site_packages):
                entry_point = app_dir / app_meta.get("entry_point", "main.py")
                if not entry_point.exists():
                    raise FileNotFoundError(
                        f"Entry point {entry_point} not found for app '{app_id}'"
                    )

                module_name = f"qgarage.apps.{app_id}.main"
                spec = importlib.util.spec_from_file_location(
                    module_name, str(entry_point)
                )
                if spec is None or spec.loader is None:
                    raise ImportError(f"Cannot create module spec for {entry_point}")

                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                class_name = app_meta.get("class_name", "App")
                app_class = getattr(module, class_name, None)
                if app_class is None:
                    raise AttributeError(
                        f"Class '{class_name}' not found in {entry_point}"
                    )

                from .base_app import BaseApp

                if not issubclass(app_class, BaseApp):
                    raise TypeError(f"'{class_name}' does not inherit from BaseApp")

                instance = app_class(app_meta=app_meta, app_dir=app_dir)
                self._loaded_modules[app_id] = module

            health.record_success()
            logger.info(f"Successfully loaded app: {app_id}")
            return instance

        except Exception:
            error_msg = traceback.format_exc()
            health.record_error(error_msg)
            logger.error(f"Failed to load app '{app_id}':\n{error_msg}")
            module_name = f"qgarage.apps.{app_id}.main"
            sys.modules.pop(module_name, None)
            return None

    def unload_app(self, app_id: str) -> None:
        """Remove a loaded app's module from sys.modules."""
        module_name = f"qgarage.apps.{app_id}.main"
        sys.modules.pop(module_name, None)
        self._loaded_modules.pop(app_id, None)
        logger.info(f"Unloaded app: {app_id}")
