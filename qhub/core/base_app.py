from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional
import logging

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qgis.PyQt.QtCore import Qt
from qgis.gui import (
    QgsFieldComboBox,
    QgsFileWidget,
    QgsMapLayerComboBox,
    QgsProjectionSelectionWidget,
)
from qgis.core import QgsMapLayerProxyModel, QgsProject

logger = logging.getLogger("qhub.base_app")


class InputType(Enum):
    """Supported declarative input types for BaseApp."""

    STRING = auto()
    INTEGER = auto()
    FLOAT = auto()
    BOOLEAN = auto()
    CHOICE = auto()
    FILE_PATH = auto()
    FOLDER_PATH = auto()
    VECTOR_LAYER = auto()
    RASTER_LAYER = auto()
    ANY_LAYER = auto()
    FIELD = auto()
    CRS = auto()
    TEXT_AREA = auto()


@dataclass
class InputSpec:
    """Specification for a single UI input."""

    key: str
    label: str
    input_type: InputType
    default: Any = None
    tooltip: str = ""
    required: bool = True
    choices: list[str] = field(default_factory=list)
    min_value: float = 0
    max_value: float = 999999
    linked_layer_key: str = ""
    file_filter: str = "All Files (*.*)"
    group: str = ""


class BaseApp(ABC):
    """Abstract base class for all QHub apps.

    Subclasses declare inputs via add_input() in __init__,
    then implement execute_logic() for the business logic.

    Example::

        class MyApp(BaseApp):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.add_input("dem", "DEM Layer", InputType.RASTER_LAYER)
                self.add_input("threshold", "Threshold", InputType.FLOAT,
                               default=10.0, min_value=0, max_value=1000)

            def execute_logic(self, inputs):
                dem = inputs["dem"]
                return {"status": "success", "message": "Done"}
    """

    def __init__(self, app_meta: dict, app_dir: Path):
        self.app_meta = app_meta
        self.app_dir = app_dir
        self.app_id: str = app_meta["id"]
        self.app_name: str = app_meta["name"]
        self._input_specs: list[InputSpec] = []
        self._widget: Optional[QWidget] = None
        self._input_widgets: dict[str, QWidget] = {}
        self._output_area: Optional[QTextEdit] = None
        self._progress_bar: Optional[QProgressBar] = None
        self._run_button: Optional[QPushButton] = None

    # --- Declarative API ---

    def add_input(
        self,
        key: str,
        label: str,
        input_type: InputType,
        **kwargs,
    ) -> None:
        """Register a declarative input. Call this in __init__."""
        spec = InputSpec(key=key, label=label, input_type=input_type, **kwargs)
        self._input_specs.append(spec)

    # --- Abstract method ---

    @abstractmethod
    def execute_logic(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the app's core logic.

        Args:
            inputs: Dictionary mapping input keys to their current values.

        Returns:
            Dictionary with at least a 'status' key ('success' or 'error').
        """
        ...

    # --- Optional hooks ---

    def on_load(self) -> None:
        """Called after the app is loaded."""

    def on_unload(self) -> None:
        """Called before the app is removed."""

    def validate_inputs(self, inputs: dict[str, Any]) -> Optional[str]:
        """Optional validation. Return error message or None."""
        return None

    # --- Widget generation ---

    def build_widget(self) -> QWidget:
        """Generate the UI from declared InputSpecs.

        Called by the QHub dashboard, not by the app developer.
        """
        self._widget = QWidget()
        main_layout = QVBoxLayout(self._widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # Header
        header = QLabel(self.app_name)
        header.setObjectName("appHeader")
        main_layout.addWidget(header)

        if desc := self.app_meta.get("description"):
            desc_label = QLabel(desc)
            desc_label.setWordWrap(True)
            desc_label.setObjectName("appDescription")
            main_layout.addWidget(desc_label)

        # Build form from input specs
        current_group = ""
        form_layout = QFormLayout()

        for spec in self._input_specs:
            if spec.group and spec.group != current_group:
                if form_layout.rowCount() > 0:
                    main_layout.addLayout(form_layout)
                group_box = QGroupBox(spec.group)
                form_layout = QFormLayout()
                group_box.setLayout(form_layout)
                main_layout.addWidget(group_box)
                current_group = spec.group

            widget = self._create_widget_for_spec(spec)
            self._input_widgets[spec.key] = widget
            form_layout.addRow(spec.label + ":", widget)
            if spec.tooltip:
                widget.setToolTip(spec.tooltip)

        if form_layout.rowCount() > 0:
            main_layout.addLayout(form_layout)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        main_layout.addWidget(self._progress_bar)

        # Run button
        self._run_button = QPushButton("Run")
        self._run_button.setObjectName("appRunButton")
        self._run_button.clicked.connect(self._on_run_clicked)
        main_layout.addWidget(self._run_button)

        # Output area
        self._output_area = QTextEdit()
        self._output_area.setReadOnly(True)
        self._output_area.setMaximumHeight(150)
        self._output_area.setObjectName("appOutputArea")
        main_layout.addWidget(self._output_area)

        main_layout.addStretch()
        return self._widget

    def _create_widget_for_spec(self, spec: InputSpec) -> QWidget:
        """Create the appropriate widget for an InputSpec."""
        if spec.input_type == InputType.STRING:
            w = QLineEdit()
            if spec.default:
                w.setText(str(spec.default))
            return w

        if spec.input_type == InputType.INTEGER:
            w = QSpinBox()
            w.setMinimum(int(spec.min_value))
            w.setMaximum(int(spec.max_value))
            if spec.default is not None:
                w.setValue(int(spec.default))
            return w

        if spec.input_type == InputType.FLOAT:
            w = QDoubleSpinBox()
            w.setMinimum(spec.min_value)
            w.setMaximum(spec.max_value)
            w.setDecimals(4)
            if spec.default is not None:
                w.setValue(float(spec.default))
            return w

        if spec.input_type == InputType.BOOLEAN:
            w = QCheckBox()
            if spec.default:
                w.setChecked(bool(spec.default))
            return w

        if spec.input_type == InputType.CHOICE:
            w = QComboBox()
            w.addItems(spec.choices)
            if spec.default and spec.default in spec.choices:
                w.setCurrentText(spec.default)
            return w

        if spec.input_type == InputType.FILE_PATH:
            w = QgsFileWidget()
            w.setFilter(spec.file_filter)
            w.setStorageMode(QgsFileWidget.StorageMode.GetFile)
            return w

        if spec.input_type == InputType.FOLDER_PATH:
            w = QgsFileWidget()
            w.setStorageMode(QgsFileWidget.StorageMode.GetDirectory)
            return w

        if spec.input_type == InputType.VECTOR_LAYER:
            w = QgsMapLayerComboBox()
            w.setFilters(QgsMapLayerProxyModel.Filter.VectorLayer)
            return w

        if spec.input_type == InputType.RASTER_LAYER:
            w = QgsMapLayerComboBox()
            w.setFilters(QgsMapLayerProxyModel.Filter.RasterLayer)
            return w

        if spec.input_type == InputType.ANY_LAYER:
            w = QgsMapLayerComboBox()
            return w

        if spec.input_type == InputType.FIELD:
            w = QgsFieldComboBox()
            if spec.linked_layer_key and spec.linked_layer_key in self._input_widgets:
                layer_combo = self._input_widgets[spec.linked_layer_key]
                if isinstance(layer_combo, QgsMapLayerComboBox):
                    layer_combo.layerChanged.connect(w.setLayer)
                    if layer_combo.currentLayer():
                        w.setLayer(layer_combo.currentLayer())
            return w

        if spec.input_type == InputType.CRS:
            return QgsProjectionSelectionWidget()

        if spec.input_type == InputType.TEXT_AREA:
            w = QTextEdit()
            w.setMaximumHeight(100)
            if spec.default:
                w.setText(str(spec.default))
            return w

        return QLineEdit()

    def _collect_inputs(self) -> dict[str, Any]:
        """Read current values from all input widgets."""
        values: dict[str, Any] = {}
        for spec in self._input_specs:
            w = self._input_widgets.get(spec.key)
            if w is None:
                continue

            if spec.input_type == InputType.STRING:
                values[spec.key] = w.text()
            elif spec.input_type == InputType.INTEGER:
                values[spec.key] = w.value()
            elif spec.input_type == InputType.FLOAT:
                values[spec.key] = w.value()
            elif spec.input_type == InputType.BOOLEAN:
                values[spec.key] = w.isChecked()
            elif spec.input_type == InputType.CHOICE:
                values[spec.key] = w.currentText()
            elif spec.input_type in (InputType.FILE_PATH, InputType.FOLDER_PATH):
                values[spec.key] = w.filePath()
            elif spec.input_type in (
                InputType.VECTOR_LAYER,
                InputType.RASTER_LAYER,
                InputType.ANY_LAYER,
            ):
                values[spec.key] = w.currentLayer()
            elif spec.input_type == InputType.FIELD:
                values[spec.key] = w.currentField()
            elif spec.input_type == InputType.CRS:
                values[spec.key] = w.crs()
            elif spec.input_type == InputType.TEXT_AREA:
                values[spec.key] = w.toPlainText()

        return values

    def _on_run_clicked(self) -> None:
        """Collect inputs, validate, and call execute_logic()."""
        inputs = self._collect_inputs()

        for spec in self._input_specs:
            if spec.required and spec.key in inputs:
                val = inputs[spec.key]
                if val is None or val == "":
                    self._output_area.setText(f"Required input missing: {spec.label}")
                    return

        error = self.validate_inputs(inputs)
        if error:
            self._output_area.setText(f"Validation error: {error}")
            return

        self._run_button.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)

        try:
            result = self.execute_logic(inputs)
            status = result.get("status", "unknown")
            message = result.get("message", str(result))
            self._output_area.setText(f"[{status.upper()}] {message}")
        except Exception as e:
            self._output_area.setText(f"[ERROR] {type(e).__name__}: {e}")
            logger.exception(f"App '{self.app_id}' execute_logic raised an exception")
        finally:
            self._run_button.setEnabled(True)
            self._progress_bar.setVisible(False)

    # --- Utility methods for app developers ---

    def log(self, message: str) -> None:
        """Append a message to the output area."""
        if self._output_area:
            self._output_area.append(message)

    def set_progress(self, value: int, maximum: int = 100) -> None:
        """Update the progress bar."""
        if self._progress_bar:
            self._progress_bar.setRange(0, maximum)
            self._progress_bar.setValue(value)
            self._progress_bar.setVisible(True)

    def get_project(self) -> QgsProject:
        """Convenience accessor for the current QGIS project."""
        return QgsProject.instance()
