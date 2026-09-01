from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from qgis.PyQt.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.app_registry import AppEntry, ToolboxEntry
from ..core.app_state import AppHealth
from ..core.marketplace import MarketplaceItem, scan_marketplace
from ..core.marketplace_cache import MarketplaceCache
from ..core.search import fuzzy_matches
from ..workers.download_worker import LocalInstallWorker
from ..workers.marketplace_scan_worker import MarketplaceScanWorker
from .app_card_widget import AppCardWidget
from .toolbox_card_widget import ToolboxCardWidget


class MarketplacePane(QWidget):
    """Dashboard page for browsing local app and toolbox directories."""

    back_requested = pyqtSignal()
    app_installed = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._apps_dir: Path | None = None
        self._directories: list[Path] = []
        self._items: list[MarketplaceItem] = []
        self._scan_times: dict[Path, datetime] = {}
        self._cache: MarketplaceCache | None = None
        self._stale_prompt_shown = False
        self._search_query = ""
        self._pending_search_query = ""
        self._installed_app_ids: set[str] = set()
        self._installed_toolbox_ids: set[str] = set()
        self._worker: LocalInstallWorker | None = None
        self._scan_worker: MarketplaceScanWorker | None = None
        self._results_transition: QPropertyAnimation | None = None
        self._search_timer = QTimer(self)
        self._search_timer.setInterval(250)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._apply_search_query)
        self._build_ui()

    def set_apps_dir(self, apps_dir: Path) -> None:
        self._apps_dir = apps_dir
        self._cache = MarketplaceCache(apps_dir)
        snapshot = self._cache.load()
        self._directories = snapshot.directories
        self._items = snapshot.items
        self._scan_times = snapshot.scanned_at
        self._directory_list.clear()
        self._directory_list.addItems([str(directory) for directory in self._directories])
        if self._items:
            self._render_items()
            self._status_label.setText("Showing cached marketplace listings.")

    def set_installed_items(
        self, app_ids: set[str], toolbox_ids: set[str]
    ) -> None:
        """Update installed status without reading or preparing marketplace items."""
        self._installed_app_ids = set(app_ids)
        self._installed_toolbox_ids = set(toolbox_ids)
        if self._items:
            self._render_items()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        back_button = QToolButton()
        back_button.setArrowType(Qt.ArrowType.LeftArrow)
        back_button.setAutoRaise(True)
        back_button.setToolTip("Back to installed apps")
        back_button.clicked.connect(self.back_requested.emit)
        header.addWidget(back_button)
        header.addWidget(QLabel("Local Plugin Marketplace"))
        header.addStretch()
        self._search_input = QLineEdit()
        self._search_input.setObjectName("qgarageMarketplaceSearchBar")
        self._search_input.setPlaceholderText("Search marketplace")
        self._search_input.setMaximumWidth(180)
        self._search_input.textChanged.connect(self._queue_search_query)
        header.addWidget(self._search_input)
        layout.addLayout(header)

        layout.addWidget(QLabel("Folders to scan"))
        self._directory_list = QListWidget()
        self._directory_list.setMaximumHeight(88)
        layout.addWidget(self._directory_list)

        directory_buttons = QHBoxLayout()
        self._add_directory_button = QPushButton("Add Directory")
        self._add_directory_button.clicked.connect(self._add_directory)
        directory_buttons.addWidget(self._add_directory_button)
        self._remove_directory_button = QPushButton("Remove Selected")
        self._remove_directory_button.clicked.connect(self._remove_selected_directory)
        directory_buttons.addWidget(self._remove_directory_button)
        self._scan_button = QPushButton("Scan")
        self._scan_button.clicked.connect(self._scan)
        directory_buttons.addWidget(self._scan_button)
        directory_buttons.addStretch()
        layout.addLayout(directory_buttons)

        self._scan_progress = QProgressBar()
        self._scan_progress.setRange(0, 0)
        self._scan_progress.setVisible(False)
        layout.addWidget(self._scan_progress)

        self._rescan_prompt = QFrame()
        self._rescan_prompt.setObjectName("marketplaceRescanPrompt")
        rescan_layout = QHBoxLayout(self._rescan_prompt)
        rescan_layout.setContentsMargins(8, 6, 8, 6)
        rescan_layout.addWidget(
            QLabel("Cached marketplace listings may be out of date.")
        )
        self._rescan_button = QPushButton("Rescan")
        self._rescan_button.clicked.connect(self._scan)
        rescan_layout.addWidget(self._rescan_button)
        rescan_layout.addStretch()
        self._rescan_prompt.setVisible(False)
        layout.addWidget(self._rescan_prompt)

        self._results_scroll = QScrollArea()
        self._results_scroll.setWidgetResizable(True)
        self._results_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._results = QWidget()
        self._results_layout = QVBoxLayout(self._results)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(8)
        self._results_layout.addStretch()
        self._results_scroll.setWidget(self._results)
        layout.addWidget(self._results_scroll, stretch=1)

        self._status_label = QLabel(
            "Add a folder containing apps or toolboxes, then select Scan."
        )
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

    def _add_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Select Marketplace Directory", ""
        )
        if not selected:
            return
        directory = Path(selected)
        if directory not in self._directories:
            self._directories.append(directory)
            self._directory_list.addItem(str(directory))
            self._stale_prompt_shown = False
            self._persist_cache()

    def _remove_selected_directory(self) -> None:
        row = self._directory_list.currentRow()
        if row >= 0:
            directory = self._directories.pop(row)
            self._scan_times.pop(directory, None)
            self._items = [
                item
                for item in self._items
                if any(
                    item.source_dir.is_relative_to(configured_directory)
                    for configured_directory in self._directories
                )
            ]
            self._directory_list.takeItem(row)
            self._render_items()
            self._persist_cache()

    def _scan(self) -> None:
        if self._scan_worker is not None:
            return
        if not self._directories:
            self._items = []
            self._render_items()
            self._status_label.setText(
                "Add a folder containing apps or toolboxes, then select Scan."
            )
            return

        self._set_scanning(True)
        worker = MarketplaceScanWorker(self._directories, self)
        worker.scan_finished.connect(self._on_scan_finished)
        worker.finished.connect(worker.deleteLater)
        self._scan_worker = worker
        worker.start()

    def _on_scan_finished(self, items: list, error_text: str) -> None:
        self._scan_worker = None
        self._set_scanning(False)
        if error_text:
            self._status_label.setText(error_text)
            return
        self._items = items
        scan_time = datetime.now(timezone.utc)
        self._scan_times = {
            directory: scan_time for directory in self._directories
        }
        self._stale_prompt_shown = True
        self._rescan_prompt.setVisible(False)
        self._persist_cache()
        self._render_items()
        self._status_label.setText(
            "No installable apps or toolboxes were found."
            if not self._items
            else f"Found {len(self._items)} item"
            + ("." if len(self._items) == 1 else "s.")
        )

    def _set_scanning(self, scanning: bool) -> None:
        self._add_directory_button.setEnabled(not scanning)
        self._remove_directory_button.setEnabled(not scanning)
        self._scan_button.setEnabled(not scanning)
        self._scan_progress.setVisible(scanning)
        self._rescan_button.setEnabled(not scanning)
        self._status_label.setText("Scanning marketplace directories..." if scanning else "")

    def _render_items(self) -> None:
        self._clear_results()
        matching_items = [item for item in self._items if self._matches_search(item)]
        grouped_items = [
            item
            for item in matching_items
            if not item.is_toolbox and item.parent_toolbox_id
        ]
        toolbox_items = [
            item
            for item in self._items
            if item.is_toolbox
            and (
                item in matching_items
                or any(child.parent_toolbox_id == item.item_id for child in grouped_items)
            )
        ]
        standalone_items = [
            item
            for item in matching_items
            if not item.is_toolbox and not item.parent_toolbox_id
        ]

        for toolbox in toolbox_items:
            tools = sorted(
                (item for item in grouped_items if item.parent_toolbox_id == toolbox.item_id),
                key=lambda item: (item.name.casefold(), item.item_id),
            )
            self._add_toolbox_card(toolbox, tools)

        if standalone_items:
            self._add_group_label("Standalone Apps")
        for item in standalone_items:
            self._add_card(item)
        self._fade_in_results()

    def _fade_in_results(self) -> None:
        effect = QGraphicsOpacityEffect(self._results)
        animation = QPropertyAnimation(effect, b"opacity")
        animation.setDuration(120)
        animation.setStartValue(0.35)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: self._results.setGraphicsEffect(None))
        self._results.setGraphicsEffect(effect)
        self._results_transition = animation
        animation.start()

    def _queue_search_query(self, query: str) -> None:
        self._pending_search_query = query
        self._search_timer.start()

    def _apply_search_query(self) -> None:
        self._search_query = self._pending_search_query.strip()
        if self._items:
            self._render_items()

    def _matches_search(self, item: MarketplaceItem) -> bool:
        if not self._search_query:
            return True
        tags = item.metadata.get("tags", [])
        searchable_values = [
            item.item_id,
            item.name,
            item.metadata.get("description", ""),
            item.parent_toolbox_name or "",
        ]
        if isinstance(tags, list):
            searchable_values.extend(tags)
        return fuzzy_matches(self._search_query, searchable_values)

    def _clear_results(self) -> None:
        while self._results_layout.count() > 1:
            layout_item = self._results_layout.takeAt(0)
            widget = layout_item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_card(self, item: MarketplaceItem) -> None:
        metadata = dict(item.metadata)
        description = str(metadata.get("description", ""))
        if item.parent_toolbox_name:
            description = f"{description}\nToolbox: {item.parent_toolbox_name}".strip()
        elif item.is_toolbox:
            description = f"{description}\nContains {item.app_count} app(s)".strip()
        metadata["description"] = description
        is_installed = (
            item.item_id in self._installed_toolbox_ids
            if item.is_toolbox
            else item.item_id in self._installed_app_ids
        )
        card = AppCardWidget(
            item.item_id,
            metadata,
            AppHealth(),
            app_dir=item.source_dir,
            primary_action="Installed" if is_installed else "Install",
            action_enabled=not is_installed,
            show_state_badge=False,
            open_on_card_click=False,
            show_context_menu=False,
        )
        card.run_clicked.connect(lambda: self._install(item))
        self._results_layout.insertWidget(self._results_layout.count() - 1, card)

    def _add_toolbox_card(
        self, toolbox_item: MarketplaceItem, tools: list[MarketplaceItem]
    ) -> None:
        toolbox_entry = ToolboxEntry(toolbox_item.source_dir, toolbox_item.metadata)
        tool_by_id = {}
        for tool in tools:
            toolbox_entry.app_entries[tool.item_id] = AppEntry(
                tool.source_dir, tool.metadata, parent_toolbox_id=toolbox_item.item_id
            )
            tool_by_id[tool.item_id] = tool

        toolbox_installed = toolbox_item.item_id in self._installed_toolbox_ids
        card = ToolboxCardWidget(
            toolbox_entry,
            primary_action="Install",
            action_enabled=True,
            show_state_badge=False,
            open_on_card_click=False,
            show_context_menu=False,
            toolbox_primary_action="Installed" if toolbox_installed else "Install",
            toolbox_action_enabled=not toolbox_installed,
            installed_app_ids=self._installed_app_ids,
        )
        card.toolbox_primary_clicked.connect(
            lambda _toolbox_id, item=toolbox_item: self._install(item)
        )
        card.app_run_clicked.connect(
            lambda app_id, items=tool_by_id: self._install(items[app_id])
        )
        self._results_layout.insertWidget(self._results_layout.count() - 1, card)

    def _install(self, item: MarketplaceItem) -> None:
        if self._apps_dir is None or self._worker is not None:
            return
        self._worker = LocalInstallWorker(item.source_dir, self._apps_dir, self)
        self._worker.progress.connect(self._on_install_progress)
        self._worker.finished.connect(self._on_install_finished)
        self._worker.start()
        self._scan_button.setEnabled(False)
        self._status_label.setText(f"Installing {item.name}...")

    def _on_install_progress(self, _percentage: int, message: str) -> None:
        self._status_label.setText(message)

    def _on_install_finished(self, success: bool, result: str, is_toolbox: bool) -> None:
        self._worker = None
        self._scan_button.setEnabled(True)
        self._status_label.setText(
            f"Installed '{result}'." if success else f"Installation failed: {result}"
        )
        if success:
            self.app_installed.emit(result, is_toolbox)

    def stop_scan(self) -> None:
        """Stop an active scan before the dashboard is destroyed."""
        if self._scan_worker is None:
            return
        self._scan_worker.requestInterruption()
        self._scan_worker.wait()
        self._scan_worker = None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._stale_prompt_shown or self._cache is None or not self._directories:
            return
        unscanned_directories = [
            directory
            for directory in self._directories
            if directory not in self._scan_times
        ]
        if unscanned_directories:
            self._stale_prompt_shown = True
            QTimer.singleShot(0, self._scan)
            return
        self._stale_prompt_shown = True
        if any(
            self._cache.is_stale(self._scan_times[directory])
            for directory in self._directories
        ):
            self._rescan_prompt.setVisible(True)

    def _persist_cache(self) -> None:
        if self._cache is not None:
            self._cache.save(self._directories, self._items, self._scan_times)