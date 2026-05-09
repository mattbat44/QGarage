from pathlib import Path

from qgis.PyQt.QtCore import QThread, pyqtSignal

from ..core.env_bridge import EnvBridge


class EnvSetupWorker(QThread):
    """Prepare a single app environment without blocking the UI thread."""

    setup_finished = pyqtSignal(str, bool, str)

    def __init__(self, app_id: str, app_dir: Path, bridge: EnvBridge, parent=None):
        super().__init__(parent)
        self.app_id = app_id
        self.app_dir = app_dir
        self.bridge = bridge

    def run(self) -> None:
        try:
            self.bridge.ensure_env(self.app_dir)
        except Exception as exc:
            self.setup_finished.emit(self.app_id, False, str(exc))
            return

        self.setup_finished.emit(self.app_id, True, "")