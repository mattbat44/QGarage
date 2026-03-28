from qgis.PyQt.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..core.settings import get_setting, get_uv_executable, set_setting


class SettingsDialog(QDialog):
    """QGarage preferences dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
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

        layout.addLayout(form)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_settings)
        layout.addWidget(save_btn)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

    def _load_settings(self):
        self._uv_path_input.setText(get_uv_executable())

    def _save_settings(self):
        uv_path = self._uv_path_input.text().strip()
        if uv_path:
            set_setting("uv_executable", uv_path)
        self._status_label.setText("Settings saved. Restart QGIS to apply changes.")
