from qgis.PyQt.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..core.package_manager_install import SUPPORTED_PACKAGE_MANAGERS
from ..core.uv_bridge import UvBridge
from ..workers.package_manager_install_worker import PackageManagerInstallWorker
from ..core.logger import log_error
from ..core.settings import get_pixi_executable, get_uv_executable, set_setting


class SettingsDialog(QDialog):
    """QGarage preferences dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._install_worker = None
        self._missing_package_managers: list[str] = []
        self.setWindowTitle("QGarage Settings")
        self.setMinimumWidth(400)
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()

        self._uv_path_input = QLineEdit()
        self._uv_path_input.setPlaceholderText("uv")
        form.addRow("uv executable:", self._uv_path_input)

        self._pixi_path_input = QLineEdit()
        self._pixi_path_input.setPlaceholderText("pixi")
        form.addRow("pixi executable:", self._pixi_path_input)

        layout.addLayout(form)

        install_row = QHBoxLayout()
        self._install_hint_label = QLabel("")
        install_row.addWidget(self._install_hint_label, stretch=1)

        self._install_missing_btn = QPushButton("Install Missing")
        self._install_missing_btn.setVisible(False)
        self._install_missing_btn.clicked.connect(self._install_missing_package_managers)
        install_row.addWidget(self._install_missing_btn)
        layout.addLayout(install_row)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_settings)
        self._save_btn = save_btn
        layout.addWidget(save_btn)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

    def _load_settings(self):
        self._uv_path_input.setText(get_uv_executable())
        self._pixi_path_input.setText(get_pixi_executable())
        self._refresh_install_prompt()

    def _save_settings(self):
        uv_path = self._uv_path_input.text().strip()
        if uv_path:
            set_setting("uv_executable", uv_path)

        pixi_path = self._pixi_path_input.text().strip()
        if pixi_path:
            set_setting("pixi_executable", pixi_path)

        self._refresh_install_prompt()
        self._status_label.setText("Settings saved. Restart QGIS to apply changes.")

    def _refresh_install_prompt(self):
        missing = self._detect_missing_package_managers()
        self._missing_package_managers = missing
        self._install_missing_btn.setVisible(bool(missing))

        if missing:
            self._install_hint_label.setText(
                f"Missing package managers: {', '.join(missing)}"
            )
            return

        self._install_hint_label.setText("uv and pixi were detected.")

    def _detect_missing_package_managers(self) -> list[str]:
        missing: list[str] = []
        uv_path = self._uv_path_input.text().strip() or "uv"
        pixi_path = self._pixi_path_input.text().strip() or "pixi"

        try:
            UvBridge(uv_path)
        except RuntimeError:
            missing.append("uv")

        try:
            from ..core.pixi_bridge import PixiBridge

            PixiBridge(pixi_path)
        except RuntimeError:
            missing.append("pixi")

        return [
            manager for manager in SUPPORTED_PACKAGE_MANAGERS if manager in set(missing)
        ]

    def _install_missing_package_managers(self):
        if not self._missing_package_managers:
            return
        if self._install_worker is not None and self._install_worker.isRunning():
            return

        self._status_label.setText(
            f"Installing {', '.join(self._missing_package_managers)}..."
        )
        self._install_missing_btn.setEnabled(False)
        self._save_btn.setEnabled(False)

        worker = PackageManagerInstallWorker(self._missing_package_managers, parent=self)
        worker.install_finished.connect(self._on_install_finished)
        worker.finished.connect(worker.deleteLater)
        self._install_worker = worker
        worker.start()

    def _on_install_finished(self, success: bool, details: str):
        self._install_worker = None
        self._install_missing_btn.setEnabled(True)
        self._save_btn.setEnabled(True)

        if success:
            self._status_label.setText(
                "Installation complete. Restart QGIS to apply the new package manager executables."
            )
            QMessageBox.information(
                self,
                "Restart Required",
                "Package manager installation finished. Restart QGIS to load the new executables.",
            )
            return

        message = details or "The installer exited with an error."
        log_error(f"Settings dialog installer failed: {message}")
        self._status_label.setText(f"Installation failed: {message}")
        QMessageBox.critical(
            self,
            "Installation Failed",
            f"Could not install the missing package managers.\n\n{message}",
        )
