from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import QThread, pyqtSignal

from ..core.marketplace import MarketplaceItem, scan_marketplace


class MarketplaceScanWorker(QThread):
    """Scan local marketplace directories without blocking the QGIS UI."""

    scan_finished = pyqtSignal(list, str)

    def __init__(self, directories: list[Path], parent=None):
        super().__init__(parent)
        self._directories = list(directories)

    def run(self) -> None:
        try:
            items = scan_marketplace(
                self._directories, is_cancelled=self.isInterruptionRequested
            )
        except Exception as exc:
            self.scan_finished.emit([], f"Scan failed: {exc}")
            return
        if self.isInterruptionRequested():
            self.scan_finished.emit([], "Scan cancelled.")
            return
        self.scan_finished.emit(items, "")