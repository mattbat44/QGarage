import logging
import re
from pathlib import Path

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QComboBox,
    QTextEdit,
    QVBoxLayout,
)

from ..core.constants import PIXI_TOML_FILENAME, REQUIREMENTS_FILENAME

logger = logging.getLogger("qgarage.scaffold_dialog")

TEMPLATES_DIR = (
    Path(__file__).parent.parent / "resources" / "templates" / "app_template"
)
BASE_TEMPLATE_NAMES = {"app_meta.json.tmpl", "main.py.tmpl"}
BACKEND_TEMPLATE_NAMES = {
    "uv": f"{REQUIREMENTS_FILENAME}.tmpl",
    "pixi": f"{PIXI_TOML_FILENAME}.tmpl",
}


def build_class_name(app_id: str) -> str:
    return "".join(word.capitalize() for word in app_id.split("_")) + "App"


def scaffold_app(
    destination_root: Path,
    app_id: str,
    replacements: dict[str, str],
    backend: str,
    templates_dir: Path = TEMPLATES_DIR,
) -> Path:
    template_name = BACKEND_TEMPLATE_NAMES.get(backend)
    if template_name is None:
        raise ValueError(f"Unsupported backend '{backend}'")

    dest_dir = destination_root / app_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    selected_templates = BASE_TEMPLATE_NAMES | {template_name}
    for template_name in selected_templates:
        tmpl_file = templates_dir / template_name
        content = tmpl_file.read_text(encoding="utf-8")
        for key, value in replacements.items():
            content = content.replace(key, value)

        output_name = tmpl_file.name.removesuffix(".tmpl")
        (dest_dir / output_name).write_text(content, encoding="utf-8")

    return dest_dir


class ScaffoldDialog(QDialog):
    """Dialog to generate a new app from template.

    Signals:
        app_created(str, bool): Emitted with app_id and whether the app was created in the managed apps directory.
    """

    app_created = pyqtSignal(str, bool)

    def __init__(self, apps_dir: Path, parent=None):
        super().__init__(parent)
        self._apps_dir = apps_dir
        self._destination_root = apps_dir
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

        self._backend_input = QComboBox()
        self._backend_input.addItem("uv", "uv")
        self._backend_input.addItem("pixi", "pixi")
        self._backend_input.setToolTip(
            "Choose uv for pure-Python dependencies or pixi for conda-forge environments."
        )
        form.addRow("Backend:", self._backend_input)

        destination_row = QHBoxLayout()
        self._destination_label = QLabel(str(self._destination_root))
        self._destination_label.setWordWrap(True)
        destination_row.addWidget(self._destination_label, stretch=1)

        browse_btn = QPushButton("Choose Folder")
        browse_btn.clicked.connect(self._browse_destination)
        destination_row.addWidget(browse_btn)
        form.addRow("Create In:", destination_row)

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

    def _browse_destination(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Parent Folder for New App",
            str(self._destination_root),
        )
        if folder:
            self._destination_root = Path(folder)
            self._destination_label.setText(str(self._destination_root))

    def _create_app(self):
        app_name = self._name_input.text().strip()
        app_id = self._id_input.text().strip()
        author = self._author_input.text().strip()
        description = self._desc_input.toPlainText().strip()
        backend = self._backend_input.currentData()

        if not app_name or not app_id:
            self._status_label.setText("App Name and App ID are required.")
            return

        if not re.match(r"^[a-z][a-z0-9_]*$", app_id):
            self._status_label.setText(
                "App ID must start with a letter and contain only lowercase letters, numbers, and underscores."
            )
            return

        dest_dir = self._destination_root / app_id
        if dest_dir.exists():
            QMessageBox.warning(
                self,
                "App Exists",
                f"An app with ID '{app_id}' already exists.",
            )
            return

        class_name = build_class_name(app_id)

        replacements = {
            "{{app_name}}": app_name,
            "{{app_id}}": app_id,
            "{{author}}": author,
            "{{description}}": description,
            "{{class_name}}": class_name,
        }

        try:
            scaffold_app(self._destination_root, app_id, replacements, backend)

            created_in_managed_dir = (
                self._destination_root.resolve() == self._apps_dir.resolve()
            )

            self._status_label.setText(f"Created app '{app_name}' at {dest_dir}")
            self.app_created.emit(app_id, created_in_managed_dir)

        except Exception as e:
            self._status_label.setText(f"Error: {e}")
            logger.exception(f"Failed to scaffold app '{app_id}'")
