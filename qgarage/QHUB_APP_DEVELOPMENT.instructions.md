---
applyTo: "qgarage/apps/**"
---

# QGarage App Development — Agent Instructions

You are developing a QGarage app — a self-contained mini-tool that runs inside the QGarage dashboard in QGIS. Follow these rules precisely.

## Architecture Overview

QGarage apps run inside QGIS but their `execute_logic()` method is dispatched to an **isolated subprocess** via `uv run --isolated`. This means:

- The UI (inputs, progress bar, output area) lives on the QGIS main thread.
- Business logic runs in a **separate console window** as a plain Python process.
- QGIS APIs (`qgis.core`, `qgis.gui`) are **stubbed** in the subprocess — you get shims, not real QGIS objects.
- Communication is via JSON files (inputs.json → subprocess → output.json).

## App File Structure

Every app lives in its own folder under `qgarage/apps/<app_id>/`:

```
qgarage/apps/my_tool/
├── app_meta.json        # Required: app metadata
├── main.py              # Required: BaseApp subclass
├── requirements.txt     # Optional: pip dependencies (resolved at runtime by uv run --isolated)
└── ...                  # Any additional modules/data files
```

### app_meta.json

```json
{
  "name": "My Tool",
  "id": "my_tool",
  "version": "1.0.0",
  "author": "Author Name",
  "description": "What this tool does.",
  "icon_path": "",
  "entry_point": "main.py",
  "class_name": "MyToolApp",
  "tags": ["category", "another-tag"]
}
```

- `id` must match the folder name and be a valid Python identifier (snake_case).
- `class_name` must match the class defined in `main.py`.
- `entry_point` is always `main.py` unless there is a specific reason to change it.
- `icon_path` is optional; if provided, the icon file is copied into the plugin directory on install.

### requirements.txt

List pure-Python dependencies only. Do NOT list:

- `qgis`, `PyQt5`, `PyQt6` — provided by the QGIS runtime
- `gdal`, `osgeo` — provided by the QGIS/OSGeo4W environment
- `numpy` — typically bundled with QGIS

Dependencies are **NOT installed at app install time**. They are resolved at runtime by `uv run --isolated --with-requirements requirements.txt` each time the app executes. This keeps installation instant and avoids polluting the environment.

### Replacing an Existing App

Installing an app with the same `id` as an existing app overwrites it. The old app is unloaded, its card is removed, and the new version is registered and loaded in its place. No manual cleanup is required.

### main.py

```python
from qgarage.core.base_app import BaseApp, InputType


class MyToolApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Declare inputs here
        self.add_input("input_layer", "Input Layer", InputType.VECTOR_LAYER)
        self.add_input("output_folder", "Output Folder", InputType.FOLDER_PATH)

    def execute_logic(self, inputs):
        layer = inputs["input_layer"]
        output = inputs["output_folder"]
        # ... business logic ...
        return {"status": "success", "message": "Done"}
```

## The BaseApp Contract

### Constructor: `__init__(self, **kwargs)`

- Always call `super().__init__(**kwargs)`.
- Only declare inputs via `self.add_input(...)` — do NOT create Qt widgets manually.
- Do NOT call QGIS APIs here — this runs on the main thread during app discovery.

### `add_input(key, label, input_type, **kwargs)`

Registers a declarative input. The framework auto-generates the Qt widget.

**Available InputTypes and their value types in `execute_logic`:**

| InputType      | Widget                         | Value in `inputs` dict       |
| -------------- | ------------------------------ | ---------------------------- |
| `STRING`       | `QLineEdit`                    | `str`                        |
| `INTEGER`      | `QSpinBox`                     | `int`                        |
| `FLOAT`        | `QDoubleSpinBox`               | `float`                      |
| `BOOLEAN`      | `QCheckBox`                    | `bool`                       |
| `CHOICE`       | `QComboBox`                    | `str` (selected text)        |
| `FILE_PATH`    | `QgsFileWidget`                | `str` (absolute path)        |
| `FOLDER_PATH`  | `QgsFileWidget`                | `str` (absolute path)        |
| `VECTOR_LAYER` | `QgsMapLayerComboBox`          | Shim object (see below)      |
| `RASTER_LAYER` | `QgsMapLayerComboBox`          | Shim object (see below)      |
| `ANY_LAYER`    | `QgsMapLayerComboBox`          | Shim object (see below)      |
| `FIELD`        | `QgsFieldComboBox`             | `str` (field name)           |
| `CRS`          | `QgsProjectionSelectionWidget` | Shim object with `.authid()` |
| `TEXT_AREA`    | `QTextEdit`                    | `str`                        |

**Common `add_input` kwargs:**

- `default` — Default value (type must match InputType).
- `tooltip` — Tooltip text shown on hover.
- `required` — `True` (default) or `False`. Required inputs block execution if empty.
- `choices` — List of strings for `CHOICE` type.
- `min_value` / `max_value` — Numeric bounds for `INTEGER` and `FLOAT`.
- `linked_layer_key` — For `FIELD` type: key of the layer input to pull fields from.
- `file_filter` — For `FILE_PATH`: e.g. `"GeoTIFF (*.tif);;All Files (*.*)"`.
- `group` — Group label string. Inputs with the same group are placed in a `QGroupBox`.

### `add_output(key, label, output_type, **kwargs)`

**Optional.** Registers a declarative output for the Processing framework.

When apps are exposed as Processing algorithms, output specs tell the framework what keys to expect in the `execute_logic()` result dict and how to expose them as algorithm outputs. This enables:

- **Model Builder integration** — outputs can be connected to other algorithm inputs
- **Batch processing** — outputs are automatically collected and displayed
- **Scripting** — outputs are returned in a typed, predictable way

**Available OutputTypes:**

| OutputType      | Processing Output Class           | Expected value in result dict |
| --------------- | --------------------------------- | ----------------------------- |
| `STRING`        | `QgsProcessingOutputString`       | `str`                         |
| `INTEGER`       | `QgsProcessingOutputNumber`       | `int`                         |
| `FLOAT`         | `QgsProcessingOutputNumber`       | `float`                       |
| `BOOLEAN`       | `QgsProcessingOutputBoolean`      | `bool`                        |
| `FILE`          | `QgsProcessingOutputFile`         | `str` (file path)             |
| `FOLDER`        | `QgsProcessingOutputFolder`       | `str` (folder path)           |
| `VECTOR_LAYER`  | `QgsProcessingOutputVectorLayer`  | `str` (layer path or ID)      |
| `RASTER_LAYER`  | `QgsProcessingOutputRasterLayer`  | `str` (layer path or ID)      |
| `ANY_LAYER`     | `QgsProcessingOutputMapLayer`     | `str` (layer path or ID)      |

**Common `add_output` kwargs:**

- `description` — Optional help text shown in the Processing UI. Defaults to the label.

**Example:**

```python
from qgarage.core.base_app import BaseApp, InputType, OutputType


class MyAnalysisApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input("input_layer", "Input Layer", InputType.VECTOR_LAYER)
        self.add_output("feature_count", "Feature Count", OutputType.INTEGER)
        self.add_output("output_file", "Output File", OutputType.FILE,
                       description="Path to the analysis result CSV")

    def execute_logic(self, inputs):
        layer = inputs["input_layer"]
        count = layer.featureCount()

        # ... analysis logic ...
        output_path = "/path/to/result.csv"

        return {
            "status": "success",
            "message": f"Analyzed {count} features",
            "feature_count": count,
            "output_file": output_path
        }
```

**Important notes:**

- **Output specs are optional.** Apps without `add_output()` calls work exactly as before.
- **Backward compatibility is preserved.** The framework always returns `STATUS` and `MESSAGE` outputs even if not declared.
- **Only declared outputs are exposed.** Keys in the result dict that don't have matching `add_output()` calls are not exposed to Processing (but are still available in `on_finalize()`).
- **Dynamic mode apps are not affected.** Output specs only apply to declarative apps exposed through Processing.

### `execute_logic(self, inputs) -> dict`

**This is the only method you must implement.** It contains your business logic.

**Critical rules:**

1. **This runs in a subprocess, not in QGIS.** You do NOT have access to the live QGIS application, map canvas, or project.

2. **QGIS objects are shims.** Layer inputs are deserialized as fake objects:
   - Vector layers: have `.source()` (path to a temp GeoJSON export), `.name()`, `.crs().authid()`, `.extent()` (with `.xMinimum()`, etc.), `.featureCount()`
   - Raster layers: have `.source()` (original file path), `.name()`, `.crs().authid()`
   - CRS: has `.authid()` returning e.g. `"EPSG:4326"`

3. **Use `self.log(message)` for output.** In the subprocess, this maps to `print()` and appears live in the console window.

4. **Return a dict** with at least `{"status": "success"|"error", "message": "..."}`. Any extra keys are passed through to `on_finalize()`.

5. **To add layers to QGIS after execution**, call:

   ```python
   from qgis.core import QgsProject, QgsRasterLayer
   QgsProject.instance().addMapLayer(QgsRasterLayer(path, name))
   ```

   This is intercepted by the stub and replayed on the QGIS main thread when the subprocess finishes. Both vector and raster layers are auto-detected during replay.

6. **For file I/O with vector layer geometry**, use the `.source()` path (a GeoJSON file) and process it with standard Python libraries (e.g., `json`, `fiona`, `geopandas`, `osgeo.ogr`). Do NOT use `QgsVectorFileWriter` for new output — it is a no-op stub.

7. **`gdal` / `osgeo` ARE available** in the subprocess because the QGIS Python interpreter is used. You can call `gdal.BuildVRT()`, `gdal.Warp()`, `gdal.Translate()`, etc.

### `validate_inputs(self, inputs) -> Optional[str]`

Optional override. Return an error message string to block execution, or `None` to allow it. Runs on the main thread before subprocess launch.

```python
def validate_inputs(self, inputs):
    if not inputs.get("api_key"):
        return "API key is required"
    return None
```

### `add_output_layer(source, name=None, provider="ogr", layer_type="auto")`

Add a layer to the QGIS map canvas via a Qt signal. Safe to call from `on_finalize()` or any main-thread context. This is the **preferred way** to deliver output layers without the subprocess round-trip.

```python
# In on_finalize — runs on the QGIS main thread
def on_finalize(self, result):
    if result.get("status") == "success":
        self.add_output_layer(result["output_path"], "My Result")  # auto-detect type
        self.add_output_layer("/tmp/out.tif", "Raster", provider="gdal", layer_type="raster")
        self.add_output_layer("/tmp/out.geojson", "Vector", layer_type="vector")
```

Parameters:

- `source` — File path or data source URI.
- `name` — Display name (defaults to file stem).
- `provider` — QGIS provider key: `"ogr"`, `"gdal"`, `"postgres"`, etc.
- `layer_type` — `"vector"`, `"raster"`, or `"auto"` (tries raster/gdal first, then vector/ogr).

### `on_finalize(self, result: dict)`

Optional override. Called on the **QGIS main thread** after the subprocess finishes. Use it to load result layers or update the project. The `result` dict contains everything returned by `execute_logic()`. Use `self.add_output_layer()` to deliver layers.

```python
def on_finalize(self, result):
    if result.get("status") == "success" and result.get("output_path"):
        self.add_output_layer(result["output_path"], "Result")
```

### `on_load()` / `on_unload()`

Optional lifecycle hooks. Called when the app is loaded/unloaded by the registry. Rarely needed.

---

## Dynamic (Custom) UI Mode

By default QGarage auto-generates a form from your `add_input()` declarations (**declarative mode**). If you need a richer interface — multi-step wizards, tab widgets, canvas interactions, real-time plots — you can opt into **dynamic mode** by overriding `build_dynamic_widget()`.

### How it works

| Feature                | Declarative mode                  | Dynamic mode                                                 |
| ---------------------- | --------------------------------- | ------------------------------------------------------------ |
| UI source              | Auto-generated from `add_input()` | Your own `QWidget` from `build_dynamic_widget()`             |
| `execute_logic()`      | **Required** — runs in subprocess | **Not called** — wire your own signals                       |
| Subprocess isolation   | Yes (uv run --isolated)           | No — all logic on the QGIS main thread (or your own threads) |
| Progress / output area | Provided automatically            | You provide them                                             |

### Minimal example

```python
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit
from qgarage.core.base_app import BaseApp


class MyDynamicApp(BaseApp):
    def build_dynamic_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel(self.app_name))

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        layout.addWidget(self._output)

        run_btn = QPushButton("Run")
        run_btn.clicked.connect(self._run)
        layout.addWidget(run_btn)

        return widget

    def _run(self):
        # Runs on the QGIS main thread — safe to call QGIS APIs directly
        self._output.append("Hello from dynamic mode!")
```

### Rules for dynamic mode

1. **Return a `QWidget`** from `build_dynamic_widget()`. The framework hosts it in a scroll area.
2. **`execute_logic()` is never called.** You do not need to implement it.
3. **All logic runs on the QGIS main thread** (or threads you manage yourself). There is no subprocess isolation.
4. **QGIS APIs are fully available** — you have a live `QgsProject`, `QgsMapCanvas`, layers, etc.
5. Use `self.app_meta`, `self.app_dir`, and `self.app_id` for metadata/paths.
6. `on_load()` / `on_unload()` lifecycle hooks still fire normally.
7. You can use any Qt widget from `qgis.PyQt.QtWidgets` or QGIS-specific widgets (`QgsMapLayerComboBox`, etc.).

### When to choose dynamic mode

- The tool needs a **multi-step wizard** or custom tab layout.
- You need **instant / reactive** feedback that doesn't fit a single "Run" click.
- The tool manipulates the **map canvas** directly (e.g., rubber-band drawing, picking features).
- You want a **live dashboard** (charts, real-time stats) rather than a one-shot processor.

---

## Execution Flow

1. User clicks **Run** in the QGarage dashboard.
2. Framework calls `validate_inputs()` on the main thread.
3. Inputs are serialized: QGIS layers → GeoJSON exports + metadata dicts; primitives pass through.
4. A temp directory is created with `inputs.json`, `runner.py`, `config.json`.
5. `uv run --isolated --python <python.exe> runner.py config.json` is launched in a **new console window**.
6. The runner script stubs all `qgis.*` modules, deserializes inputs, imports your app class, and calls `execute_logic(inputs)`.
7. `self.log()` calls become `print()` — visible live in the console.
8. The result dict is written to `output.json`.
9. A `ProcessMonitor` QThread on the QGIS side polls for `output.json` and emits a signal when found.
10. `_on_subprocess_complete()` runs on the main thread: logs status, replays `addMapLayer()` calls, and calls `on_finalize()`.

## Common Patterns

### Pattern: Download + Process + Load

```python
class MyDownloader(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input("area", "Area of Interest", InputType.VECTOR_LAYER)
        self.add_input("output_folder", "Output Folder", InputType.FOLDER_PATH)
        self.add_input("output_name", "Output Name", InputType.STRING, default="result")

    def execute_logic(self, inputs):
        import requests, os
        from osgeo import gdal

        area = inputs["area"]
        extent = area.extent()
        out_folder = inputs["output_folder"]
        out_name = inputs["output_name"]

        self.log(f"Extent: {extent.xMinimum()}, {extent.yMinimum()}, {extent.xMaximum()}, {extent.yMaximum()}")

        # Download data using extent...
        self.log("Downloading tiles...")
        # ... download logic ...

        # Process with GDAL
        out_path = os.path.join(out_folder, f"{out_name}.tif")
        # gdal.Warp(out_path, ...)

        # Auto-add to QGIS (intercepted by stub, replayed on main thread)
        from qgis.core import QgsProject, QgsRasterLayer
        QgsProject.instance().addMapLayer(QgsRasterLayer(out_path, out_name))

        return {"status": "success", "message": f"Saved to {out_path}"}
```

### Pattern: API Key Management

```python
class ApiTool(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input("api_key", "API Key", InputType.STRING,
                       tooltip="Leave blank to use saved key")

    def execute_logic(self, inputs):
        import json, os

        api_key = inputs.get("api_key", "")
        config_path = os.path.join(str(self.app_dir), "config.json")

        if api_key:
            with open(config_path, "w") as f:
                json.dump({"api_key": api_key}, f)
        elif os.path.exists(config_path):
            with open(config_path) as f:
                api_key = json.load(f).get("api_key", "")

        if not api_key:
            return {"status": "error", "message": "No API key provided or saved."}

        # Use api_key...
        return {"status": "success", "message": "Done"}
```

### Pattern: Grouped Inputs

```python
self.add_input("input_layer", "Input Layer", InputType.VECTOR_LAYER, group="Input")
self.add_input("filter_field", "Filter Field", InputType.FIELD,
               linked_layer_key="input_layer", group="Input")
self.add_input("output_folder", "Output Folder", InputType.FOLDER_PATH, group="Output")
self.add_input("output_name", "Output Name", InputType.STRING, group="Output")
```

### Pattern: Using on_finalize + add_output_layer

```python
def execute_logic(self, inputs):
    # ... processing ...
    return {
        "status": "success",
        "message": "Processed 3 layers",
        "output_files": [
            {"path": "/tmp/a.tif", "name": "Layer A"},
            {"path": "/tmp/b.tif", "name": "Layer B"},
            {"path": "/tmp/c.geojson", "name": "Layer C"},
        ]
    }

def on_finalize(self, result):
    for f in result.get("output_files", []):
        self.add_output_layer(f["path"], f["name"])  # auto-detect type
```

## Parameter Caching & Run History

Every app automatically gets **parameter caching** and **run history** — no code changes required.

### How It Works

- **Last-used parameters** are saved to `QgsSettings` each time the user clicks **Run**. When the app UI is rebuilt (e.g. navigating back to it), the last-used values are automatically restored.
- **Run history** keeps up to 20 recent parameter sets. A **History** dropdown appears at the top of every app below the description. Selecting an entry restores all parameters to those values.
- Layer inputs are matched best-effort by layer ID → name → source, so they restore correctly as long as the same layers are loaded in the project.
- CRS values store the `authid()` string (e.g. `EPSG:4326`).
- File/folder paths, strings, numbers, booleans, choices, and text areas are stored directly.

### Clearing Cache

```python
from qgarage.core.settings import ParameterCache
ParameterCache("my_app_id").clear()
```

### Notes

- State between runs is **not shared via `self`** — each `execute_logic()` invocation runs in a fresh subprocess. The cache operates at the UI level only.
- Apps do not need to opt in or change any code — caching is handled by the framework.

## Critical Do's and Don'ts

### DO

- Import third-party libraries inside `execute_logic()`, not at module top level (they may not be on QGIS's sys.path, only in the subprocess env).
- Use `self.log()` liberally for user-visible progress.
- Return descriptive status messages.
- Use `self.app_dir` for paths relative to your app folder (config files, data caches).
- Use `os.path.join` or `pathlib.Path` for cross-platform paths.
- List all pip dependencies in `requirements.txt`.
- Use `on_finalize()` for any QGIS-side post-processing (this runs in real QGIS, not the stub).
- Use `self.add_output_layer(path, name)` in `on_finalize()` to load layers — it is signal-based and the **preferred** way to deliver layers.

### DON'T

- **Don't use `QgsVectorFileWriter`** in `execute_logic()` — it's a no-op stub. Use `osgeo.ogr`, `fiona`, or `geopandas` to write vector files.
- **Don't call `iface`** or any `qgis.utils.iface` methods — `iface` does not exist in the subprocess.
- **Don't create Qt widgets** in `execute_logic()` — there is no event loop in the subprocess.
- **Don't import `PyQt5` or `PyQt6` directly** — always use `qgis.PyQt` for QGIS compatibility (but only in main-thread code, not in `execute_logic`).
- **Don't use `QgsProcessingAlgorithm`** — QGarage apps use `BaseApp`, not the Processing framework.
- **Don't modify `sys.path`** — the framework handles it.
- **Don't assume the working directory** — use absolute paths or `self.app_dir`.
- **Don't store state on `self`** between runs — each execution is a fresh subprocess.

## Converting a QgsProcessingAlgorithm to a QGarage App

If you have an existing `QgsProcessingAlgorithm`, follow these steps:

1. **Map parameters → `add_input()` calls:**
   - `QgsProcessingParameterFeatureSource` → `InputType.VECTOR_LAYER`
   - `QgsProcessingParameterRasterLayer` → `InputType.RASTER_LAYER`
   - `QgsProcessingParameterEnum` → `InputType.CHOICE` with `choices=[...]`
   - `QgsProcessingParameterFolderDestination` → `InputType.FOLDER_PATH`
   - `QgsProcessingParameterString` → `InputType.STRING`
   - `QgsProcessingParameterNumber` → `InputType.INTEGER` or `InputType.FLOAT`
   - `QgsProcessingParameterBoolean` → `InputType.BOOLEAN`
   - `QgsProcessingParameterCrs` → `InputType.CRS`

2. **Move `processAlgorithm` body → `execute_logic()`:**
   - Replace `self.parameterAs*(parameters, key, context)` with `inputs["key"]`.
   - Replace `feedback.pushInfo(...)` with `self.log(...)`.
   - Replace `feedback.setProgress(...)` with `self.set_progress(value, maximum)`.
   - Area/layer `.sourceExtent()` becomes `layer.extent()` (shim object).
   - Use `layer.source()` to get the GeoJSON file path for vector data.
   - Use `layer.crs().authid()` for CRS strings.

3. **Handle layer output** via `QgsProject.instance().addMapLayer()` in `execute_logic()` (auto-replayed) or preferably via `self.add_output_layer(path, name)` in `on_finalize()`.

4. **Create `app_meta.json`** with matching `id`, `class_name`, etc.

5. **Create `requirements.txt`** with any non-QGIS dependencies (e.g., `requests`, `pandas`).

## Qt Import Convention

For any code that runs on the QGIS main thread (e.g., `on_finalize`, `validate_inputs`):

```python
from qgis.PyQt.QtWidgets import ...   # CORRECT
from qgis.PyQt.QtCore import ...      # CORRECT
```

Never use `PyQt5` or `PyQt6` directly — this breaks compatibility between QGIS 3.x and 4.0.

## Creating a New App — Step-by-Step Checklist

Follow every step in order. Each one is a common reason an app fails to open.

### 1. Create the folder

```
qgarage/apps/<app_id>/
```

`<app_id>` must be a valid Python identifier (lowercase, underscores, no spaces). Example: `dem_slope`.

### 2. Create `app_meta.json`

```json
{
  "name": "DEM Slope",
  "id": "dem_slope",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "Computes slope from a DEM raster.",
  "icon_path": "",
  "entry_point": "main.py",
  "class_name": "DemSlopeApp",
  "tags": ["dem", "raster"]
}
```

**Checklist:**

- [ ] `"id"` exactly matches the folder name.
- [ ] `"class_name"` exactly matches the class name in `main.py`.
- [ ] The JSON is valid (no trailing commas, all strings quoted).

### 3. Create `main.py`

```python
from qgarage.core.base_app import BaseApp, InputType


class DemSlopeApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input("dem", "DEM Raster", InputType.RASTER_LAYER)

    def execute_logic(self, inputs):
        dem = inputs["dem"]
        self.log(f"Processing: {dem.name()}")
        return {"status": "success", "message": "Done"}
```

**Checklist:**

- [ ] `super().__init__(**kwargs)` is the first line of `__init__`. The `**kwargs` must be passed through — without it, `app_meta` and `app_dir` are never set, and the app will crash on load with `TypeError`.
- [ ] The class name matches `"class_name"` in `app_meta.json` exactly (case-sensitive).
- [ ] `execute_logic` returns a dict with at least `{"status": ..., "message": ...}`.
- [ ] The import is `from qgarage.core.base_app import BaseApp, InputType` — not a relative import.
- [ ] There are no syntax errors (run `python -m py_compile main.py` to check).
- [ ] No code at module level calls Qt or QGIS APIs — only plain Python.

### 4. (Optional) Create `requirements.txt`

Only needed if your app uses packages not bundled with QGIS. Leave the file empty or omit it if you have no extra dependencies.

### 5. Deploy and reload

```powershell
.\install-qgarage-plugin.ps1
```

Then in QGIS: **Plugins → QGarage → (close and reopen dock, or restart QGIS)**. The new card should appear in the dashboard.

---

## Why My App Doesn't Open — Diagnostic Guide

When clicking **Open** on an app card does nothing (or snaps back to the card grid), it means the app **failed to load or failed to build its UI**. Work through these checks in order.

### Step 1 — Check the app state badge

If the card shows an orange **"Error"** or red **"Crashed"** badge, the app failed to _load_. The error happened during import of `main.py` or during `__init__`. See Step 2.

If the card shows no badge (i.e. it looks healthy) but opening it immediately returns to the card grid, the app loaded fine but `build_widget()` / `build_dynamic_widget()` threw an exception. See Step 3.

### Step 2 — Loading errors (badge on card)

The most common causes, in order:

| Cause                                                                      | Fix                                                        |
| -------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `super().__init__(**kwargs)` missing or called without `**kwargs`          | Add it as the very first line of `__init__`                |
| `"class_name"` in `app_meta.json` doesn't match the class in `main.py`     | Make them identical, case-sensitive                        |
| `"id"` in `app_meta.json` doesn't match the folder name                    | Rename one to match the other                              |
| Syntax error in `main.py`                                                  | Run `python -m py_compile main.py` in a terminal           |
| Top-level import fails (e.g. a package not available on QGIS's `sys.path`) | Move third-party imports inside `execute_logic()`          |
| Relative import used (`from .something import X`)                          | Use absolute imports: `from qgarage.core.base_app import ...` |

To see the full traceback: open the QGIS **Python Console** and look for the error logged by QGarage, or click the **Reset** button on the card — the error message is stored in `AppHealth.error_text`.

### Step 3 — UI build errors (no badge, but opens and snaps back)

This means the app was loaded successfully but crashed inside `build_widget()` or `build_dynamic_widget()`. The dashboard catches the exception and restores the card grid.

Common causes:

| Cause                                                                                               | Fix                                                                          |
| --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| **Dynamic mode:** `build_dynamic_widget()` raises an exception                                      | Check the QGIS Python Console for the traceback                              |
| **Dynamic mode:** `build_dynamic_widget()` returns `None` instead of a `QWidget`                    | Ensure all code paths return a `QWidget` instance                            |
| Qt widget created with a bad parent or invalid arguments                                            | Construct widgets without a parent first, set layout explicitly              |
| Calling a QGIS API that isn't available yet (e.g. accessing the project before QGIS is fully ready) | Move initialization into a slot or `on_load()`, not `build_dynamic_widget()` |

To see the error: open the **QGIS Python Console** — the framework logs the full traceback via `logger.exception`.

### Step 4 — App opens but Run does nothing (declarative mode)

| Cause                                              | Fix                                                           |
| -------------------------------------------------- | ------------------------------------------------------------- |
| A required input is empty (e.g. no layer selected) | Fill all required fields before clicking Run                  |
| `validate_inputs()` returns an error string        | Check the output area — the validation message is shown there |
| `execute_logic` not implemented                    | Implement it (it raises `NotImplementedError` by default)     |

### Step 5 — App opens but subprocess window never appears

The subprocess launch itself failed.

| Cause                                            | Fix                                               |
| ------------------------------------------------ | ------------------------------------------------- |
| `uv` not found or not configured                 | Check QGarage settings — the `uv` path must be valid |
| `requirements.txt` lists an unresolvable package | Remove or fix the broken dependency               |

---

## Testing

Run the test suite with:

```bash
uv run pytest
```

Deploy the plugin to QGIS with:

```powershell
.\install-qgarage-plugin.ps1
```

Then reload the plugin in QGIS (Plugin Manager → QGarage → Reinstall/Reload) or restart QGIS.
