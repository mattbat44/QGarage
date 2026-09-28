from __future__ import annotations

from qgis.PyQt.QtCore import QThread, pyqtSignal


class BackendCheckWorker(QThread):
    """Verify one optional environment backend without blocking the UI."""

    check_finished = pyqtSignal(str, object, str)

    def __init__(self, tool: str, executable: str, parent=None) -> None:
        super().__init__(parent)
        self._tool = tool
        self._executable = executable

    def run(self) -> None:
        try:
            if self._tool == "uv":
                from ..core.uv_bridge import UvBridge

                bridge = UvBridge(self._executable)
            else:
                from ..core.pixi_bridge import PixiBridge

                bridge = PixiBridge(self._executable)
        except Exception as exc:
            self.check_finished.emit(self._tool, None, str(exc))
            return

        self.check_finished.emit(self._tool, bridge, "")