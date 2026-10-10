from __future__ import annotations

from qgis.PyQt.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    QVariantAnimation,
    pyqtSignal,
)
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.app_registry import ToolboxEntry
from ..themes import assets
from .app_card_widget import AppCardWidget
from .pill_frame import CircleButton, PillFrame, pill_margins


class ToolboxCardWidget(QFrame):
    """A card representing a toolbox containing multiple apps.

    Displays: icon area, title, description, expand/collapse button, and contained apps.
    Emits app_run_clicked(app_id) when a user clicks Run on any contained app.
    Emits app_reset_clicked(app_id) when a user clicks Reset on any contained app.
    """

    app_run_clicked = pyqtSignal(str)
    app_reset_clicked = pyqtSignal(str)
    app_refresh_clicked = pyqtSignal(str)
    app_check_updates_clicked = pyqtSignal(str)
    app_update_clicked = pyqtSignal(str)
    toolbox_primary_clicked = pyqtSignal(str)

    def __init__(
        self,
        toolbox_entry: ToolboxEntry,
        *,
        primary_action: str = "Open",
        action_enabled: bool | None = None,
        show_state_badge: bool = True,
        open_on_card_click: bool = True,
        show_context_menu: bool = True,
        toolbox_primary_action: str | None = None,
        toolbox_action_enabled: bool = True,
        installed_app_ids: set[str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.toolbox_entry = toolbox_entry
        self._primary_action = primary_action
        self._action_enabled = action_enabled
        self._show_state_badge = show_state_badge
        self._open_on_card_click = open_on_card_click
        self._show_context_menu = show_context_menu
        self._toolbox_primary_action = toolbox_primary_action
        self._toolbox_action_enabled = toolbox_action_enabled
        self._installed_app_ids = installed_app_ids or set()
        self._app_cards: dict[str, AppCardWidget] = {}
        self._pre_search_expanded: bool | None = None

        self.setObjectName("toolboxCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        self._build_ui()

    def _build_ui(self):
        # Main vertical layout for the entire toolbox card
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # Header area (toolbox info + expand/collapse button)
        self._header_frame = PillFrame()
        self._header_frame.setObjectName("toolboxHeader")
        self._header_frame.setMinimumHeight(104)
        self._header_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(self._header_frame)
        header_layout.setContentsMargins(*pill_margins(20, 10, 18, 10))
        header_layout.setSpacing(14)

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

        self._toolbox_primary_button = None
        if self._toolbox_primary_action is not None:
            self._toolbox_primary_button = QPushButton(self._toolbox_primary_action)
            self._toolbox_primary_button.setEnabled(self._toolbox_action_enabled)
            self._toolbox_primary_button.clicked.connect(
                lambda: self.toolbox_primary_clicked.emit(self.toolbox_entry.toolbox_id)
            )
            header_layout.addWidget(self._toolbox_primary_button)

        # Expand/collapse button
        expand_column = QVBoxLayout()
        expand_column.setSpacing(0)
        expand_column.addStretch()
        self._expand_button = CircleButton(68)
        self._expand_button.setObjectName("toolboxExpandButton")
        self._expand_button.setToolTip("view tools")
        self._expand_button.clicked.connect(self._toggle_expanded)
        expand_column.addWidget(
            self._expand_button, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        expand_caption = QLabel("view tools")
        expand_caption.setObjectName("appCardActionCaption")
        expand_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        expand_column.addWidget(expand_caption)
        expand_column.addStretch()
        header_layout.addLayout(expand_column)

        self._main_layout.addWidget(self._header_frame)

        # Container for app cards (initially hidden)
        self._apps_container = QWidget()
        self._apps_container.setObjectName("toolboxAppsContainer")
        self._apps_layout = QVBoxLayout(self._apps_container)
        self._apps_layout.setContentsMargins(28, 0, 0, 0)
        self._apps_layout.setSpacing(0)
        self._apps_container.setVisible(False)
        self._apps_container.setMaximumHeight(0)

        self._apps_animation = QPropertyAnimation(
            self._apps_container, b"maximumHeight", self
        )
        self._apps_animation.setDuration(200)
        self._apps_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._apps_animation.finished.connect(self._on_apps_animation_finished)

        # Arrow rotation: 0 = pointing down (open), -90 = pointing right (closed).
        self._arrow_animation = QVariantAnimation(self)
        self._arrow_animation.setDuration(200)
        self._arrow_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._arrow_animation.valueChanged.connect(
            lambda value: self._expand_button.set_icon_rotation(float(value))
        )

        # Add app cards
        for app_id, app_entry in self.toolbox_entry.app_entries.items():
            is_installed = app_id in self._installed_app_ids
            card = AppCardWidget(
                app_id,
                app_entry.app_meta,
                app_entry.health,
                app_dir=app_entry.app_dir,
                update_available=app_entry.update_available,
                available_version=app_entry.available_version,
                checking_updates=app_entry.checking_updates,
                primary_action="Installed" if is_installed else self._primary_action,
                action_enabled=False if is_installed else self._action_enabled,
                show_state_badge=self._show_state_badge,
                open_on_card_click=self._open_on_card_click,
                show_context_menu=self._show_context_menu,
            )
            card.run_clicked.connect(self.app_run_clicked.emit)
            card.reset_clicked.connect(self.app_reset_clicked.emit)
            card.refresh_clicked.connect(self.app_refresh_clicked.emit)
            card.check_updates_clicked.connect(self.app_check_updates_clicked.emit)
            card.update_clicked.connect(self.app_update_clicked.emit)
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

        # Fallback: the real toolbox icon asset with the app count overlaid.
        fallback = QLabel()
        fallback.setFixedSize(64, 64)
        brand_pixmap = assets.pixmap("toolbox_icon", QSize(64, 64))
        if brand_pixmap is not None:
            fallback.setPixmap(brand_pixmap)
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            count_layout = QVBoxLayout(fallback)
            count_layout.setContentsMargins(0, 18, 0, 0)
            count_layout.setSpacing(0)
            count = QLabel(str(len(self.toolbox_entry.app_entries)))
            count.setObjectName("toolboxCountNumber")
            count.setAlignment(Qt.AlignmentFlag.AlignCenter)
            count_layout.addWidget(count)
            tools = QLabel("tools")
            tools.setObjectName("appCardActionCaption")
            tools.setAlignment(Qt.AlignmentFlag.AlignCenter)
            count_layout.addWidget(tools)
            count_layout.addStretch()
            return fallback
        fallback.setStyleSheet(
            "background: #FFFFFF; border: 2px solid #8DAD25; border-radius: 10px;"
        )
        return fallback

    def _apply_expand_icon(self, expanded: bool, animate: bool = False) -> None:
        """Point the arrow down when open and sideways when closed."""
        if self._expand_button.icon().isNull():
            pixmap = assets.pixmap("toolbox_dropdown", QSize(64, 64))
            if pixmap is None:
                return
            self._expand_button.setIcon(QIcon(pixmap))
            # Rotate and centre about the triangle's centroid, not the SVG box.
            self._expand_button.set_icon_anchor(0.49, 0.31)
        target = 0.0 if expanded else -90.0
        self._arrow_animation.stop()
        if not animate:
            self._expand_button.set_icon_rotation(target)
            return
        self._arrow_animation.setStartValue(self._expand_button._icon_rotation)
        self._arrow_animation.setEndValue(target)
        self._arrow_animation.start()

    def _toggle_expanded(self):
        """Toggle the expanded/collapsed state of the toolbox."""
        self._set_expanded(not self.toolbox_entry.is_expanded)

    def _set_expanded(self, expanded: bool, animate: bool = True):
        """Apply expanded state and animate the app list height."""
        self.toolbox_entry.is_expanded = expanded
        self._apply_expand_icon(expanded, animate=animate)
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
                if (
                    self._toolbox_primary_button is not None
                    and self._toolbox_primary_button.geometry().contains(click_pos)
                ):
                    event.ignore()
                    return
                self._toggle_expanded()
                event.accept()
                return
        QFrame.mouseReleaseEvent(self._header_frame, event)

    def set_search_matches(self, matching_app_ids: set[str] | None) -> None:
        """Apply a search to the contained apps.

        ``None`` clears the search: every app is shown again and the expanded
        state from before the search is restored. A non-empty set shows only
        those apps and expands the toolbox; an empty set (the toolbox itself
        matched) shows every app without changing the expanded state.
        """
        if matching_app_ids is None:
            for card in self._app_cards.values():
                card.setVisible(True)
            if self._pre_search_expanded is not None:
                restore = self._pre_search_expanded
                self._pre_search_expanded = None
                if restore != self.toolbox_entry.is_expanded:
                    self._set_expanded(restore, animate=False)
            return

        for app_id, card in self._app_cards.items():
            card.setVisible(not matching_app_ids or app_id in matching_app_ids)
        if matching_app_ids:
            if self._pre_search_expanded is None:
                self._pre_search_expanded = self.toolbox_entry.is_expanded
            if not self.toolbox_entry.is_expanded:
                self._set_expanded(True, animate=False)

    def update_app_state(self, app_id: str):
        """Refresh a contained app card's badge."""
        card = self._app_cards.get(app_id)
        if card:
            app_entry = self.toolbox_entry.app_entries.get(app_id)
            if app_entry is not None:
                card.set_update_status(
                    update_available=app_entry.update_available,
                    available_version=app_entry.available_version,
                    checking_updates=app_entry.checking_updates,
                )
            card.update_state()

    def set_app_backend_checked(self, app_id: str, checked: bool = True) -> None:
        """Update the neutral backend-check badge on one contained app."""
        card = self._app_cards.get(app_id)
        if card is not None:
            card.set_backend_checked(checked)
