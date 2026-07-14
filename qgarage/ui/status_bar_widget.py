from __future__ import annotations
"""Minimal status bar showing uv / pixi connection status at the bottom of the dock.

Each indicator is a small clickable label: ⚡ tool-name.
  - Blue  → tool found and verified.
  - Grey  → tool not found; click to install via the system's preferred method.
"""
import logging

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

logger = logging.getLogger("qgarage.status_bar")

# Blue used for "connected" glow
_COLOR_CONNECTED = "#2196F3"
# Muted grey used for "not found"
_COLOR_DISCONNECTED = "#888888"


class _ToolIndicator(QWidget):
    """A ⚡ label + tool-name label that together act as a button.

    When *not* connected the widget emits ``install_requested`` on left-click.
    When connected it does nothing (the indicator is purely informational).
    """

    install_requested = pyqtSignal()

    def __init__(self, tool_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tool_name = tool_name
        self._connected = False

        self.setObjectName(f"qgarageToolIndicator_{tool_name}")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._bolt = QLabel("⚡")
        self._bolt.setObjectName("qgarageToolIndicatorBolt")
        layout.addWidget(self._bolt)

        self._name_label = QLabel(tool_name)
        self._name_label.setObjectName("qgarageToolIndicatorName")
        layout.addWidget(self._name_label)

        self._apply_style()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_connected(self, connected: bool) -> None:
        """Update the visual state; does NOT trigger install logic."""
        self._connected = connected
        self._apply_style()

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_style(self) -> None:
        color = _COLOR_CONNECTED if self._connected else _COLOR_DISCONNECTED

        bolt_qss = f"color: {color}; font-size: 11px;"
        name_qss = f"color: {color}; font-size: 10px;"

        if self._connected:
            tip = f"{self._tool_name} is connected"
            cursor = Qt.CursorShape.ArrowCursor
        else:
            tip = (
                f"{self._tool_name} not found — click to install using the "
                "system's preferred method"
            )
            cursor = Qt.CursorShape.PointingHandCursor

        self._bolt.setStyleSheet(bolt_qss)
        self._name_label.setStyleSheet(name_qss)
        self.setToolTip(tip)
        self.setCursor(cursor)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if not self._connected and event.button() == Qt.MouseButton.LeftButton:
            self.install_requested.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class StatusBarWidget(QWidget):
    """Thin bar pinned to the bottom of the dashboard dock.

    Signals
    -------
    uv_install_requested
        Emitted when the user clicks the uv indicator while uv is not found.
    pixi_install_requested
        Emitted when the user clicks the pixi indicator while pixi is not found.
    """

    uv_install_requested = pyqtSignal()
    pixi_install_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("qgarageStatusBar")
        self.setFixedHeight(22)
        self._build_ui()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(16)

        self._pixi_indicator = _ToolIndicator("pixi", self)
        self._pixi_indicator.install_requested.connect(self.pixi_install_requested.emit)
        layout.addWidget(self._pixi_indicator)

        self._uv_indicator = _ToolIndicator("uv", self)
        self._uv_indicator.install_requested.connect(self.uv_install_requested.emit)
        layout.addWidget(self._uv_indicator)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_uv_connected(self, connected: bool) -> None:
        self._uv_indicator.set_connected(connected)

    def set_pixi_connected(self, connected: bool) -> None:
        self._pixi_indicator.set_connected(connected)

    @property
    def uv_connected(self) -> bool:
        return self._uv_indicator.is_connected

    @property
    def pixi_connected(self) -> bool:
        return self._pixi_indicator.is_connected
