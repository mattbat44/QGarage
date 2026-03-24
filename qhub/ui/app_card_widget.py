from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from ..core.app_state import AppHealth, AppState


class AppCardWidget(QFrame):
    """A card representing an installed app in the dashboard grid.

    Displays: icon area, title, description, state badge, and Run button.
    Emits run_clicked(app_id) when the user clicks Run.
    Emits reset_clicked(app_id) when the user clicks Reset on a crashed app.
    """

    run_clicked = pyqtSignal(str)
    reset_clicked = pyqtSignal(str)

    def __init__(self, app_id: str, app_meta: dict, health: AppHealth, app_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.app_id = app_id
        self._app_meta = app_meta
        self._health = health
        self._app_dir = app_dir

        self.setProperty("class", "AppCardWidget")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(72)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._build_ui()
        self._update_state_badge()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # Icon
        icon_widget = self._build_icon()
        layout.addWidget(icon_widget)

        # Text area
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        # Title row with badge
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        self._title_label = QLabel(self._app_meta.get("name", self.app_id))
        self._title_label.setObjectName("appCardTitle")
        title_row.addWidget(self._title_label)

        self._badge_label = QLabel()
        self._badge_label.setObjectName("appStateBadge")
        self._badge_label.setVisible(False)
        title_row.addWidget(self._badge_label)

        title_row.addStretch()
        text_layout.addLayout(title_row)

        # Description
        desc = self._app_meta.get("description", "")
        if desc:
            desc_label = QLabel(desc)
            desc_label.setObjectName("appCardDescription")
            desc_label.setWordWrap(True)
            text_layout.addWidget(desc_label)

        layout.addLayout(text_layout, stretch=1)

        # Buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(4)

        self._run_button = QPushButton("Open")
        self._run_button.setObjectName("appCardRunButton")
        self._run_button.clicked.connect(lambda: self.run_clicked.emit(self.app_id))
        btn_layout.addWidget(self._run_button)

        self._reset_button = QPushButton("Reset")
        self._reset_button.setVisible(False)
        self._reset_button.clicked.connect(lambda: self.reset_clicked.emit(self.app_id))
        btn_layout.addWidget(self._reset_button)

        layout.addLayout(btn_layout)

    def update_state(self):
        """Refresh the badge to reflect current AppHealth state."""
        self._update_state_badge()

    def _update_state_badge(self):
        state = self._health.state
        badge_map = {
            AppState.READY: ("Ready", "background-color: #4CAF50;"),
            AppState.RUNNING: ("Running", "background-color: #2196F3;"),
            AppState.ERROR: ("Error", "background-color: #FF9800;"),
            AppState.CRASHED: ("Crashed", "background-color: #F44336;"),
            AppState.DISABLED: ("Disabled", "background-color: #9E9E9E;"),
            AppState.INSTALLING: ("Installing", "background-color: #4CAF50;"),
            AppState.LOADING: ("Loading", "background-color: #2196F3;"),
        }
        text, style = badge_map.get(state, ("", ""))
        self._badge_label.setText(text)
        self._badge_label.setStyleSheet(style)
        self._badge_label.setVisible(bool(text))

        if state == AppState.ERROR and self._health.last_error:
            self._badge_label.setToolTip(
                f"Errors: {self._health.consecutive_errors}\n"
                f"Last: {self._health.last_error[:200]}"
            )

        self._reset_button.setVisible(state == AppState.CRASHED)
        self._run_button.setEnabled(state in (AppState.READY, AppState.ERROR))

    def _build_icon(self) -> QLabel:
        """Build the icon widget from app_meta icon_path, or a coloured fallback."""
        icon_path_value = (self._app_meta.get("icon_path") or "").strip()
        if icon_path_value and self._app_dir is not None:
            resolved = self._app_dir / icon_path_value
            if resolved.is_file():
                pixmap = QPixmap(str(resolved))
                if not pixmap.isNull():
                    label = QLabel()
                    label.setFixedSize(40, 40)
                    label.setPixmap(
                        pixmap.scaled(
                            40, 40,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    return label

        # Fallback: coloured square
        fallback = QLabel()
        fallback.setFixedSize(40, 40)
        fallback.setStyleSheet("background-color: #4CAF50; border-radius: 8px;")
        return fallback

    def mouseReleaseEvent(self, event):
        """Open app when the card background is clicked.

        Keeps button clicks working normally by ignoring clicks that originate
        from a QPushButton child.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            click_pos = (
                event.pos() if hasattr(event, "pos") else event.position().toPoint()
            )
            child = self.childAt(click_pos)
            if not isinstance(child, QPushButton) and self._run_button.isEnabled():
                self.run_clicked.emit(self.app_id)
                event.accept()
                return
        super().mouseReleaseEvent(event)
