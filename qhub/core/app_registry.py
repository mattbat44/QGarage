import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .app_loader import AppLoader
from .app_state import AppHealth
from .uv_bridge import UvBridge

if TYPE_CHECKING:
    from .base_app import BaseApp

logger = logging.getLogger("qhub.app_registry")


class AppEntry:
    """Container for a single registered app."""

    def __init__(self, app_dir: Path, app_meta: dict):
        self.app_dir = app_dir
        self.app_meta = app_meta
        self.health = AppHealth()
        self.instance: Optional["BaseApp"] = None

    @property
    def app_id(self) -> str:
        return self.app_meta["id"]

    @property
    def app_name(self) -> str:
        return self.app_meta.get("name", self.app_id)


class AppRegistry:
    """Discovers, loads, and tracks all installed QHub apps."""

    def __init__(self, apps_dir: Path, uv_bridge: UvBridge):
        self.apps_dir = apps_dir
        self.uv_bridge = uv_bridge
        self.loader = AppLoader(uv_bridge)
        self._entries: dict[str, AppEntry] = {}

    @property
    def entries(self) -> dict[str, AppEntry]:
        return dict(self._entries)

    def discover(self) -> list[AppEntry]:
        """Scan apps_dir for subdirectories containing app_meta.json."""
        discovered: list[AppEntry] = []
        if not self.apps_dir.exists():
            self.apps_dir.mkdir(parents=True, exist_ok=True)
            return discovered

        for child in sorted(self.apps_dir.iterdir()):
            meta_file = child / "app_meta.json"
            if not child.is_dir() or not meta_file.exists():
                continue
            try:
                with open(meta_file, encoding="utf-8") as f:
                    app_meta = json.load(f)
                app_id = app_meta.get("id")
                if not app_id:
                    logger.warning(f"Skipping {child}: app_meta.json missing 'id'")
                    continue
                if app_id not in self._entries:
                    entry = AppEntry(child, app_meta)
                    self._entries[app_id] = entry
                    discovered.append(entry)
                    logger.info(f"Discovered app: {app_id}")
            except Exception as e:
                logger.error(f"Error reading {meta_file}: {e}")

        return discovered

    def load_all(self) -> None:
        """Load all discovered apps."""
        for entry in self._entries.values():
            if entry.instance is None:
                self._load_entry(entry)

    def load_app(self, app_id: str) -> Optional["BaseApp"]:
        """Load a specific app by ID."""
        entry = self._entries.get(app_id)
        if entry is None:
            logger.warning(f"App '{app_id}' not found in registry")
            return None
        return self._load_entry(entry)

    def _load_entry(self, entry: AppEntry) -> Optional["BaseApp"]:
        instance = self.loader.load_app(entry.app_dir, entry.app_meta, entry.health)
        entry.instance = instance
        if instance is not None:
            try:
                instance.on_load()
            except Exception:
                logger.exception(f"on_load() failed for {entry.app_id}")
        return instance

    def unload_app(self, app_id: str) -> None:
        """Unload a specific app."""
        entry = self._entries.get(app_id)
        if entry is None:
            return
        if entry.instance is not None:
            try:
                entry.instance.on_unload()
            except Exception:
                logger.exception(f"on_unload() failed for {app_id}")
            entry.instance = None
        self.loader.unload_app(app_id)

    def remove_app(self, app_id: str) -> None:
        """Unload and remove an app from the registry (does not delete files)."""
        self.unload_app(app_id)
        self._entries.pop(app_id, None)

    def unload_all(self) -> None:
        """Unload all apps."""
        for app_id in list(self._entries.keys()):
            self.unload_app(app_id)

    def register_entry(self, entry: AppEntry) -> None:
        """Add an app entry to the registry (used after remote/local install)."""
        self._entries[entry.app_id] = entry
