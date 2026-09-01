from __future__ import annotations

import logging
from typing import Optional

from qgis.gui import QgisInterface, QgsDockWidget
from qgis.PyQt.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from ..core.app_registry import AppEntry, AppRegistry
from ..core.constants import PIXI_TOML_FILENAME
from ..core.search import fuzzy_matches
from ..themes.theme_manager import ThemeManager
from .app_card_widget import AppCardWidget
from .app_host_widget import AppHostWidget
from .marketplace_pane import MarketplacePane
from .status_bar_widget import StatusBarWidget
from .toolbox_card_widget import ToolboxCardWidget

logger = logging.getLogger("qgarage.dashboard")


class DashboardDock(QgsDockWidget):
    """Main QGarage dashboard dock widget.

    Three views managed by a QStackedWidget:
      0 = card grid (app listing)
      1 = app host (runs a single app's UI)
    """

    install_requested = pyqtSignal()
    marketplace_app_installed = pyqtSignal(str, bool)
    backend_ready = pyqtSignal(str)
    new_app_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    #: Emitted when the user right-clicks an app card and chooses "Refresh App".
    refresh_app_requested = pyqtSignal(str)
    check_updates_requested = pyqtSignal(str)
    update_app_requested = pyqtSignal(str)
    #: Emitted when the user clicks the global ↺ reload button.
    global_refresh_requested = pyqtSignal()
    #: Emitted when an unloaded app is opened and needs its environment prepared.
    app_prepare_requested = pyqtSignal(str)
    tool_install_confirmed = pyqtSignal(str)

    def __init__(self, iface: QgisInterface, parent=None):
        super().__init__("QGarage", parent or iface.mainWindow())
        self.iface = iface
        self.setObjectName("qgarageDashboard")
        self._registry: Optional[AppRegistry] = None
        self._cards: dict[str, AppCardWidget] = {}
        self._toolbox_cards: dict[str, ToolboxCardWidget] = {}
        self._current_app_id: Optional[str] = None  # Track currently running app
        self._page_transition: Optional[QPropertyAnimation] = None
        self._cards_transition: Optional[QPropertyAnimation] = None
        self._ready_backends: set[str] = set()
        self._app_search_timer = QTimer(self)
        self._app_search_timer.setInterval(250)
        self._app_search_timer.setSingleShot(True)
        self._app_search_timer.timeout.connect(self._apply_pending_card_filter)
        self.backend_ready.connect(self._on_backend_ready)

        self._build_ui()
        ThemeManager.apply_to_widget(self)

    @property
    def current_app_id(self) -> Optional[str]:
        """Return the currently hosted app id, or None when showing cards."""
        return self._current_app_id

    def close_current_app(self) -> None:
        """Close the currently hosted app and return to the cards view."""
        if self._current_app_id is None:
            return
        self._app_host.clear()
        self._current_app_id = None
        self._show_cards()

    def set_registry(self, registry: AppRegistry | None):
        """Set the app registry and populate the card grid."""
        self._registry = registry
        if registry is None:
            self._current_app_id = None
            self._app_host.clear()
            self.refresh_cards()
            self._refresh_marketplace_install_status()
            return
        self.refresh_cards()
        self._refresh_marketplace_install_status()

    def _build_ui(self):
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Toolbar ---
        self._toolbar = QWidget()
        self._toolbar.setObjectName("qgarageToolbar")
        toolbar_layout = QHBoxLayout(self._toolbar)
        toolbar_layout.setContentsMargins(8, 8, 8, 8)
        toolbar_layout.setSpacing(6)

        self.install_button = QPushButton("+  Install")
        self.install_button.setObjectName("qgarageInstallButton")
        self.install_button.setToolTip("Install an app from a URL or local folder")
        self.install_button.clicked.connect(self.install_requested.emit)
        toolbar_layout.addWidget(self.install_button)

        self.marketplace_button = QPushButton("Marketplace")
        self.marketplace_button.setObjectName("qgarageMarketplaceButton")
        self.marketplace_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        )
        self.marketplace_button.setToolTip(
            "Browse apps and toolboxes from local directories before installing"
        )
        self.marketplace_button.clicked.connect(self._show_marketplace)
        toolbar_layout.addWidget(self.marketplace_button)

        self.new_app_button = QPushButton("New App")
        self.new_app_button.setObjectName("qgarageNewAppButton")
        self.new_app_button.setToolTip("Generate a new app from template")
        self.new_app_button.clicked.connect(self.new_app_requested.emit)
        toolbar_layout.addWidget(self.new_app_button)

        self._app_search = QLineEdit()
        self._app_search.setObjectName("qgarageSearchBar")
        self._app_search.setPlaceholderText("Search apps")
        self._app_search.setMaximumWidth(180)
        self._app_search.textChanged.connect(self._queue_card_filter)
        toolbar_layout.addWidget(self._app_search)

        toolbar_layout.addStretch()

        self.reload_button = QPushButton("↺")
        self.reload_button.setObjectName("qgarageReloadButton")
        self.reload_button.setToolTip(
            "Reload QGarage — equivalent to the Plugin Reloader.\n"
            "Re-imports all modules, rediscovers apps, and resets all state."
        )
        self.reload_button.setFixedWidth(28)
        self.reload_button.clicked.connect(self.global_refresh_requested.emit)
        toolbar_layout.addWidget(self.reload_button)

        main_layout.addWidget(self._toolbar)

        # --- Stacked widget: cards view + app host view ---
        self._stack = QStackedWidget()

        # Page 0: Card grid
        self._cards_page = QWidget()
        cards_page_layout = QVBoxLayout(self._cards_page)
        cards_page_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("qgarageCardArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.card_container = QWidget()
        self.card_layout = QVBoxLayout(self.card_container)
        self.card_layout.setContentsMargins(8, 8, 8, 8)
        self.card_layout.setSpacing(8)

        self._tool_install_prompt = QFrame()
        self._tool_install_prompt.setObjectName("qgarageToolInstallPrompt")
        prompt_layout = QVBoxLayout(self._tool_install_prompt)
        prompt_layout.setContentsMargins(10, 10, 10, 10)
        prompt_layout.setSpacing(6)
        self._tool_install_title = QLabel()
        self._tool_install_title.setObjectName("qgarageToolInstallTitle")
        prompt_layout.addWidget(self._tool_install_title)
        self._tool_install_detail = QLabel()
        self._tool_install_detail.setWordWrap(True)
        self._tool_install_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        prompt_layout.addWidget(self._tool_install_detail)
        prompt_buttons = QHBoxLayout()
        self._tool_install_button = QPushButton("Install")
        self._tool_install_button.clicked.connect(self._confirm_tool_install)
        prompt_buttons.addWidget(self._tool_install_button)
        self._tool_install_cancel_button = QPushButton("Cancel")
        self._tool_install_cancel_button.clicked.connect(self._tool_install_prompt.hide)
        prompt_buttons.addWidget(self._tool_install_cancel_button)
        prompt_buttons.addStretch()
        prompt_layout.addLayout(prompt_buttons)
        self._tool_install_prompt.setVisible(False)
        self.card_layout.addWidget(self._tool_install_prompt)

        self._empty_label = QLabel(
            "No apps installed.\nClick '+  Install' to get started."
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self.card_layout.addWidget(self._empty_label)
        self.card_layout.addStretch()

        self.scroll_area.setWidget(self.card_container)
        cards_page_layout.addWidget(self.scroll_area)
        self._stack.addWidget(self._cards_page)

        # Page 1: App host
        self._app_host = AppHostWidget()
        self._app_host.back_requested.connect(self._show_cards)
        self._stack.addWidget(self._app_host)

        # Page 2: local plugin marketplace
        self._marketplace = MarketplacePane()
        self._marketplace.back_requested.connect(self._show_cards)
        self._marketplace.app_installed.connect(self.marketplace_app_installed.emit)
        self._stack.addWidget(self._marketplace)

        main_layout.addWidget(self._stack, stretch=1)

        # --- Bottom status bar: uv / pixi indicators ---
        self.status_bar = StatusBarWidget()
        self.status_bar.setObjectName("qgarageStatusBar")
        main_layout.addWidget(self.status_bar)

        self.setWidget(container)

    # --- Card management ---

    def refresh_cards(self):
        """Rebuild card grid from the registry."""
        if self._registry is None:
            for card in self._cards.values():
                self.card_layout.removeWidget(card)
                card.deleteLater()
            self._cards.clear()
            for toolbox_card in self._toolbox_cards.values():
                self.card_layout.removeWidget(toolbox_card)
                toolbox_card.deleteLater()
            self._toolbox_cards.clear()
            self._empty_label.setVisible(True)
            self._refresh_marketplace_install_status()
            return

        # Clear existing cards
        for card in self._cards.values():
            self.card_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        for toolbox_card in self._toolbox_cards.values():
            self.card_layout.removeWidget(toolbox_card)
            toolbox_card.deleteLater()
        self._toolbox_cards.clear()

        # Add toolboxes first
        toolbox_entries = self._registry.toolbox_entries
        for toolbox_id, toolbox_entry in toolbox_entries.items():
            toolbox_card = ToolboxCardWidget(toolbox_entry)
            toolbox_card.app_run_clicked.connect(self._on_app_run)
            toolbox_card.app_reset_clicked.connect(self._on_app_reset)
            toolbox_card.app_refresh_clicked.connect(self.refresh_app_requested.emit)
            toolbox_card.app_check_updates_clicked.connect(
                self.check_updates_requested.emit
            )
            toolbox_card.app_update_clicked.connect(self.update_app_requested.emit)
            self._toolbox_cards[toolbox_id] = toolbox_card
            # Insert before the stretch
            self.card_layout.insertWidget(self.card_layout.count() - 1, toolbox_card)

        # Add standalone apps (those not in toolboxes)
        entries = self._registry.entries
        total_count = len(toolbox_entries) + sum(
            1 for e in entries.values() if e.parent_toolbox_id is None
        )
        self._empty_label.setVisible(total_count == 0)

        for app_id, entry in entries.items():
            # Skip apps that are in toolboxes (they're displayed inside toolbox cards)
            if entry.parent_toolbox_id is not None:
                continue

            card = AppCardWidget(
                app_id,
                entry.app_meta,
                entry.health,
                app_dir=entry.app_dir,
                update_available=entry.update_available,
                available_version=entry.available_version,
                checking_updates=entry.checking_updates,
            )
            card.run_clicked.connect(self._on_app_run)
            card.reset_clicked.connect(self._on_app_reset)
            card.refresh_clicked.connect(self.refresh_app_requested.emit)
            card.check_updates_clicked.connect(self.check_updates_requested.emit)
            card.update_clicked.connect(self.update_app_requested.emit)
            self._cards[app_id] = card
            # Insert before the stretch
            self.card_layout.insertWidget(self.card_layout.count() - 1, card)

        self._refresh_marketplace_install_status()
        self._apply_card_filter(self._app_search.text())
        self._sync_backend_check_indicators()
        self._fade_in_widget(self.card_container, "_cards_transition")

    def add_card(self, entry: AppEntry):
        """Add a single card (used after installing a new app)."""
        self._empty_label.setVisible(False)
        card = AppCardWidget(
            entry.app_id,
            entry.app_meta,
            entry.health,
            app_dir=entry.app_dir,
            update_available=entry.update_available,
            available_version=entry.available_version,
            checking_updates=entry.checking_updates,
        )
        card.run_clicked.connect(self._on_app_run)
        card.reset_clicked.connect(self._on_app_reset)
        card.refresh_clicked.connect(self.refresh_app_requested.emit)
        card.check_updates_clicked.connect(self.check_updates_requested.emit)
        card.update_clicked.connect(self.update_app_requested.emit)
        self._cards[entry.app_id] = card
        self.card_layout.insertWidget(self.card_layout.count() - 1, card)
        self._refresh_marketplace_install_status()
        self._sync_backend_check_indicators()
        self._fade_in_widget(self.card_container, "_cards_transition")

    def remove_card(self, app_id: str):
        """Remove a card from the grid."""
        if app_id == self._current_app_id:
            self._app_host.clear()
            self._current_app_id = None
            self._show_cards()

        card = self._cards.pop(app_id, None)
        if card:
            self.card_layout.removeWidget(card)
            card.deleteLater()
        if not self._cards and not self._toolbox_cards:
            self._empty_label.setVisible(True)
        self._refresh_marketplace_install_status()

    def update_card_state(self, app_id: str):
        """Refresh a single card's badge."""
        card = self._cards.get(app_id)
        if card:
            if self._registry is not None:
                entry = self._registry.entries.get(app_id)
                if entry is not None:
                    card.set_update_status(
                        update_available=entry.update_available,
                        available_version=entry.available_version,
                        checking_updates=entry.checking_updates,
                    )
            card.update_state()
            return

        # Check if the app is in a toolbox
        if self._registry:
            entry = self._registry.entries.get(app_id)
            if entry and entry.parent_toolbox_id:
                toolbox_card = self._toolbox_cards.get(entry.parent_toolbox_id)
                if toolbox_card:
                    toolbox_card.update_app_state(app_id)

    # --- Navigation ---

    def set_marketplace_apps_dir(self, apps_dir) -> None:
        """Set the managed destination used by marketplace installations."""
        self._marketplace.set_apps_dir(apps_dir)

    def stop_marketplace_scan(self) -> None:
        """Stop marketplace background work before the dock is destroyed."""
        self._marketplace.stop_scan()

    def _show_marketplace(self) -> None:
        self._refresh_marketplace_install_status()
        self._switch_page(self._marketplace)

    def _refresh_marketplace_install_status(self) -> None:
        if self._registry is None:
            self._marketplace.set_installed_items(set(), set())
            return
        self._marketplace.set_installed_items(
            set(self._registry.entries), set(self._registry.toolbox_entries)
        )

    def _on_backend_ready(self, tool: str) -> None:
        """Clear neutral Checking badges for apps whose backend is verified."""
        self._ready_backends.add(tool)
        self._sync_backend_check_indicators()

    def _sync_backend_check_indicators(self) -> None:
        if self._registry is None:
            return
        for app_id, entry in self._registry.entries.items():
            backend = "pixi" if (entry.app_dir / PIXI_TOML_FILENAME).exists() else "uv"
            if backend not in self._ready_backends:
                continue
            card = self._cards.get(app_id)
            if card is not None:
                card.set_backend_checked()
            if entry.parent_toolbox_id is not None:
                toolbox_card = self._toolbox_cards.get(entry.parent_toolbox_id)
                if toolbox_card is not None:
                    toolbox_card.set_app_backend_checked(app_id)

    def _show_cards(self):
        """Return to the cards view without clearing the running app."""
        # Don't clear the app - just hide it to preserve state
        self._toolbar.setVisible(True)
        self._switch_page(self._cards_page)

    def _switch_page(self, page: QWidget) -> None:
        """Fade between dashboard pages without changing their state."""
        current_page = self._stack.currentWidget()
        if current_page is page:
            return

        current_effect = QGraphicsOpacityEffect(current_page)
        fade_out = QPropertyAnimation(current_effect, b"opacity")
        fade_out.setDuration(90)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.OutCubic)

        def show_destination() -> None:
            current_page.setGraphicsEffect(None)
            self._stack.setCurrentWidget(page)
            destination_effect = QGraphicsOpacityEffect(page)
            fade_in = QPropertyAnimation(destination_effect, b"opacity")
            fade_in.setDuration(140)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.Type.InOutCubic)
            fade_in.finished.connect(lambda: page.setGraphicsEffect(None))
            self._page_transition = fade_in
            fade_in.start()

        current_page.setGraphicsEffect(current_effect)
        fade_out.finished.connect(show_destination)
        self._page_transition = fade_out
        fade_out.start()

    def _fade_in_widget(self, widget: QWidget, animation_attribute: str) -> None:
        """Apply a short fade-in after a card surface changes."""
        effect = QGraphicsOpacityEffect(widget)
        animation = QPropertyAnimation(effect, b"opacity")
        animation.setDuration(120)
        animation.setStartValue(0.35)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: widget.setGraphicsEffect(None))
        widget.setGraphicsEffect(effect)
        setattr(self, animation_attribute, animation)
        animation.start()

    def _show_app(self, app_id: str):
        """Show an app in the host widget, reusing existing widget if already running."""
        if self._registry is None:
            return
        entry = self._registry.entries.get(app_id)
        if entry is None or entry.instance is None:
            return

        # Check if this app is already open with a widget
        if app_id == self._current_app_id and self._app_host.has_app():
            # App UI is already open, just switch to it
            self._toolbar.setVisible(False)
            self._switch_page(self._app_host)
            return

        # If switching to a different app, clear the previous one
        if self._current_app_id and self._current_app_id != app_id:
            self._app_host.clear()

        self._current_app_id = app_id
        self._toolbar.setVisible(False)
        try:
            self._app_host.show_app(entry.instance)
        except Exception:
            logger.exception("Failed to build UI for app '%s'", app_id)
            from ..core.app_state import AppState

            entry.health.state = AppState.ERROR
            self._current_app_id = None
            self._show_cards()  # restore toolbar + card grid
            return

        self._switch_page(self._app_host)

    def open_app(self, app_id: str) -> None:
        """Open an app whose environment and instance are ready."""
        self._show_app(app_id)

    def prompt_tool_install(self, tool: str, command: str) -> None:
        """Show a visible, dashboard-owned consent prompt for a backend."""
        self._pending_tool_install = tool
        self._tool_install_messages = []
        self._tool_install_title.setText(f"{tool} is required to open this app")
        self._tool_install_detail.setText(
            "QGarage will run this official installer command:\n\n" + command
        )
        self._tool_install_button.setText(f"Install {tool}")
        self._tool_install_button.setEnabled(True)
        self._tool_install_cancel_button.setEnabled(True)
        self._tool_install_prompt.setVisible(True)

    def set_tool_install_status(self, message: str, *, running: bool = False) -> None:
        """Display installer progress in the dashboard prompt."""
        if running:
            messages = getattr(self, "_tool_install_messages", [])
            messages.append(message)
            self._tool_install_messages = messages[-100:]
            message = "\n".join(self._tool_install_messages)
        self._tool_install_detail.setText(message)
        self._tool_install_button.setEnabled(not running)
        self._tool_install_cancel_button.setEnabled(not running)
        self._tool_install_prompt.setVisible(True)

    def _confirm_tool_install(self) -> None:
        tool = getattr(self, "_pending_tool_install", None)
        if tool:
            self.tool_install_confirmed.emit(tool)

    # --- Slots ---

    def _on_app_run(self, app_id: str):
        if self._registry is None:
            return
        entry = self._registry.entries.get(app_id)
        if entry is not None and entry.instance is None:
            self.app_prepare_requested.emit(app_id)
            return
        self._show_app(app_id)

    def _on_app_reset(self, app_id: str):
        if self._registry is None:
            return
        entry = self._registry.entries.get(app_id)
        if entry is None:
            return

        # If this is the currently running app, clear it
        if app_id == self._current_app_id:
            self._app_host.clear()
            self._current_app_id = None

        entry.health.reset()
        self._registry.load_app(app_id)
        self.update_card_state(app_id)

    def showEvent(self, event):
        super().showEvent(event)
        ThemeManager.apply_to_widget(self)
        # Refresh all card states when dashboard becomes visible
        self._refresh_all_card_states()

    def _refresh_all_card_states(self):
        """Update all app card states to reflect current health."""
        for app_id in self._cards:
            self.update_card_state(app_id)
        for toolbox_card in self._toolbox_cards.values():
            for app_id in toolbox_card.toolbox_entry.app_entries:
                toolbox_card.update_app_state(app_id)

    def _apply_card_filter(self, query: str) -> None:
        """Filter installed app and toolbox cards without changing their state."""
        if self._registry is None:
            return
        normalized_query = query.strip()
        for app_id, card in self._cards.items():
            entry = self._registry.entries.get(app_id)
            card.setVisible(
                entry is not None and self._entry_matches(entry.app_meta, normalized_query)
            )
        for toolbox_id, toolbox_card in self._toolbox_cards.items():
            toolbox_entry = self._registry.toolbox_entries.get(toolbox_id)
            if toolbox_entry is None:
                toolbox_card.setVisible(False)
                continue
            matches = self._entry_matches(toolbox_entry.toolbox_meta, normalized_query)
            matches = matches or any(
                self._entry_matches(entry.app_meta, normalized_query)
                for entry in toolbox_entry.app_entries.values()
            )
            toolbox_card.setVisible(matches)

    def _queue_card_filter(self, _query: str) -> None:
        self._app_search_timer.start()

    def _apply_pending_card_filter(self) -> None:
        self._apply_card_filter(self._app_search.text())

    @staticmethod
    def _entry_matches(metadata: dict, query: str) -> bool:
        if not query:
            return True
        tags = metadata.get("tags", [])
        searchable_values = [
            metadata.get("id", ""),
            metadata.get("name", ""),
            metadata.get("description", ""),
        ]
        if isinstance(tags, list):
            searchable_values.extend(tags)
        return fuzzy_matches(query, searchable_values)
