from abc import ABC
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
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.gui import (
    QgsFieldComboBox,
    QgsFileWidget,
    QgsMapLayerComboBox,
    QgsProjectionSelectionWidget,
)
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsMapLayerProxyModel,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)

from .settings import get_uv_executable, ParameterCache
from .subprocess_runner import ProcessMonitor, launch_isolated_app_run
from .uv_bridge import UvBridge

logger = logging.getLogger("qgarage.base_app")


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


class _LayerBridge(QObject):
    """Internal QObject that carries layer-add requests as Qt signals.

    This lets apps deliver output layers to the QGIS map canvas directly
    on the main thread — no subprocess round-trip needed.
    """

    layer_requested = pyqtSignal(dict)


class BaseApp(ABC):
    """Abstract base class for all QGarage apps.

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
        self._uv_bridge: Optional[UvBridge] = None
        self._monitor: Optional[ProcessMonitor] = None
        self._tmp_dir: Optional[Any] = None  # tempfile.TemporaryDirectory
        self._layer_bridge: Optional[_LayerBridge] = None
        self._param_cache = ParameterCache(self.app_id)
        self._history_btn: Optional[QToolButton] = None
        self._history_menu: Optional[QMenu] = None

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

    def execute_logic(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the app's core logic.

        Args:
            inputs: Dictionary mapping input keys to their current values.

        Returns:
            Dictionary with at least a 'status' key ('success' or 'error').

        Note:
            Must be overridden in *declarative mode* apps.  Not called by the
            framework when ``build_dynamic_widget()`` returns a widget.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement execute_logic() when using "
            "declarative mode, or build_dynamic_widget() for a custom UI."
        )

    # --- Optional hooks ---

    def on_load(self) -> None:
        """Called after the app is loaded."""

    def on_unload(self) -> None:
        """Called before the app is removed."""

    def validate_inputs(self, inputs: dict[str, Any]) -> Optional[str]:
        """Optional validation. Return error message or None."""
        return None

    # --- Widget generation ---

    def build_dynamic_widget(self) -> Optional[QWidget]:
        """Override to provide a fully custom Qt widget for this app.

        Return a :class:`QWidget` to opt into *dynamic mode* — the framework
        will host it directly inside a scroll area without generating any
        declarative form.  Return ``None`` (the default) to use the standard
        declarative form built from :meth:`add_input` calls.

        In dynamic mode you are responsible for all UI logic, including
        triggering your own business logic and wiring Qt signals.
        :meth:`execute_logic` is **not** called by the framework in dynamic
        mode.
        """
        return None

    def build_widget(self) -> QWidget:
        """Generate the UI for this app.

        If :meth:`build_dynamic_widget` returns a widget it is used directly
        (dynamic mode).  Otherwise the declarative form is generated from the
        :class:`InputSpec` list built by :meth:`add_input` calls.

        Called by the QGarage dashboard, not by the app developer.
        """
        dynamic = self.build_dynamic_widget()
        if dynamic is not None:
            self._widget = dynamic
            # Wire the layer bridge so add_output_layer() works from dynamic apps too
            self._layer_bridge = _LayerBridge()
            self._layer_bridge.layer_requested.connect(self._add_layer_to_project)
            return self._widget

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

        # Run button row with history recall
        run_row = QHBoxLayout()
        self._run_button = QPushButton("Run")
        self._run_button.setObjectName("appRunButton")
        self._run_button.clicked.connect(self._on_run_clicked)
        run_row.addWidget(self._run_button)

        self._history_menu = QMenu(self._widget)
        self._history_btn = QToolButton()
        self._history_btn.setIcon(
            QIcon.fromTheme("clock", QIcon(":/images/themes/default/mIconHistory.svg"))
        )
        self._history_btn.setToolTip("Recall parameters from a previous run")
        self._history_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._history_btn.setMenu(self._history_menu)
        self._history_btn.setObjectName("appHistoryButton")
        self._history_btn.setFixedSize(28, 28)
        self._populate_history_menu()
        run_row.addWidget(self._history_btn)

        main_layout.addLayout(run_row)

        # Output area
        self._output_area = QTextEdit()
        self._output_area.setReadOnly(True)
        self._output_area.setMaximumHeight(150)
        self._output_area.setObjectName("appOutputArea")
        main_layout.addWidget(self._output_area)

        main_layout.addStretch()

        # Wire layer signal so add_output_layer() works from any context
        self._layer_bridge = _LayerBridge(self._widget)
        self._layer_bridge.layer_requested.connect(self._add_layer_to_project)

        # Restore last-used parameters
        self._restore_params(self._param_cache.load_last())

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

    # --- Parameter caching helpers ---

    def _serialize_for_cache(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Convert collected inputs to a JSON-serialisable dict for caching."""
        out: dict[str, Any] = {}
        for spec in self._input_specs:
            val = inputs.get(spec.key)
            if val is None:
                out[spec.key] = None
                continue
            if spec.input_type in (
                InputType.STRING,
                InputType.INTEGER,
                InputType.FLOAT,
                InputType.BOOLEAN,
                InputType.CHOICE,
                InputType.TEXT_AREA,
                InputType.FIELD,
            ):
                out[spec.key] = val
            elif spec.input_type in (InputType.FILE_PATH, InputType.FOLDER_PATH):
                out[spec.key] = str(val) if val else ""
            elif spec.input_type in (
                InputType.VECTOR_LAYER,
                InputType.RASTER_LAYER,
                InputType.ANY_LAYER,
            ):
                # Store layer id + name + source for best-effort matching
                out[spec.key] = {
                    "id": val.id() if hasattr(val, "id") else "",
                    "name": val.name() if hasattr(val, "name") else "",
                    "source": val.source() if hasattr(val, "source") else "",
                }
            elif spec.input_type == InputType.CRS:
                out[spec.key] = val.authid() if hasattr(val, "authid") else str(val)
            else:
                out[spec.key] = str(val)
        return out

    def _restore_params(self, params: dict | None) -> None:
        """Apply a cached parameter dict back to the current widgets."""
        if not params:
            return
        for spec in self._input_specs:
            val = params.get(spec.key)
            if val is None:
                continue
            w = self._input_widgets.get(spec.key)
            if w is None:
                continue
            try:
                self._apply_cached_value(spec, w, val)
            except Exception:
                logger.debug(
                    "Could not restore cached value for '%s'", spec.key, exc_info=True
                )

    def _apply_cached_value(self, spec: InputSpec, w: QWidget, val: Any) -> None:
        """Set a single widget's value from a cached representation."""
        if spec.input_type == InputType.STRING:
            w.setText(str(val))
        elif spec.input_type == InputType.INTEGER:
            w.setValue(int(val))
        elif spec.input_type == InputType.FLOAT:
            w.setValue(float(val))
        elif spec.input_type == InputType.BOOLEAN:
            w.setChecked(bool(val))
        elif spec.input_type == InputType.CHOICE:
            idx = w.findText(str(val))
            if idx >= 0:
                w.setCurrentIndex(idx)
        elif spec.input_type in (InputType.FILE_PATH, InputType.FOLDER_PATH):
            w.setFilePath(str(val))
        elif spec.input_type in (
            InputType.VECTOR_LAYER,
            InputType.RASTER_LAYER,
            InputType.ANY_LAYER,
        ):
            self._try_restore_layer(w, val)
        elif spec.input_type == InputType.FIELD:
            w.setField(str(val))
        elif spec.input_type == InputType.CRS:
            crs = QgsCoordinateReferenceSystem(str(val))
            if crs.isValid():
                w.setCrs(crs)
        elif spec.input_type == InputType.TEXT_AREA:
            w.setText(str(val))

    @staticmethod
    def _try_restore_layer(combo: QgsMapLayerComboBox, info: Any) -> None:
        """Best-effort: match a project layer by id, then name, then source."""
        if isinstance(info, str):
            info = {"name": info}
        if not isinstance(info, dict):
            return
        project = QgsProject.instance()
        # Try by layer id first
        layer_id = info.get("id", "")
        if layer_id:
            lyr = project.mapLayer(layer_id)
            if lyr:
                combo.setLayer(lyr)
                return
        # Fall back to name match
        name = info.get("name", "")
        if name:
            matches = project.mapLayersByName(name)
            if matches:
                combo.setLayer(matches[0])
                return
        # Fall back to source match
        source = info.get("source", "")
        if source:
            for lyr in project.mapLayers().values():
                if lyr.source() == source:
                    combo.setLayer(lyr)
                    return

    def _populate_history_menu(self) -> None:
        """Refresh the history popup menu from the cache."""
        if self._history_menu is None:
            return
        self._history_menu.clear()
        history = self._param_cache.load_history()
        if not history:
            action = self._history_menu.addAction("No previous runs")
            action.setEnabled(False)
            return
        for entry in reversed(history):  # most recent first
            ts = entry.get("timestamp", "?")
            try:
                from datetime import datetime, timezone

                dt = datetime.fromisoformat(ts)
                label = dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                label = ts
            p = entry.get("params", {})
            summary_parts = []
            for spec in self._input_specs[:3]:
                v = p.get(spec.key)
                if v is not None:
                    if isinstance(v, dict):
                        v = v.get("name", str(v))
                    text = str(v)
                    if len(text) > 20:
                        text = text[:20] + "\u2026"
                    summary_parts.append(f"{spec.label}={text}")
            summary = ", ".join(summary_parts)
            display = f"{label}  \u2014  {summary}" if summary else label
            params = entry.get("params")
            action = self._history_menu.addAction(display)
            action.triggered.connect(lambda checked, p=params: self._restore_params(p))

    def _on_run_clicked(self) -> None:
        """Collect inputs, validate, then dispatch execute_logic via uv run --isolated."""
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

        # Cache parameters before launch
        cacheable = self._serialize_for_cache(inputs)
        self._param_cache.save_last(cacheable)
        self._param_cache.push_history(cacheable)
        self._populate_history_menu()

        self._output_area.clear()
        self._run_button.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)  # indeterminate
        self._output_area.append("Launching in isolated process…")

        try:
            self._launch_isolated(inputs)
        except Exception as exc:
            self._output_area.append(f"[ERROR] Failed to launch: {exc}")
            logger.exception(
                "Failed to launch isolated subprocess for '%s'", self.app_id
            )
            self._run_button.setEnabled(True)
            self._progress_bar.setVisible(False)

    def _launch_isolated(self, inputs: dict) -> None:
        """Serialise inputs, write runner+config, spawn uv run --isolated."""
        launch = launch_isolated_app_run(
            app_dir=self.app_dir,
            app_meta=self.app_meta,
            inputs=inputs,
            uv_bridge=self._get_uv_bridge(),
            keep_open=True,
        )
        self._tmp_dir = launch["tmp_dir"]

        # Start monitor thread – polls for output.json, signals us when done
        self._monitor = ProcessMonitor(
            launch["process"],
            launch["output_path"],
            launch["tmp_path"],
            stderr_log_path=launch["stderr_log_path"],
            parent=None,
        )
        self._monitor.completed.connect(self._on_subprocess_complete)
        self._monitor.error.connect(self._on_subprocess_error)
        self._monitor.start()

    def _on_subprocess_complete(self, result: dict) -> None:
        """Called on the Qt main thread when the runner writes its output JSON."""
        status = result.get("status", "unknown")
        message = result.get("message", str(result))
        self._output_area.append(f"[{status.upper()}] {message}")

        traceback_text = result.get("traceback", "")
        if status == "error" and traceback_text:
            self._output_area.append(f"\n--- Traceback ---\n{traceback_text}")
            logger.error("App '%s' traceback:\n%s", self.app_id, traceback_text)

        # Replay any addMapLayer() calls that happened inside the subprocess
        added = result.get("__added_layers__", [])
        for layer_info in added:
            self._add_layer_to_project(layer_info)

        self.on_finalize(result)
        self._run_button.setEnabled(True)
        self._progress_bar.setVisible(False)
        # tmp_dir cleanup happens when TemporaryDirectory is GC'd

    def _on_subprocess_error(self, msg: str) -> None:
        """Called on the Qt main thread when the monitor detects an error."""
        self._output_area.append(f"[ERROR] {msg}")
        logger.error("App '%s' subprocess error: %s", self.app_id, msg)
        self._run_button.setEnabled(True)
        self._progress_bar.setVisible(False)

    def on_finalize(self, result: dict) -> None:
        """Optional hook called on the main thread after subprocess completes.

        Override to perform additional QGIS-side work (e.g. loading a result
        layer not captured via QgsProject.addMapLayer inside execute_logic).
        """
        pass

    def _add_layer_to_project(self, layer_info: dict) -> None:
        """Slot: resolve *layer_info* to a real QGIS layer and add it to the project."""
        source = layer_info.get("source", "")
        name = layer_info.get("name") or Path(source).stem
        provider = layer_info.get("provider", "ogr")
        layer_type = layer_info.get("layer_type", "auto")

        if not source:
            logger.warning("add_output_layer called with empty source — skipping")
            return

        lyr = None
        if layer_type == "raster":
            lyr = QgsRasterLayer(source, name, provider)
        elif layer_type == "vector":
            lyr = QgsVectorLayer(source, name, provider)
        else:
            # Auto-detect: try raster first (gdal), fall back to vector (ogr)
            lyr = QgsRasterLayer(source, name, "gdal")
            if not lyr.isValid():
                lyr = QgsVectorLayer(source, name, "ogr")

        if lyr and lyr.isValid():
            QgsProject.instance().addMapLayer(lyr)
        else:
            logger.warning("Could not load layer '%s' from '%s'", name, source)

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

    def add_output_layer(
        self,
        source: str | Path,
        name: str | None = None,
        provider: str = "ogr",
        layer_type: str = "auto",
    ) -> None:
        """Add a layer to the QGIS map canvas via the layer bridge signal.

        This is safe to call from ``on_finalize()`` or any main-thread context.
        The layer is loaded and added to the current project immediately.

        Args:
            source: File path or data source URI for the layer.
            name: Display name in the layer tree. Defaults to the file stem.
            provider: QGIS data-provider key (``"ogr"``, ``"gdal"``,
                ``"postgres"``, etc.).
            layer_type: ``"vector"``, ``"raster"``, or ``"auto"`` (tries
                raster then vector).
        """
        if self._layer_bridge is None:
            logger.warning(
                "add_output_layer called before widget was built — adding directly"
            )
            self._add_layer_to_project({
                "source": str(source),
                "name": name or Path(source).stem,
                "provider": provider,
                "layer_type": layer_type,
            })
            return

        self._layer_bridge.layer_requested.emit({
            "source": str(source),
            "name": name or Path(source).stem,
            "provider": provider,
            "layer_type": layer_type,
        })

    def get_project(self) -> QgsProject:
        """Convenience accessor for the current QGIS project."""
        return QgsProject.instance()

    def run_uvx_tool(
        self,
        tool: str,
        args: Optional[list[str]] = None,
        cwd: Optional[Path] = None,
        env: Optional[dict[str, str]] = None,
    ) -> int:
        """Launch ``uvx`` tool in a separate console window.

        Returns the spawned process PID.
        """
        bridge = self._get_uv_bridge()
        return bridge.launch_uvx_windowed(
            tool=tool,
            args=args,
            cwd=cwd or self.app_dir,
            env=env,
        )

    def run_uv_isolated(
        self,
        command: list[str],
        with_packages: Optional[list[str]] = None,
        cwd: Optional[Path] = None,
        env: Optional[dict[str, str]] = None,
    ) -> int:
        """Launch ``uv run --isolated`` in a separate console window.

        Returns the spawned process PID.
        """
        bridge = self._get_uv_bridge()
        return bridge.launch_uv_run_windowed(
            command=command,
            with_packages=with_packages,
            cwd=cwd or self.app_dir,
            env=env,
            isolated=True,
        )

    def _get_uv_bridge(self) -> UvBridge:
        if self._uv_bridge is None:
            self._uv_bridge = UvBridge(get_uv_executable())
        return self._uv_bridge
