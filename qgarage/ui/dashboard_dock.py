import logging
from typing import Optional

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qgis.gui import QgsDockWidget, QgisInterface

from ..core.app_registry import AppEntry, AppRegistry
from ..themes.theme_manager import ThemeManager
from .app_card_widget import AppCardWidget
from .app_host_widget import AppHostWidget
from .toolbox_card_widget import ToolboxCardWidget

logger = logging.getLogger("qgarage.dashboard")


class DashboardDock(QgsDockWidget):
    """Main QGarage dashboard dock widget.

    Two views managed by a QStackedWidget:
      0 = card grid (app listing)
      1 = app host (runs a single app's UI)
    """

    install_requested = pyqtSignal()
    new_app_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self, iface: QgisInterface, parent=None):
        super().__init__("QGarage", parent or iface.mainWindow())
        self.iface = iface
        self.setObjectName("qgarageDashboard")
        self._registry: Optional[AppRegistry] = None
        self._cards: dict[str, AppCardWidget] = {}
        self._toolbox_cards: dict[str, ToolboxCardWidget] = {}
        self._current_app_id: Optional[str] = None  # Track currently running app

        self._build_ui()
        ThemeManager.apply_to_widget(self)

    def set_registry(self, registry: AppRegistry):
        """Set the app registry and populate the card grid."""
        self._registry = registry
        self.refresh_cards()

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

        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("qgarageSearchBar")
        self.search_bar.setPlaceholderText("Search apps...")
        self.search_bar.textChanged.connect(self._filter_cards)
        toolbar_layout.addWidget(self.search_bar, stretch=1)

        self.install_button = QPushButton("+  Install")
        self.install_button.setObjectName("qgarageInstallButton")
        self.install_button.setToolTip("Install an app from a URL or local folder")
        self.install_button.clicked.connect(self.install_requested.emit)
        toolbar_layout.addWidget(self.install_button)

        self.new_app_button = QPushButton("New App")
        self.new_app_button.setObjectName("qgarageNewAppButton")
        self.new_app_button.setToolTip("Generate a new app from template")
        self.new_app_button.clicked.connect(self.new_app_requested.emit)
        toolbar_layout.addWidget(self.new_app_button)

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

        main_layout.addWidget(self._stack, stretch=1)
        self.setWidget(container)

    # --- Card management ---

    def refresh_cards(self):
        """Rebuild card grid from the registry."""
        if self._registry is None:
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
                app_id, entry.app_meta, entry.health, app_dir=entry.app_dir
            )
            card.run_clicked.connect(self._on_app_run)
            card.reset_clicked.connect(self._on_app_reset)
            self._cards[app_id] = card
            # Insert before the stretch
            self.card_layout.insertWidget(self.card_layout.count() - 1, card)

    def add_card(self, entry: AppEntry):
        """Add a single card (used after installing a new app)."""
        self._empty_label.setVisible(False)
        card = AppCardWidget(
            entry.app_id, entry.app_meta, entry.health, app_dir=entry.app_dir
        )
        card.run_clicked.connect(self._on_app_run)
        card.reset_clicked.connect(self._on_app_reset)
        self._cards[entry.app_id] = card
        self.card_layout.insertWidget(self.card_layout.count() - 1, card)

    def remove_card(self, app_id: str):
        """Remove a card from the grid."""
        card = self._cards.pop(app_id, None)
        if card:
            self.card_layout.removeWidget(card)
            card.deleteLater()
        if not self._cards:
            self._empty_label.setVisible(True)

    def update_card_state(self, app_id: str):
        """Refresh a single card's badge."""
        card = self._cards.get(app_id)
        if card:
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

    def _show_cards(self):
        """Return to the cards view without clearing the running app."""
        # Don't clear the app - just hide it to preserve state
        self._toolbar.setVisible(True)
        self._stack.setCurrentIndex(0)

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
            self._stack.setCurrentIndex(1)
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

        self._stack.setCurrentIndex(1)

    # --- Slots ---

    def _on_app_run(self, app_id: str):
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

    def _filter_cards(self, text: str):
        text_lower = text.lower()

        # Filter standalone app cards
        for app_id, card in self._cards.items():
            name = card._app_meta.get("name", "").lower()
            desc = card._app_meta.get("description", "").lower()
            tags = " ".join(card._app_meta.get("tags", [])).lower()
            visible = text_lower in name or text_lower in desc or text_lower in tags
            card.setVisible(visible)

        # Filter toolbox cards
        for toolbox_id, toolbox_card in self._toolbox_cards.items():
            toolbox_meta = toolbox_card.toolbox_entry.toolbox_meta
            toolbox_name = toolbox_meta.get("name", "").lower()
            toolbox_desc = toolbox_meta.get("description", "").lower()
            toolbox_tags = " ".join(toolbox_meta.get("tags", [])).lower()

            # Check if toolbox itself matches
            toolbox_matches = (
                text_lower in toolbox_name or
                text_lower in toolbox_desc or
                text_lower in toolbox_tags
            )

            # Check if any app in the toolbox matches
            any_app_matches = False
            for app_entry in toolbox_card.toolbox_entry.app_entries.values():
                app_name = app_entry.app_meta.get("name", "").lower()
                app_desc = app_entry.app_meta.get("description", "").lower()
                app_tags = " ".join(app_entry.app_meta.get("tags", [])).lower()
                if (
                    text_lower in app_name or
                    text_lower in app_desc or
                    text_lower in app_tags
                ):
                    any_app_matches = True
                    break

            # Show toolbox if either toolbox or any of its apps matches
            toolbox_card.setVisible(toolbox_matches or any_app_matches)

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
