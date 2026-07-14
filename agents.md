--

# QGarage App Development Guide for Agents

This document is your complete reference for building QGarage applications. You do not need to examine the QGarage framework code — everything you need to know is described here.

## What Is QGarage?

QGarage is a lightweight framework for QGIS that lets you build and deploy self-contained geospatial tools ("Apps") without complex plugin boilerplate. Each app:

- Runs in its own **isolated subprocess** with a clean Python environment (`uv` or `pixi`)
- Gets an **auto-generated Qt UI** from declarative input definitions
- Can be **installed independently** as a ZIP or folder
- Appears in both the **QGarage dashboard** and **QGIS Processing Toolbox** (if declarative)
- Has access to **GDAL, numpy, and other QGIS bundled libraries**

---

## Quick Start: Creating Your First App

Every app needs exactly three things:

1. **app_meta.json** — Metadata and configuration
2. **main.py** — Your BaseApp subclass with input definitions and business logic
3. **requirements.txt** (optional) — Any pip dependencies your app needs

All three live in a single folder: `qgarage/apps/<app_id>/`

### Minimal Example

```json
{
  "name": "My First Tool",
  "id": "my_first_tool",
  "version": "1.0.0",
  "author": "You",
  "description": "A simple demonstration tool.",
  "icon_path": "",
  "entry_point": "main.py",
  "class_name": "MyFirstToolApp",
  "tags": ["demo"]
}
```

```python
from qgarage.core.base_app import BaseApp, InputType

class MyFirstToolApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input("input_text", "Input Text", InputType.STRING)

    def execute_logic(self, inputs):
        text = inputs["input_text"]
        self.log(f"You entered: {text}")
        return {"status": "success", "message": "Done"}
```

That's it. Place both files in `qgarage/apps/my_first_tool/` and deploy with the install script. The framework handles the rest.

---

## Understanding the Architecture

### Execution Model: Subprocess Isolation

QGarage has a critical design: **`execute_logic()` runs in a subprocess, not in QGIS.**

**Why?** Each app gets its own clean Python environment. If your app's dependencies conflict with QGIS's environment, they don't break QGIS.

**What this means for you:**

- **Main thread:** UI, input widgets, progress bar — all live on the QGIS main thread
- **Subprocess:** Your `execute_logic()` code runs here, completely isolated
- **Communication:** Inputs are serialized to JSON, passed to subprocess, results come back as JSON
- **QGIS stubs:** In the subprocess, QGIS modules are fake shims that support enough to let you access layer data and add results back to QGIS

**Key implication:** You cannot call `iface` or manipulate the live QGIS application inside `execute_logic()`. You can, however, call `self.log()` for output and return layers to be loaded via `add_output_layer()` or `addMapLayer()` calls.

---

## App File Structure

### app_meta.json (Required)

Metadata that the framework reads to register and display your app. All fields are required.

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `name` | string | "DEM Slope Calculator" | User-visible app name |
| `id` | string | `dem_slope_calc` | Folder name + Python identifier (snake_case) |
| `version` | string | "1.0.0" | Semantic versioning |
| `author` | string | "Your Name" | Author credit |
| `description` | string | "Computes slope from a DEM." | Shown in the dashboard |
| `icon_path` | string | `""` or `"icon.png"` | Icon file (optional, relative to app dir) |
| `entry_point` | string | `"main.py"` | Always `main.py` |
| `class_name` | string | `"DemSlopeCalcApp"` | Class name in main.py (case-sensitive) |
| `tags` | array | `["dem", "raster", "analysis"]` | Search/filtering tags |

**Critical rule:** `"id"` must exactly match your folder name, and `"class_name"` must exactly match your class name in `main.py`. Mismatches are the #1 reason apps fail to load.

### main.py (Required)

Your app's logic. Must define a class that inherits from `BaseApp`:

```python
from qgarage.core.base_app import BaseApp, InputType

class MyToolApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Declare inputs in constructor
        self.add_input("input_param", "Label", InputType.STRING)

    def execute_logic(self, inputs):
        # Your business logic here
        param = inputs["input_param"]
        # ...
        return {"status": "success", "message": "..."}
```

**Mandatory imports:**
- `from qgarage.core.base_app import BaseApp, InputType`

**Never do this in main.py:**
- Don't put third-party imports at the module level (import them inside `execute_logic()` instead)
- Don't call Qt or QGIS APIs at module level
- Don't use relative imports; only absolute imports

### requirements.txt (Optional: uv backend)

List one package per line. These are pip packages installed into a persistent venv on first run.

```
requests>=2.28
pandas>=1.5
geopandas
```

**Do NOT list:**
- `qgis`, `PyQt5`, `PyQt6` — provided by QGIS
- `gdal`, `osgeo` — provided by QGIS/OSGeo4W
- `numpy` — typically bundled with QGIS

**Backend selection:** If your app has only `requirements.txt`, it uses the **uv backend** (QGIS's Python + your pip packages). If it has a `pixi.toml`, the **pixi backend** takes precedence.

### pixi.toml (Optional: conda backend)

Use this if your app needs compiled packages from conda-forge (scipy, rasterio, compiled GDAL builds, etc.).

```toml
[project]
name = "my_app"
channels = ["conda-forge"]
platforms = ["win-64", "linux-64", "osx-64", "osx-arm64"]

[dependencies]
python = ">=3.10,<3.13"
scipy = "*"
gdal = ">=3.6"

[pypi-dependencies]
requests = ">=2.28"
```

**Key difference:** With pixi, **QGIS's bundled packages are NOT available**. If you need numpy or GDAL, declare them in `[dependencies]`.

---

## The BaseApp Contract

Every app is a subclass of `BaseApp`. You must implement these methods/patterns:

### `__init__(self, **kwargs)` (Required)

```python
def __init__(self, **kwargs):
    super().__init__(**kwargs)  # MUST be first line
    self.add_input("key1", "Label 1", InputType.STRING)
    self.add_input("key2", "Label 2", InputType.INTEGER, default=10)
```

**Rules:**
- Call `super().__init__(**kwargs)` as the very first line (without it, `app_meta` and `app_dir` are never set)
- Use `self.add_input()` to declare inputs
- Do NOT call QGIS or Qt APIs here
- Do NOT import heavy third-party libraries at module level

### `add_input(key, label, input_type, **kwargs)` 

Register a declarative input. The framework auto-generates a Qt widget for it.

```python
self.add_input("layer", "Input Vector Layer", InputType.VECTOR_LAYER)
self.add_input("buffer_distance", "Buffer Distance (m)", InputType.FLOAT, 
               default=10.0, min_value=0.1, max_value=1000.0)
self.add_input("output_format", "Output Format", InputType.CHOICE,
               choices=["GeoJSON", "Shapefile", "GeoPackage"])
```

#### InputTypes Reference

| InputType | Widget | Python Type | Example |
|-----------|--------|-------------|---------|
| `STRING` | Text box | `str` | "hello" |
| `INTEGER` | Spinner | `int` | 42 |
| `FLOAT` | Decimal spinner | `float` | 3.14 |
| `BOOLEAN` | Checkbox | `bool` | True |
| `CHOICE` | Dropdown | `str` | "Option A" |
| `FILE_PATH` | File picker | `str` | "/path/to/file.txt" |
| `FOLDER_PATH` | Folder picker | `str` | "/path/to/folder" |
| `VECTOR_LAYER` | Layer combo | Shim object | Has `.source()`, `.name()`, `.crs()` |
| `RASTER_LAYER` | Layer combo | Shim object | Has `.source()`, `.name()`, `.crs()` |
| `ANY_LAYER` | Layer combo | Shim object | Vector or raster |
| `FIELD` | Field combo | `str` | "id" |
| `CRS` | CRS picker | Shim object | Has `.authid()` (e.g., "EPSG:4326") |
| `TEXT_AREA` | Multi-line text | `str` | Multi-paragraph text |

#### Common kwargs for `add_input()`

| Kwarg | Type | Example | Effect |
|-------|------|---------|--------|
| `default` | varies | `default=10` | Initial/default value |
| `required` | bool | `required=True` | If False, empty inputs are allowed |
| `tooltip` | str | `tooltip="Tip text"` | Hover tooltip |
| `min_value` | number | `min_value=0` | Lower bound for INTEGER/FLOAT |
| `max_value` | number | `max_value=100` | Upper bound for INTEGER/FLOAT |
| `choices` | list | `choices=["A", "B"]` | Options for CHOICE type |
| `linked_layer_key` | str | `linked_layer_key="input_layer"` | For FIELD: which layer to get fields from |
| `file_filter` | str | `file_filter="*.tif"` | For FILE_PATH: file extension filter |
| `group` | str | `group="Input"` | Inputs in same group appear in a box |

### `execute_logic(self, inputs) -> dict` (Required for declarative mode)

Your main business logic. **This runs in a subprocess.**

```python
def execute_logic(self, inputs):
    # Inputs dict contains resolved values
    layer = inputs["vector_layer"]      # Shim object
    text = inputs["text_field"]         # String
    distance = inputs["distance"]       # Float
    
    # Log progress (visible in console window)
    self.log(f"Processing layer: {layer.name()}")
    
    # Your logic here (can use standard Python libraries)
    # Can import GDAL, osgeo, numpy, pandas, etc.
    
    # Return result dict
    return {
        "status": "success",  # or "error"
        "message": "Completed successfully",
        "output_path": "/tmp/result.geojson",  # optional extra data
    }
```

#### Critical Rules for `execute_logic()`

1. **Subprocess isolation:** You do NOT have access to `iface`, the live QGIS project, or any Qt event loop.

2. **Shim objects:** Layer inputs are fake objects with limited methods:
   - **Vector layers:** `.source()` (GeoJSON path), `.name()`, `.crs().authid()`, `.extent()`, `.featureCount()`
   - **Raster layers:** `.source()` (file path), `.name()`, `.crs().authid()`
   - **CRS:** `.authid()` (e.g., "EPSG:4326")

3. **Use `self.log(msg)`** for all output. It becomes `print()` in the subprocess:
   ```python
   self.log("Starting processing...")
   self.log(f"Found {layer.featureCount()} features")
   ```

4. **Return a dict** with at least `{"status": "success"|"error", "message": "..."}`. Any extra keys are passed to `on_finalize()`.

5. **Import third-party packages here**, not at module level:
   ```python
   def execute_logic(self, inputs):
       import requests  # OK - imported here
       import geopandas as gpd  # OK
       data = requests.get("...")
   ```

6. **Add layers via `QgsProject.addMapLayer()`** — it's intercepted and replayed on QGIS main thread:
   ```python
   from qgis.core import QgsProject, QgsVectorLayer
   layer = QgsVectorLayer(json_path, "Result", "ogr")
   QgsProject.instance().addMapLayer(layer)  # Intercepted and replayed
   ```

7. **GDAL/osgeo ARE available** because QGIS's Python is used:
   ```python
   from osgeo import gdal
   gdal.Warp(output_path, input_path, xRes=10, yRes=10)
   ```

8. **Do NOT use `QgsVectorFileWriter`** — it's a no-op stub. Use `osgeo.ogr` or `fiona` instead.

### `validate_inputs(self, inputs) -> Optional[str]` (Optional)

Run custom validation before launching subprocess. Return error message to block execution, or `None` to proceed.

```python
def validate_inputs(self, inputs):
    if inputs["distance"] < 0:
        return "Distance must be positive"
    return None
```

### `on_finalize(self, result: dict)` (Optional)

Called on the **QGIS main thread** after subprocess finishes. Use it to load result layers.

```python
def on_finalize(self, result):
    if result.get("status") == "success":
        self.add_output_layer(result["output_path"], "My Result")
```

### `add_output_layer(source, name=None, provider="ogr", layer_type="auto")`

Load a layer into QGIS. Preferred over `addMapLayer()` in `execute_logic()` because it uses signals.

```python
# Calls from on_finalize (main thread)
self.add_output_layer("/tmp/result.geojson", "Vector Result")
self.add_output_layer("/tmp/result.tif", "Raster Result", provider="gdal", layer_type="raster")
self.add_output_layer("/tmp/result.gpkg", "GeoPackage", layer_type="auto")
```

### `on_load()` / `on_unload()` (Optional)

Lifecycle hooks called when the app is loaded/unloaded. Rarely needed.

---

## Two Modes: Declarative vs. Dynamic

### Declarative Mode (Default)

Use `add_input()` declarations. Framework generates UI automatically.

- ✅ Auto-generated form
- ✅ Subprocess isolation
- ✅ Automatic Processing Toolbox integration
- ✅ Parameter caching / history
- ❌ Limited to simple forms

### Dynamic Mode

Override `build_dynamic_widget()` for custom UI (wizards, interactive tools, charts).

```python
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QPushButton, QTextEdit
from qgarage.core.base_app import BaseApp

class MyDynamicApp(BaseApp):
    def build_dynamic_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        self._output = QTextEdit()
        layout.addWidget(self._output)
        
        btn = QPushButton("Click me")
        btn.clicked.connect(self._on_click)
        layout.addWidget(btn)
        
        return widget
    
    def _on_click(self):
        # Runs on QGIS main thread
        self._output.append("Clicked!")
        # Access QGIS APIs, project, canvas, etc.
```

**Rules for dynamic mode:**
- `execute_logic()` is NOT called
- All code runs on QGIS main thread (no subprocess)
- QGIS APIs are fully available
- You provide your own UI, progress, output
- Does NOT appear in Processing Toolbox
- Use Qt imports from `qgis.PyQt.QtWidgets` and `qgis.PyQt.QtCore`

**When to use dynamic mode:**
- Multi-step wizards
- Real-time reactive feedback
- Map canvas interaction (drawing, picking)
- Live dashboards / charts

---

## Common Patterns

### Pattern: Process Vector Layer → Save Result

```python
def execute_logic(self, inputs):
    import os
    from osgeo import ogr
    
    layer = inputs["input_layer"]
    output_folder = inputs["output_folder"]
    
    # Read GeoJSON
    source = ogr.Open(layer.source())
    self.log(f"Processing {layer.name()} ({layer.featureCount()} features)")
    
    # Process and write result
    output_path = os.path.join(output_folder, f"{layer.name()}_processed.geojson")
    # ... processing logic ...
    
    return {
        "status": "success",
        "message": f"Saved to {output_path}",
        "output_path": output_path,
    }

def on_finalize(self, result):
    if result.get("status") == "success":
        self.add_output_layer(result["output_path"], "Processed Vector")
```

### Pattern: Download + Process + Load

```python
def execute_logic(self, inputs):
    import requests
    import os
    from osgeo import gdal
    
    bbox = inputs["area"].extent()
    output_folder = inputs["output_folder"]
    
    # Download (bounds as xmin, ymin, xmax, ymax)
    url = f"https://api.example.com/download?bbox={bbox.xMinimum()},{bbox.yMinimum()},{bbox.xMaximum()},{bbox.yMaximum()}"
    self.log("Downloading...")
    response = requests.get(url)
    
    # Save raw
    raw_path = os.path.join(output_folder, "raw.tif")
    with open(raw_path, "wb") as f:
        f.write(response.content)
    
    # Process with GDAL
    output_path = os.path.join(output_folder, "processed.tif")
    self.log("Processing with GDAL...")
    gdal.Warp(output_path, raw_path, xRes=10, yRes=10)
    
    return {
        "status": "success",
        "message": "Done",
        "output_path": output_path,
    }
```

### Pattern: API Key Persistence

```python
def execute_logic(self, inputs):
    import json
    import os
    
    api_key = inputs.get("api_key", "")
    config_path = os.path.join(str(self.app_dir), "config.json")
    
    # Save if provided
    if api_key:
        with open(config_path, "w") as f:
            json.dump({"api_key": api_key}, f)
    # Load if not provided
    elif os.path.exists(config_path):
        with open(config_path) as f:
            api_key = json.load(f).get("api_key", "")
    
    if not api_key:
        return {"status": "error", "message": "No API key"}
    
    # Use api_key...
    return {"status": "success", "message": "Done"}
```

### Pattern: Grouped Inputs

```python
self.add_input("input_layer", "Layer", InputType.VECTOR_LAYER, group="Input")
self.add_input("filter_field", "Filter Field", InputType.FIELD,
               linked_layer_key="input_layer", group="Input")
self.add_input("output_folder", "Output Folder", InputType.FOLDER_PATH, group="Output")
self.add_input("output_name", "Name", InputType.STRING, group="Output")
```

---

## Parameter Caching & Run History

**Automatic—no code changes needed.** Last-used parameters are saved to `QgsSettings`. A history dropdown remembers up to 20 recent runs.

Layer inputs are matched best-effort by layer ID → name → source. CRS values store the `authid()` string (e.g., "EPSG:4326").

**To clear cache programmatically:**
```python
from qgarage.core.settings import ParameterCache
ParameterCache("my_app_id").clear()
```

---

## Critical Do's and Don'ts

### ✅ DO

- **Import third-party libraries inside `execute_logic()`**, not at module top level
- **Use `self.log(msg)`** liberally for user-visible progress
- **Return descriptive status messages** for user feedback
- **Use `self.app_dir` / `self.app_id` / `self.app_meta`** for app paths and metadata
- **Use `os.path.join()` or `pathlib.Path`** for cross-platform file paths
- **List all pip dependencies in `requirements.txt`**
- **Use `on_finalize()` for QGIS-side post-processing**
- **Use `self.add_output_layer()` to load results** — it's the preferred signal-based method

### ❌ DON'T

- **Don't call `iface`** or any `qgis.utils.iface` methods — doesn't exist in subprocess
- **Don't use `QgsVectorFileWriter`** — it's a no-op stub; use `osgeo.ogr` or `fiona`
- **Don't create Qt widgets** in `execute_logic()` — no event loop in subprocess
- **Don't import `PyQt5` / `PyQt6` directly** — always use `qgis.PyQt` (main thread only)
- **Don't use `QgsProcessingAlgorithm`** — QGarage apps use `BaseApp`
- **Don't modify `sys.path`** — framework handles it
- **Don't assume the working directory** — use absolute paths or `self.app_dir`
- **Don't store state on `self`** between runs — each execution is a fresh subprocess

---

## Qt Import Convention

For code running on the QGIS main thread (dynamic mode, `on_finalize`, `validate_inputs`):

```python
from qgis.PyQt.QtWidgets import QWidget, QPushButton  # ✅ CORRECT
from qgis.PyQt.QtCore import Qt, pyqtSignal           # ✅ CORRECT
```

**Never:**
```python
from PyQt5.QtWidgets import QWidget  # ❌ WRONG — breaks QGIS 4.0 compat
from PyQt6.QtWidgets import QWidget  # ❌ WRONG
```

---

## Creating a New App: Step-by-Step Checklist

### 1. Create folder

```
qgarage/apps/my_new_tool/
```

Folder name = Python identifier (lowercase, underscores).

### 2. Create `app_meta.json`

```json
{
  "name": "My New Tool",
  "id": "my_new_tool",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "What it does.",
  "icon_path": "",
  "entry_point": "main.py",
  "class_name": "MyNewToolApp",
  "tags": ["tag1", "tag2"]
}
```

- [ ] `id` exactly matches folder name
- [ ] `class_name` exactly matches class in `main.py`
- [ ] JSON is valid (no trailing commas)

### 3. Create `main.py`

```python
from qgarage.core.base_app import BaseApp, InputType

class MyNewToolApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input("param1", "Parameter 1", InputType.STRING)
        self.add_input("param2", "Parameter 2", InputType.INTEGER)

    def execute_logic(self, inputs):
        param1 = inputs["param1"]
        param2 = inputs["param2"]
        self.log(f"Params: {param1}, {param2}")
        return {"status": "success", "message": "Completed"}
```

- [ ] `super().__init__(**kwargs)` is first line of `__init__`
- [ ] Class name matches `app_meta.json` exactly
- [ ] `execute_logic()` returns dict with `status` and `message`
- [ ] Import is `from qgarage.core.base_app import ...` (not relative)
- [ ] No syntax errors (`python -m py_compile main.py`)
- [ ] No module-level Qt/QGIS calls

### 4. (Optional) Create `requirements.txt` or `pixi.toml`

Only if your app needs extra packages.

**For `requirements.txt` (pure Python):**
```
requests>=2.28
geopandas
```

**For `pixi.toml` (conda packages):**
```toml
[project]
name = "my_new_tool"
channels = ["conda-forge"]
platforms = ["win-64", "linux-64", "osx-64", "osx-arm64"]

[dependencies]
python = ">=3.10,<3.13"
scipy = "*"

[pypi-dependencies]
requests = ">=2.28"
```

### 5. Deploy & reload

```powershell
.\install-qgarage-plugin.ps1
```

In QGIS: **Plugins → QGarage → (close/reopen dock or restart)**.

Your app card should appear in the dashboard.

---

## Troubleshooting

### App card shows Error/Crashed badge

Loading failed. Check QGIS Python Console for traceback, or click card's Reset button.

**Most common causes:**
| Cause | Fix |
|-------|-----|
| `super().__init__(**kwargs)` missing or incomplete | Add it as first line of `__init__` |
| `class_name` mismatch (case-sensitive) | Make it identical in `app_meta.json` and `main.py` |
| `id` doesn't match folder name | Rename folder or `id` to match |
| Syntax error in `main.py` | Run `python -m py_compile main.py` |
| Top-level import fails | Move imports into `execute_logic()` |
| Relative import used | Use absolute imports: `from qgarage.core.base_app import ...` |

### App opens but immediately snaps back to card grid

UI build crashed. Check QGIS Python Console for traceback.

**For dynamic mode:** Make sure `build_dynamic_widget()` returns a `QWidget` instance, and all code paths are valid.

### App opens, user fills inputs, but "Run" does nothing

- Validation failed silently — check output area for validation error
- `execute_logic()` not implemented — skeleton raises `NotImplementedError`
- A required input is empty — user must fill all `required=True` inputs

### Subprocess window never appears

Backend not found or misconfigured:

- **uv apps:** Check QGarage settings — `uv` path must be valid
- **pixi apps:** Check QGarage settings — `pixi` path must be valid
- **Dependencies broken:** Run `uv pip install -r requirements.txt` manually to diagnose

---

## Reference: What Gets Serialized?

When a user clicks **Run**, inputs are serialized from QGIS to JSON:

| InputType | Serialized as | Deserialized in subprocess as |
|-----------|---------------|------------------------------|
| STRING | String | `str` |
| INTEGER | Integer | `int` |
| FLOAT | Number | `float` |
| BOOLEAN | Boolean | `bool` |
| CHOICE | String | `str` (selected text) |
| FILE_PATH | String (absolute path) | `str` |
| FOLDER_PATH | String (absolute path) | `str` |
| VECTOR_LAYER | Layer metadata + GeoJSON path | Shim with `.source()`, `.name()`, `.crs()` |
| RASTER_LAYER | Layer metadata + file path | Shim with `.source()`, `.name()`, `.crs()` |
| CRS | EPSG code | Shim with `.authid()` |
| TEXT_AREA | String | `str` |

---

## Execution Flow (Advanced)

Understanding what happens when user clicks **Run**:

1. **Main thread:** `validate_inputs()` called
2. **Main thread:** Inputs serialized (layers → GeoJSON, values → JSON)
3. **Main thread:** Temp directory created with `inputs.json`, `config.json`, `runner.py`
4. **Subprocess launched:**
   - uv apps: `.venv/bin/python runner.py config.json`
   - pixi apps: `pixi run python runner.py config.json`
5. **Subprocess:** QGIS modules stubbed, app class imported, `execute_logic(inputs)` called
6. **Subprocess:** Output written to `output.json`
7. **Main thread:** ProcessMonitor polls for `output.json`, reads result
8. **Main thread:** `on_finalize(result)` called
9. **Main thread:** Any `addMapLayer()` calls from subprocess are replayed

---

## Converting an Existing QGIS Plugin

If you have a `QgsProcessingAlgorithm`, you can convert it to a QGarage app:

1. **Map parameters to `add_input()`:**
   - `QgsProcessingParameterFeatureSource` → `InputType.VECTOR_LAYER`
   - `QgsProcessingParameterRasterLayer` → `InputType.RASTER_LAYER`
   - `QgsProcessingParameterString` → `InputType.STRING`
   - `QgsProcessingParameterNumber` → `InputType.INTEGER` / `FLOAT`
   - `QgsProcessingParameterBoolean` → `InputType.BOOLEAN`
   - `QgsProcessingParameterCrs` → `InputType.CRS`

2. **Move `processAlgorithm()` body to `execute_logic()`:**
   - Replace `self.parameterAs*(parameters, key, context)` with `inputs["key"]`
   - Replace `feedback.pushInfo(...)` with `self.log(...)`
   - Use `layer.source()` to get GeoJSON path (vector)
   - Use `layer.crs().authid()` for CRS

3. **Create `app_meta.json`** with metadata.

4. **Create `requirements.txt`** if needed.

---

## Next Steps

- Read through the examples in `qgarage/apps/` to see real implementations
- Run the test suite: `uv run pytest`
- Deploy to QGIS and test your app in the dashboard
- Check the QGIS Python Console for errors

Good luck! 🎉
