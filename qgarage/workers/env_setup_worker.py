import logging
import shutil
from pathlib import Path

from qgis.PyQt.QtCore import QThread, pyqtSignal

from ..core.env_bridge import EnvBridge

logger = logging.getLogger("qgarage.env_setup_worker")

# Directories that constitute a cached environment for an app
_ENV_DIRS = (".venv", ".pixi")


class EnvSetupWorker(QThread):
    """Prepare a single app environment without blocking the UI thread.

    Parameters
    ----------
    clean:
        When *True* the worker removes any existing environment directories
        (`.venv`, `.pixi`) before calling ``bridge.ensure_env()``.  This
        forces a full reinstall of all dependencies — used by the
        "Refresh App" right-click action.
    """

    setup_finished = pyqtSignal(str, bool, str)

    def __init__(
        self,
        app_id: str,
        app_dir: Path,
        bridge: EnvBridge,
        parent=None,
        *,
        clean: bool = False,
    ):
        super().__init__(parent)
        self.app_id = app_id
        self.app_dir = app_dir
        self.bridge = bridge
        self._clean = clean

    def run(self) -> None:
        if self._clean:
            self._remove_env_dirs()

        try:
            self.bridge.ensure_env(self.app_dir)
        except Exception as exc:
            self.setup_finished.emit(self.app_id, False, str(exc))
            return

        self.setup_finished.emit(self.app_id, True, "")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _remove_env_dirs(self) -> None:
        """Delete cached environment directories so they are rebuilt from scratch."""
        for name in _ENV_DIRS:
            env_dir = self.app_dir / name
            if env_dir.exists():
                try:
                    shutil.rmtree(env_dir)
                    logger.info("Removed env dir: %s", env_dir)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not remove %s: %s", env_dir, exc)
