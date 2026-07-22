from __future__ import annotations

from qgis.PyQt.QtCore import QThread, pyqtSignal

from ..core.app_update import check_for_app_update


class UpdateCheckWorker(QThread):
    """Check one installed app source for a newer version in the background."""

    check_finished = pyqtSignal(str, bool, str)

    def __init__(self, app_id: str, app_meta: dict, parent=None):
        super().__init__(parent)
        self.app_id = app_id
        self.app_meta = dict(app_meta)

    def run(self) -> None:
        result = check_for_app_update(self.app_meta)
        self.check_finished.emit(
            self.app_id,
            result.available,
            result.available_version or "",
        )
