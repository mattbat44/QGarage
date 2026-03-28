import logging
from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ..workers.download_worker import DownloadAndInstallWorker, LocalInstallWorker

logger = logging.getLogger("qgarage.install_dialog")


class InstallDialog(QDialog):
    """Dialog for installing an app from a ZIP URL or local folder.

    Signals:
        app_installed(str): Emitted with app_id on successful install.
    """

    app_installed = pyqtSignal(str)

    def __init__(self, apps_dir: Path, parent=None):
        super().__init__(parent)
        self._apps_dir = apps_dir
        self._worker: Optional[DownloadAndInstallWorker | LocalInstallWorker] = None

        self.setWindowTitle("Install App")
        self.setMinimumWidth(450)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # URL input
        layout.addWidget(QLabel("Enter a URL to a .zip file:"))
        url_row = QHBoxLayout()
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("https://github.com/.../app.zip")
        url_row.addWidget(self._url_input, stretch=1)

        self._install_url_btn = QPushButton("Install from URL")
        self._install_url_btn.clicked.connect(self._start_url_install)
        url_row.addWidget(self._install_url_btn)
        layout.addLayout(url_row)

        # Separator
        layout.addWidget(QLabel("— or —"))

        # Local folder
        folder_row = QHBoxLayout()
        self._folder_label = QLabel("No folder selected")
        folder_row.addWidget(self._folder_label, stretch=1)

        self._browse_btn = QPushButton("Browse Local Folder")
        self._browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(self._browse_btn)
        layout.addLayout(folder_row)

        self._install_local_btn = QPushButton("Install from Folder")
        self._install_local_btn.setEnabled(False)
        self._install_local_btn.clicked.connect(self._start_local_install)
        layout.addWidget(self._install_local_btn)

        # Progress
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        # Cancel
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._cancel_install)
        layout.addWidget(self._cancel_btn)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select App Folder", "")
        if folder:
            self._selected_folder = Path(folder)
            self._folder_label.setText(str(self._selected_folder))
            self._install_local_btn.setEnabled(True)
        else:
            self._selected_folder = None
            self._folder_label.setText("No folder selected")
            self._install_local_btn.setEnabled(False)

    def _start_url_install(self):
        url = self._url_input.text().strip()
        if not url:
            self._status_label.setText("Please enter a URL")
            return

        self._set_installing(True)
        self._worker = DownloadAndInstallWorker(
            url=url,
            apps_dir=self._apps_dir,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _start_local_install(self):
        if not hasattr(self, "_selected_folder") or self._selected_folder is None:
            return

        self._set_installing(True)
        self._worker = LocalInstallWorker(
            source_dir=self._selected_folder,
            apps_dir=self._apps_dir,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _cancel_install(self):
        if self._worker is not None and hasattr(self._worker, "cancel"):
            self._worker.cancel()

    def _set_installing(self, installing: bool):
        self._install_url_btn.setEnabled(not installing)
        self._install_local_btn.setEnabled(not installing)
        self._browse_btn.setEnabled(not installing)
        self._cancel_btn.setEnabled(installing)
        self._progress_bar.setVisible(installing)
        if installing:
            self._progress_bar.setValue(0)

    def _on_progress(self, pct: int, message: str):
        self._progress_bar.setValue(pct)
        self._status_label.setText(message)

    def _on_finished(self, success: bool, result: str):
        self._set_installing(False)
        self._worker = None
        if success:
            self._status_label.setText(f"Successfully installed '{result}'")
            self.app_installed.emit(result)
        else:
            self._status_label.setText(f"Failed: {result}")
