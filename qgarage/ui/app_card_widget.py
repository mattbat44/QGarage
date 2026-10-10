from __future__ import annotations

from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import (
    QAction,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from ..core.app_state import AppHealth, AppState
from ..core.constants import PIXI_TOML_FILENAME
from ..themes import assets
from .pill_frame import CircleButton, PillFrame, pill_margins

ICON_BOX_SIZE = 64
ACTION_ICON_SIZE = 56


class AppCardWidget(PillFrame):
    """A pill-shaped card representing an installed app.

    Left: icon box with backend label. Middle: title, version/author,
    description. Right: large state icon (open / running / installing / update)
    with a tiny caption.
    """

    run_clicked = pyqtSignal(str)
    reset_clicked = pyqtSignal(str)
    #: Emitted when the user chooses "Refresh App" from the right-click menu.
    #: The plugin handles environment teardown + reinstall.
    refresh_clicked = pyqtSignal(str)
    check_updates_clicked = pyqtSignal(str)
    update_clicked = pyqtSignal(str)

    def __init__(
        self,
        app_id: str,
        app_meta: dict,
        health: AppHealth,
        app_dir: Optional[Path] = None,
        *,
        update_available: bool = False,
        available_version: Optional[str] = None,
        checking_updates: bool = False,
        primary_action: str = "Open",
        action_enabled: Optional[bool] = None,
        show_state_badge: bool = True,
        open_on_card_click: bool = True,
        show_context_menu: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.app_id = app_id
        self._app_meta = app_meta
        self._health = health
        self._app_dir = app_dir
        self._update_available = update_available
        self._available_version = available_version
        self._checking_updates = checking_updates
        self._primary_action = primary_action
        self._action_enabled = action_enabled
        self._show_state_badge = show_state_badge
        self._open_on_card_click = open_on_card_click
        self._show_context_menu = show_context_menu
        self._backend_checked = False

        self.setObjectName("appCard")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.setMinimumHeight(104)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._build_ui()
        self._update_state_badge()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _backend_name(self) -> str:
        if self._app_dir is not None and (self._app_dir / PIXI_TOML_FILENAME).exists():
            return "pixi"
        return "uv"

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(*pill_margins(20, 10, 18, 10))
        layout.setSpacing(14)

        # Left: icon box + backend label
        icon_column = QVBoxLayout()
        icon_column.setSpacing(2)
        icon_column.addStretch()
        icon_column.addWidget(
            self._build_icon(), alignment=Qt.AlignmentFlag.AlignHCenter
        )
        self._backend_label = QLabel(self._backend_name())
        self._backend_label.setObjectName("appCardBackend")
        self._backend_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_column.addWidget(self._backend_label)
        icon_column.addStretch()
        layout.addLayout(icon_column)

        # Middle: text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._title_label = QLabel(self._app_meta.get("name", self.app_id))
        self._title_label.setObjectName("appCardTitle")
        self._title_label.setWordWrap(True)
        title_row.addWidget(self._title_label, stretch=1)

        self._badge_label = QLabel()
        self._badge_label.setObjectName("appStateBadge")
        self._badge_label.setVisible(False)
        title_row.addWidget(self._badge_label)
        text_layout.addLayout(title_row)

        meta_parts = []
        version = (self._app_meta.get("version") or "").strip()
        if version:
            meta_parts.append(f"v{version}")
        author = (self._app_meta.get("author") or "").strip()
        if author:
            meta_parts.append(f"Developed by {author}")
        if meta_parts:
            meta_label = QLabel("   ".join(meta_parts))
            meta_label.setObjectName("appCardMeta")
            meta_label.setWordWrap(True)
            text_layout.addWidget(meta_label)

        desc = self._app_meta.get("description", "")
        if desc:
            desc_label = QLabel(desc)
            desc_label.setObjectName("appCardDescription")
            desc_label.setWordWrap(True)
            text_layout.addWidget(desc_label)

        text_layout.addStretch()
        layout.addLayout(text_layout, stretch=1)

        # Right: state icon + caption
        action_column = QVBoxLayout()
        action_column.setSpacing(0)
        action_column.addStretch()

        self._run_button = self._make_icon_button("appCardRunButton")
        self._run_button.clicked.connect(lambda: self.run_clicked.emit(self.app_id))
        action_column.addWidget(
            self._run_button, alignment=Qt.AlignmentFlag.AlignHCenter
        )

        self._update_button = self._make_icon_button("appCardUpdateButton")
        self._update_button.setIcon(assets.icon("update_tool", ACTION_ICON_SIZE))
        self._update_button.setVisible(False)
        self._update_button.clicked.connect(
            lambda: self.update_clicked.emit(self.app_id)
        )
        action_column.addWidget(
            self._update_button, alignment=Qt.AlignmentFlag.AlignHCenter
        )

        self._reset_button = QPushButton("reset")
        self._reset_button.setObjectName("appCardResetButton")
        self._reset_button.setVisible(False)
        self._reset_button.clicked.connect(lambda: self.reset_clicked.emit(self.app_id))
        action_column.addWidget(
            self._reset_button, alignment=Qt.AlignmentFlag.AlignHCenter
        )

        self._action_caption = QLabel()
        self._action_caption.setObjectName("appCardActionCaption")
        self._action_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        action_column.addWidget(self._action_caption)
        action_column.addStretch()
        layout.addLayout(action_column)

    @staticmethod
    def _make_icon_button(object_name: str) -> QPushButton:
        button = CircleButton(ACTION_ICON_SIZE + 12)
        button.setObjectName(object_name)
        return button

    def _build_icon(self) -> QLabel:
        """Green-outlined box; filled with the app's icon only when one is provided."""
        box = QLabel()
        box.setObjectName("appIconBox")
        box.setFixedSize(ICON_BOX_SIZE, ICON_BOX_SIZE)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_path_value = (self._app_meta.get("icon_path") or "").strip()
        if icon_path_value and self._app_dir is not None:
            resolved = self._app_dir / icon_path_value
            if resolved.is_file():
                pixmap = QPixmap(str(resolved))
                if not pixmap.isNull():
                    inner = ICON_BOX_SIZE - 12
                    box.setPixmap(
                        pixmap.scaled(
                            inner,
                            inner,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
        return box

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def update_state(self):
        """Refresh the badge and state icon to reflect current AppHealth state."""
        self._update_state_badge()
        self._refresh_update_button()

    def set_backend_checked(self, checked: bool = True) -> None:
        """Called once this app's backend is verified."""
        self._backend_checked = checked
        self._update_state_badge()

    def set_update_status(
        self,
        *,
        update_available: bool,
        available_version: Optional[str] = None,
        checking_updates: bool = False,
    ) -> None:
        self._update_available = update_available
        self._available_version = available_version
        self._checking_updates = checking_updates
        self._refresh_update_button()

    def _update_state_badge(self):
        state = self._health.state
        text = {
            AppState.ERROR: "error",
            AppState.CRASHED: "crashed",
            AppState.DISABLED: "disabled",
        }.get(state, "")
        self._badge_label.setText(text)
        self._badge_label.setVisible(self._show_state_badge and bool(text))

        if state == AppState.ERROR and self._health.last_error:
            self._badge_label.setToolTip(
                f"Errors: {self._health.consecutive_errors}\n"
                f"Last: {self._health.last_error[:200]}"
            )

        self._run_button.setEnabled(
            self._action_enabled
            if self._action_enabled is not None
            else state in (AppState.DISCOVERED, AppState.READY, AppState.ERROR)
        )
        self._refresh_action()

    def _refresh_update_button(self) -> None:
        self._refresh_action()
        if self._available_version:
            self._update_button.setToolTip(f"Update to {self._available_version}")
        else:
            self._update_button.setToolTip("")

    def _refresh_action(self) -> None:
        """Pick which state icon occupies the right-hand slot."""
        state = self._health.state
        crashed = state == AppState.CRASHED
        busy = state in (AppState.RUNNING, AppState.INSTALLING, AppState.LOADING)
        show_update = (
            self._update_available
            and not self._checking_updates
            and not crashed
            and not busy
        )

        self._reset_button.setVisible(crashed)
        self._update_button.setVisible(show_update)
        self._update_button.setEnabled(show_update)
        self._run_button.setVisible(not crashed and not show_update)

        if crashed:
            caption = ""
        elif show_update:
            caption = "update"
        elif state == AppState.RUNNING:
            self._run_button.setIcon(assets.icon("running_tool", ACTION_ICON_SIZE))
            caption = "running..."
        elif state == AppState.LOADING:
            self._run_button.setIcon(assets.icon("running_tool", ACTION_ICON_SIZE))
            caption = "loading..."
        elif state == AppState.INSTALLING:
            self._run_button.setIcon(assets.icon("installing_tool", ACTION_ICON_SIZE))
            caption = "installing..."
        elif self._primary_action == "Install":
            self._run_button.setIcon(assets.icon("installing_tool", ACTION_ICON_SIZE))
            caption = "install"
        else:
            self._run_button.setIcon(assets.icon("open_tool", ACTION_ICON_SIZE))
            caption = (
                "open tool"
                if self._primary_action == "Open"
                else self._primary_action.lower()
            )
        self._action_caption.setText(caption)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def mouseReleaseEvent(self, event):
        """Open app when the card background is clicked.

        Keeps button clicks working normally by ignoring clicks that originate
        from a QPushButton child.
        """
        if self._open_on_card_click and event.button() == Qt.MouseButton.LeftButton:
            click_pos = (
                event.pos() if hasattr(event, "pos") else event.position().toPoint()
            )
            child = self.childAt(click_pos)
            if not isinstance(child, QPushButton) and self._run_button.isEnabled():
                self.run_clicked.emit(self.app_id)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """Show a right-click context menu with app management actions."""
        if not self._show_context_menu:
            event.ignore()
            return
        menu = QMenu(self)

        open_action = QAction("Open", self)
        open_action.setEnabled(self._run_button.isEnabled())
        open_action.triggered.connect(lambda: self.run_clicked.emit(self.app_id))
        menu.addAction(open_action)

        menu.addSeparator()

        check_updates_action = QAction("Check for Updates", self)
        check_updates_action.setEnabled(not self._checking_updates)
        check_updates_action.triggered.connect(
            lambda: self.check_updates_clicked.emit(self.app_id)
        )
        menu.addAction(check_updates_action)

        if self._update_available:
            update_label = "Update App"
            if self._available_version:
                update_label = f"Update to {self._available_version}"
            update_action = QAction(update_label, self)
            update_action.triggered.connect(lambda: self.update_clicked.emit(self.app_id))
            menu.addAction(update_action)

        refresh_action = QAction("↺  Refresh App", self)
        refresh_action.setToolTip(
            "Wipe the cached environment and reinstall all dependencies,"
            " then reload the app."
        )
        refresh_action.triggered.connect(lambda: self.refresh_clicked.emit(self.app_id))
        menu.addAction(refresh_action)

        menu.exec(event.globalPos())
