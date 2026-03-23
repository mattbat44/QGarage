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

logger = logging.getLogger("qhub.dashboard")


class DashboardDock(QgsDockWidget):
    """Main QHub dashboard dock widget.

    Two views managed by a QStackedWidget:
      0 = card grid (app listing)
      1 = app host (runs a single app's UI)
    """

    install_requested = pyqtSignal()
    new_app_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self, iface: QgisInterface, parent=None):
        super().__init__("QHub", parent or iface.mainWindow())
        self.iface = iface
        self.setObjectName("qhubDashboard")
        self._registry: Optional[AppRegistry] = None
        self._cards: dict[str, AppCardWidget] = {}

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
        self._toolbar.setObjectName("qhubToolbar")
        toolbar_layout = QHBoxLayout(self._toolbar)
        toolbar_layout.setContentsMargins(8, 8, 8, 8)
        toolbar_layout.setSpacing(6)

        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("qhubSearchBar")
        self.search_bar.setPlaceholderText("Search apps...")
        self.search_bar.textChanged.connect(self._filter_cards)
        toolbar_layout.addWidget(self.search_bar, stretch=1)

        self.install_button = QPushButton("+  Install")
        self.install_button.setObjectName("qhubInstallButton")
        self.install_button.setToolTip("Install an app from a URL or local folder")
        self.install_button.clicked.connect(self.install_requested.emit)
        toolbar_layout.addWidget(self.install_button)

        self.new_app_button = QPushButton("New App")
        self.new_app_button.setObjectName("qhubNewAppButton")
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
        self.scroll_area.setObjectName("qhubCardArea")
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

        entries = self._registry.entries
        self._empty_label.setVisible(len(entries) == 0)

        for app_id, entry in entries.items():
            card = AppCardWidget(app_id, entry.app_meta, entry.health)
            card.run_clicked.connect(self._on_app_run)
            card.reset_clicked.connect(self._on_app_reset)
            self._cards[app_id] = card
            # Insert before the stretch
            self.card_layout.insertWidget(self.card_layout.count() - 1, card)

    def add_card(self, entry: AppEntry):
        """Add a single card (used after installing a new app)."""
        self._empty_label.setVisible(False)
        card = AppCardWidget(entry.app_id, entry.app_meta, entry.health)
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

    # --- Navigation ---

    def _show_cards(self):
        self._app_host.clear()
        self._toolbar.setVisible(True)
        self._stack.setCurrentIndex(0)

    def _show_app(self, app_id: str):
        if self._registry is None:
            return
        entry = self._registry.entries.get(app_id)
        if entry is None or entry.instance is None:
            return
        self._toolbar.setVisible(False)
        self._app_host.show_app(entry.instance)
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
        entry.health.reset()
        self._registry.load_app(app_id)
        self.update_card_state(app_id)

    def _filter_cards(self, text: str):
        text_lower = text.lower()
        for app_id, card in self._cards.items():
            name = card._app_meta.get("name", "").lower()
            desc = card._app_meta.get("description", "").lower()
            tags = " ".join(card._app_meta.get("tags", [])).lower()
            visible = text_lower in name or text_lower in desc or text_lower in tags
            card.setVisible(visible)

    def showEvent(self, event):
        super().showEvent(event)
        ThemeManager.apply_to_widget(self)
