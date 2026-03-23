import logging
import shutil
from pathlib import Path

from qgis.PyQt.QtCore import QThread, pyqtSignal

logger = logging.getLogger("qhub.uninstall_worker")


class UninstallWorker(QThread):
    """Worker thread to remove an app directory and its venv.

    Signals:
        finished(bool, str): (success, app_id_or_error_message)
    """

    finished = pyqtSignal(bool, str)

    def __init__(self, app_dir: Path, app_id: str, parent=None):
        super().__init__(parent)
        self.app_dir = app_dir
        self.app_id = app_id

    def run(self):
        try:
            if self.app_dir.exists():
                shutil.rmtree(self.app_dir)
                logger.info(f"Removed app directory: {self.app_dir}")
            self.finished.emit(True, self.app_id)
        except Exception as e:
            self.finished.emit(False, f"Failed to uninstall '{self.app_id}': {e}")
