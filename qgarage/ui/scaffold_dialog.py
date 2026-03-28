import logging
import os
import re
from pathlib import Path

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

logger = logging.getLogger("qgarage.scaffold_dialog")

TEMPLATES_DIR = (
    Path(__file__).parent.parent / "resources" / "templates" / "app_template"
)


class ScaffoldDialog(QDialog):
    """Dialog to generate a new app from template.

    Signals:
        app_created(str): Emitted with app_id on successful creation.
    """

    app_created = pyqtSignal(str)

    def __init__(self, apps_dir: Path, parent=None):
        super().__init__(parent)
        self._apps_dir = apps_dir
        self.setWindowTitle("Generate New App")
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("My Cool Tool")
        self._name_input.textChanged.connect(self._auto_fill_id)
        form.addRow("App Name:", self._name_input)

        self._id_input = QLineEdit()
        self._id_input.setPlaceholderText("my_cool_tool")
        form.addRow("App ID:", self._id_input)

        self._author_input = QLineEdit()
        form.addRow("Author:", self._author_input)

        self._desc_input = QTextEdit()
        self._desc_input.setMaximumHeight(60)
        self._desc_input.setPlaceholderText("A short description of what this app does")
        form.addRow("Description:", self._desc_input)

        layout.addLayout(form)

        create_btn = QPushButton("Create App")
        create_btn.clicked.connect(self._create_app)
        layout.addWidget(create_btn)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

    def _auto_fill_id(self, name: str):
        """Auto-generate an ID from the name."""
        app_id = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
        self._id_input.setText(app_id)

    def _create_app(self):
        app_name = self._name_input.text().strip()
        app_id = self._id_input.text().strip()
        author = self._author_input.text().strip()
        description = self._desc_input.toPlainText().strip()

        if not app_name or not app_id:
            self._status_label.setText("App Name and App ID are required.")
            return

        if not re.match(r"^[a-z][a-z0-9_]*$", app_id):
            self._status_label.setText(
                "App ID must start with a letter and contain only lowercase letters, numbers, and underscores."
            )
            return

        dest_dir = self._apps_dir / app_id
        if dest_dir.exists():
            QMessageBox.warning(
                self,
                "App Exists",
                f"An app with ID '{app_id}' already exists.",
            )
            return

        # Generate class name from app_id
        class_name = "".join(word.capitalize() for word in app_id.split("_")) + "App"

        replacements = {
            "{{app_name}}": app_name,
            "{{app_id}}": app_id,
            "{{author}}": author,
            "{{description}}": description,
            "{{class_name}}": class_name,
        }

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)

            for tmpl_file in TEMPLATES_DIR.iterdir():
                if not tmpl_file.name.endswith(".tmpl"):
                    continue
                content = tmpl_file.read_text(encoding="utf-8")
                for key, value in replacements.items():
                    content = content.replace(key, value)

                output_name = tmpl_file.name.removesuffix(".tmpl")
                (dest_dir / output_name).write_text(content, encoding="utf-8")

            self._status_label.setText(f"Created app '{app_name}' at {dest_dir}")
            self.app_created.emit(app_id)

        except Exception as e:
            self._status_label.setText(f"Error: {e}")
            logger.exception(f"Failed to scaffold app '{app_id}'")
