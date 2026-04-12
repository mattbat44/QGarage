from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.base_app import BaseApp


class AppHostWidget(QWidget):
    """Container that hosts a running app's auto-generated UI.

    Shows a back button to return to the card grid.
    """

    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_app: BaseApp | None = None
        self._build_ui()

    def _build_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Top bar with back button
        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(8, 8, 8, 4)

        back_btn = QPushButton("< Back")
        back_btn.setObjectName("qgarageBackButton")
        back_btn.clicked.connect(self.back_requested.emit)
        top_layout.addWidget(back_btn)
        top_layout.addStretch()

        self._layout.addWidget(top_bar)

        # Scroll area for app content
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._layout.addWidget(self._scroll, stretch=1)

    def show_app(self, app: BaseApp) -> None:
        """Build and display an app's widget."""
        self._current_app = app
        widget = app.build_widget()
        self._scroll.setWidget(widget)

    def has_app(self) -> bool:
        """Check if an app widget is currently loaded."""
        return self._current_app is not None

    def clear(self) -> None:
        """Remove the current app's widget."""
        if self._current_app is not None:
            self._current_app = None
        empty = QWidget()
        self._scroll.setWidget(empty)
