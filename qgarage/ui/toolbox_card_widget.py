from qgis.PyQt.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtSignal
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.app_registry import ToolboxEntry
from .app_card_widget import AppCardWidget


class ToolboxCardWidget(QFrame):
    """A card representing a toolbox containing multiple apps.

    Displays: icon area, title, description, expand/collapse button, and contained apps.
    Emits app_run_clicked(app_id) when a user clicks Run on any contained app.
    Emits app_reset_clicked(app_id) when a user clicks Reset on any contained app.
    """

    app_run_clicked = pyqtSignal(str)
    app_reset_clicked = pyqtSignal(str)

    def __init__(
        self,
        toolbox_entry: ToolboxEntry,
        parent=None,
    ):
        super().__init__(parent)
        self.toolbox_entry = toolbox_entry
        self._app_cards: dict[str, AppCardWidget] = {}

        self.setProperty("class", "ToolboxCardWidget")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(72)

        self._build_ui()

    def _build_ui(self):
        # Main vertical layout for the entire toolbox card
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # Header area (toolbox info + expand/collapse button)
        self._header_frame = QFrame()
        self._header_frame.setObjectName("toolboxHeader")
        self._header_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(self._header_frame)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(10)

        # Icon
        icon_widget = self._build_icon()
        header_layout.addWidget(icon_widget)

        # Text area
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        # Title row
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        self._title_label = QLabel(self.toolbox_entry.toolbox_name)
        self._title_label.setObjectName("toolboxCardTitle")
        title_row.addWidget(self._title_label)

        # App count badge
        app_count = len(self.toolbox_entry.app_entries)
        self._count_badge = QLabel(f"{app_count} app" + ("s" if app_count != 1 else ""))
        self._count_badge.setObjectName("toolboxCountBadge")
        title_row.addWidget(self._count_badge)

        title_row.addStretch()
        text_layout.addLayout(title_row)

        # Description
        desc = self.toolbox_entry.toolbox_meta.get("description", "")
        if desc:
            desc_label = QLabel(desc)
            desc_label.setObjectName("toolboxCardDescription")
            desc_label.setWordWrap(True)
            text_layout.addWidget(desc_label)

        header_layout.addLayout(text_layout, stretch=1)

        # Expand/collapse button
        self._expand_button = QToolButton()
        self._expand_button.setObjectName("toolboxExpandButton")
        self._expand_button.setFixedSize(32, 32)
        self._expand_button.setAutoRaise(True)
        self._expand_button.setArrowType(Qt.ArrowType.RightArrow)
        self._expand_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expand_button.clicked.connect(self._toggle_expanded)
        header_layout.addWidget(self._expand_button)

        self._main_layout.addWidget(self._header_frame)

        # Container for app cards (initially hidden)
        self._apps_container = QWidget()
        self._apps_container.setObjectName("toolboxAppsContainer")
        self._apps_layout = QVBoxLayout(self._apps_container)
        self._apps_layout.setContentsMargins(12, 0, 12, 8)
        self._apps_layout.setSpacing(8)
        self._apps_container.setVisible(False)
        self._apps_container.setMaximumHeight(0)

        self._apps_animation = QPropertyAnimation(
            self._apps_container, b"maximumHeight", self
        )
        self._apps_animation.setDuration(180)
        self._apps_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._apps_animation.finished.connect(self._on_apps_animation_finished)

        # Add app cards
        for app_id, app_entry in self.toolbox_entry.app_entries.items():
            card = AppCardWidget(
                app_id, app_entry.app_meta, app_entry.health, app_dir=app_entry.app_dir
            )
            card.run_clicked.connect(self.app_run_clicked.emit)
            card.reset_clicked.connect(self.app_reset_clicked.emit)
            self._app_cards[app_id] = card
            self._apps_layout.addWidget(card)

        self._main_layout.addWidget(self._apps_container)

        # Connect header click to toggle
        self._header_frame.mouseReleaseEvent = self._on_header_clicked
        self._set_expanded(self.toolbox_entry.is_expanded, animate=False)

    def _build_icon(self) -> QLabel:
        """Build the icon widget from toolbox_meta icon_path, or a coloured fallback."""
        icon_path_value = (
            self.toolbox_entry.toolbox_meta.get("icon_path") or ""
        ).strip()
        if icon_path_value:
            resolved = self.toolbox_entry.toolbox_dir / icon_path_value
            if resolved.is_file():
                pixmap = QPixmap(str(resolved))
                if not pixmap.isNull():
                    label = QLabel()
                    label.setFixedSize(40, 40)
                    label.setPixmap(
                        pixmap.scaled(
                            40,
                            40,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    return label

        # Fallback: coloured square (different color than single apps)
        fallback = QLabel()
        fallback.setFixedSize(40, 40)
        fallback.setStyleSheet("background-color: #FF9800; border-radius: 8px;")
        return fallback

    def _toggle_expanded(self):
        """Toggle the expanded/collapsed state of the toolbox."""
        self._set_expanded(not self.toolbox_entry.is_expanded)

    def _set_expanded(self, expanded: bool, animate: bool = True):
        """Apply expanded state and animate the app list height."""
        self.toolbox_entry.is_expanded = expanded
        self._expand_button.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self._header_frame.setProperty("expanded", expanded)
        self.setProperty("expanded", expanded)
        self.style().unpolish(self)
        self.style().polish(self)
        self._header_frame.style().unpolish(self._header_frame)
        self._header_frame.style().polish(self._header_frame)

        target_height = self._apps_container.sizeHint().height()
        current_height = (
            self._apps_container.height() or self._apps_container.maximumHeight()
        )
        self._apps_animation.stop()

        if not animate:
            self._apps_container.setVisible(expanded)
            self._apps_container.setMaximumHeight(target_height if expanded else 0)
            if expanded:
                self._apps_container.setMaximumHeight(16777215)
            return

        if expanded:
            self._apps_container.setVisible(True)
            start_height = max(0, current_height)
            self._apps_container.setMaximumHeight(start_height)
            self._apps_animation.setStartValue(start_height)
            self._apps_animation.setEndValue(target_height)
            self._apps_animation.start()
            return

        start_height = current_height or target_height
        self._apps_container.setMaximumHeight(start_height)
        self._apps_animation.setStartValue(start_height)
        self._apps_animation.setEndValue(0)
        self._apps_animation.start()

    def _on_apps_animation_finished(self):
        """Release height constraints after expansion and hide when collapsed."""
        if self.toolbox_entry.is_expanded:
            self._apps_container.setMaximumHeight(16777215)
            return

        self._apps_container.setVisible(False)

    def _on_header_clicked(self, event):
        """Toggle expansion when the header background is clicked."""
        if event.button() == Qt.MouseButton.LeftButton:
            click_pos = (
                event.pos() if hasattr(event, "pos") else event.position().toPoint()
            )
            if not self._expand_button.geometry().contains(click_pos):
                self._toggle_expanded()
                event.accept()
                return
        QFrame.mouseReleaseEvent(self._header_frame, event)

    def update_app_state(self, app_id: str):
        """Refresh a contained app card's badge."""
        card = self._app_cards.get(app_id)
        if card:
            card.update_state()
