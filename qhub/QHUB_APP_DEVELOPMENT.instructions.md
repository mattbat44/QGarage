---
applyTo: "qhub/apps/**"
---

# QHub App Development — Agent Instructions

You are developing a QHub app — a self-contained mini-tool that runs inside the QHub dashboard in QGIS. Follow these rules precisely.

## Architecture Overview

QHub apps run inside QGIS but their `execute_logic()` method is dispatched to an **isolated subprocess** via `uv run --isolated`. This means:

- The UI (inputs, progress bar, output area) lives on the QGIS main thread.
- Business logic runs in a **separate console window** as a plain Python process.
- QGIS APIs (`qgis.core`, `qgis.gui`) are **stubbed** in the subprocess — you get shims, not real QGIS objects.
- Communication is via JSON files (inputs.json → subprocess → output.json).

## App File Structure

Every app lives in its own folder under `qhub/apps/<app_id>/`:

```
qhub/apps/my_tool/
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
from qhub.core.base_app import BaseApp, InputType


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

## Execution Flow

1. User clicks **Run** in the QHub dashboard.
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
- **Don't use `QgsProcessingAlgorithm`** — QHub apps use `BaseApp`, not the Processing framework.
- **Don't modify `sys.path`** — the framework handles it.
- **Don't assume the working directory** — use absolute paths or `self.app_dir`.
- **Don't store state on `self`** between runs — each execution is a fresh subprocess.

## Converting a QgsProcessingAlgorithm to a QHub App

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

## Testing

Run the test suite with:

```bash
uv run pytest
```

Deploy the plugin to QGIS with:

```powershell
.\install-qhub-plugin.ps1
```

Then reload the plugin in QGIS (Plugin Manager → QHub → Reinstall/Reload) or restart QGIS.
