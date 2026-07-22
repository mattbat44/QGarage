from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import QThread, pyqtSignal

from ..core.app_update import apply_update_from_source


class AppUpdateWorker(QThread):
    """Apply an in-place app update from the app's recorded install source."""

    update_finished = pyqtSignal(str, bool, bool, bool, str)

    def __init__(self, app_id: str, app_dir: Path, app_meta: dict, parent=None):
        super().__init__(parent)
        self.app_id = app_id
        self.app_dir = app_dir
        self.app_meta = dict(app_meta)

    def run(self) -> None:
        try:
            result = apply_update_from_source(self.app_dir, self.app_meta)
        except Exception as exc:
            self.update_finished.emit(self.app_id, False, False, False, str(exc))
            return

        self.update_finished.emit(
            self.app_id,
            True,
            result.requirements_changed,
            result.pixi_changed,
            "",
        )
