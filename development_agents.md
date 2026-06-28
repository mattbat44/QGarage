# QGarage App Development — Complete Agent Reference

This document is the single source of truth for writing QGarage apps. Read it in full before touching any files. Everything here is derived directly from the framework source code.

---

## Table of Contents

1. [Architecture in One Page](#1-architecture-in-one-page)
2. [The Subprocess Boundary — The Most Critical Concept](#2-the-subprocess-boundary)
3. [Required File Structure](#3-required-file-structure)
4. [app_meta.json Reference](#4-app_metajson-reference)
5. [main.py — The App Class Contract](#5-mainpy--the-app-class-contract)
6. [All InputTypes](#6-all-inputtypes)
7. [Layer and CRS Shim Objects in execute_logic](#7-layer-and-crs-shim-objects-in-execute_logic)
8. [Returning Results and Loading Layers](#8-returning-results-and-loading-layers)
9. [Good Python Practice — Keep Logic in src/](#9-good-python-practice--keep-logic-in-src)
10. [Dependency Backends — uv vs pixi](#10-dependency-backends--uv-vs-pixi)
11. [Optional Hooks and Advanced Patterns](#11-optional-hooks-and-advanced-patterns)
12. [Dynamic Mode — Custom UI](#12-dynamic-mode--custom-ui)
13. [Toolboxes — Grouping Multiple Apps](#13-toolboxes--grouping-multiple-apps)
14. [Testing Your App Without QGIS](#14-testing-your-app-without-qgis)
15. [Complete Reference App (Well-Structured)](#15-complete-reference-app-well-structured)
16. [Diagnostic Guide — Why Doesn't It Open?](#16-diagnostic-guide--why-doesnt-it-open)
17. [Quick Checklist](#17-quick-checklist)

---

## 1. Architecture in One Page

QGarage is a QGIS plugin that hosts mini-tools ("apps"). Each app is a directory inside `qgarage/apps/`. The plugin:

1. **Discovers** apps by scanning for `app_meta.json` files.
2. **Loads** the app's Python class (on the QGIS main thread).
3. **Auto-generates** a Qt form from your `add_input()` declarations.
4. **Runs** your business logic in a **completely separate subprocess** when the user clicks Run.
5. **Replays** any layer additions back on the QGIS main thread when the subprocess finishes.

```
┌──────────────────────────────────────────────┐
│  QGIS Main Thread                            │
│                                              │
│  __init__()     ← runs here (import time)   │
│  build_widget() ← runs here (UI generation) │
│  validate_inputs() ← runs here              │
│  on_finalize()  ← runs here (post-run)      │
│  add_output_layer() ← runs here             │
└──────────────────┬───────────────────────────┘
                   │  inputs.json
                   ▼
┌──────────────────────────────────────────────┐
│  Isolated Subprocess (uv venv or pixi)       │
│                                              │
│  execute_logic(inputs) ← YOUR LOGIC HERE     │
│  self.log(msg) → print()                     │
│  QgsProject.addMapLayer() → captured         │
│                                              │
│  writes output.json                          │
└──────────────────────────────────────────────┘
```

**What this means for you:**
- `execute_logic()` has **no access** to the live QGIS application.
- All `qgis.*` imports in `execute_logic()` are satisfied by lightweight stubs (via `unittest.mock`).
- Third-party packages imported in `execute_logic()` must be listed in `requirements.txt` or `pixi.toml`.
- Third-party imports at **module top-level** (outside any function) will fail at load time if they are not in QGIS's own Python environment.

---

## 2. The Subprocess Boundary

This is the most important thing to understand. When the user clicks **Run**:

1. QGIS serialises your inputs to `inputs.json` in a temp directory.  
   - Primitive types (str, int, float, bool) → pass through as-is.  
   - Vector layers → exported to a temporary GeoJSON file; the shim points `.source()` at it.  
   - Raster layers → serialised as `{"source": "/original/path.tif", "name": "...", "crs": "EPSG:4326"}`.  
   - CRS → serialised as `{"authid": "EPSG:4326"}`.  
2. The framework writes a `runner.py` and `config.json` to the same temp dir.
3. The subprocess is launched: either `.venv/bin/python runner.py config.json` (uv) or `pixi run python runner.py config.json` (pixi).
4. Inside `runner.py`, **before** importing your app, every `qgis.*` module is replaced with a `MagicMock` (plus specific shims for `QgsProject`, `QgsVectorLayer`, etc.).
5. Your app is imported, `execute_logic(inputs)` is called, and the result is written to `output.json`.
6. The QGIS-side `ProcessMonitor` thread polls for `output.json` and fires `on_finalize()` on the main thread.

### What you CAN do in execute_logic

- Call standard library modules freely (`os`, `pathlib`, `json`, `subprocess`, `urllib`, etc.).
- Import any package installed in your `.venv` or pixi environment.
- Use `osgeo.gdal` / `osgeo.ogr` (available on QGIS Python interpreter for **uv** apps only).
- Call `self.log("message")` — maps to `print()`, appears live in the console window.
- Call `self.set_progress(value, maximum)` — prints `[PROGRESS] v/m` to the console.
- Call `QgsProject.instance().addMapLayer(layer)` — intercepted by the stub, layers are added to QGIS after the subprocess finishes.
- Use `self.app_dir` (a `pathlib.Path`) to read/write config files inside your app folder.

### What you CANNOT do in execute_logic

- Call `iface` — it does not exist in the subprocess.
- Create Qt widgets (no event loop).
- Access live QGIS layers (layers are shims, not real objects).
- Import `qgis.PyQt` or `PyQt5`/`PyQt6` for widget creation.
- Use `QgsVectorFileWriter` to write vector output — it is a no-op stub. Use `osgeo.ogr`, `fiona`, or `geopandas` to write vector files.
- Rely on `self` state persisting between runs — each click spawns a fresh subprocess.

---

## 3. Required File Structure

Every app lives in its own folder under `qgarage/apps/`:

```
qgarage/apps/
└── my_tool/                  ← folder name == app id
    ├── app_meta.json         ← REQUIRED: metadata
    ├── main.py               ← REQUIRED: app class (keep this minimal)
    ├── requirements.txt      ← OPTIONAL: uv backend dependencies
    ├── pixi.toml             ← OPTIONAL: pixi backend dependencies
    └── src/                  ← RECOMMENDED: your actual logic lives here
        ├── __init__.py
        └── processing.py
```

**Rules:**
- The folder name must equal the `"id"` field in `app_meta.json` exactly.
- The folder name must be a valid Python identifier: lowercase, letters, digits, underscores. No hyphens, no spaces.
- `main.py` should be a thin wrapper. All real logic belongs in `src/` modules.
- Either `requirements.txt` or `pixi.toml` triggers the corresponding backend. If both exist, `pixi.toml` takes precedence.
- You may include any additional data files, config files, or assets in the app directory.

---

## 4. app_meta.json Reference

```json
{
    "name": "My Tool",
    "id": "my_tool",
    "version": "1.0.0",
    "author": "Your Name",
    "description": "A short, clear description of what this tool does.",
    "icon_path": "",
    "entry_point": "main.py",
    "class_name": "MyToolApp",
    "tags": ["analysis", "raster"]
}
```

| Field | Required | Rules |
|---|---|---|
| `id` | **Yes** | Must exactly match the folder name. Lowercase, alphanumeric, underscores only. |
| `name` | Yes | Human-readable display name. |
| `version` | Yes | Semantic version string, e.g. `"1.0.0"`. |
| `author` | No | Author name. |
| `description` | No | Shown below the app title in the dashboard UI. |
| `icon_path` | No | Filename of an icon image in the app folder (e.g. `"icon.png"`). Leave `""` for no icon. |
| `entry_point` | No | Defaults to `"main.py"`. Change only if your entry file has a different name. |
| `class_name` | Yes | Must exactly match the class name in your entry point file. Case-sensitive. |
| `tags` | No | List of strings. First tag becomes the Processing Toolbox group name. |

**Common mistake:** Trailing commas in JSON are invalid. The file must be strict JSON.

---

## 5. main.py — The App Class Contract

### The Minimal Template

```python
from qgarage.core.base_app import BaseApp, InputType


class MyToolApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)  # MUST be first, MUST pass **kwargs
        # Declare all inputs here — no Qt widgets, no QGIS API calls
        self.add_input("input_layer", "Input Layer", InputType.VECTOR_LAYER)
        self.add_input("output_folder", "Output Folder", InputType.FOLDER_PATH)

    def execute_logic(self, inputs: dict) -> dict:
        # Delegate to src/ modules. Keep this function short.
        from src.processing import run_analysis
        return run_analysis(inputs, log=self.log)
```

### The __init__ Rules

**Rule 1: `super().__init__(**kwargs)` is always the first line.**

Omitting it or removing `**kwargs` causes the framework to fail when setting `app_meta` and `app_dir`. The app will show an error badge and never open. This is the single most common mistake.

```python
# CORRECT
def __init__(self, **kwargs):
    super().__init__(**kwargs)
    self.add_input(...)

# WRONG — missing **kwargs
def __init__(self):
    super().__init__()  # app_meta and app_dir never set → crash

# WRONG — super() not called first
def __init__(self, **kwargs):
    self.add_input(...)  # _input_specs doesn't exist yet → AttributeError
    super().__init__(**kwargs)
```

**Rule 2: Only declare inputs in `__init__`. No business logic.**

The `__init__` runs on the QGIS main thread at import time. Do not make network calls, read large files, or call QGIS processing APIs here.

**Rule 3: Do not import third-party packages at module top level.**

At load time, QGIS's Python doesn't know about packages in your `.venv`. They are only available inside `execute_logic()` (subprocess) or within functions called from `on_finalize()` (main thread, venv is on `PYTHONPATH`).

```python
# WRONG — fails at import time if 'requests' is not in QGIS's Python
import requests
from qgarage.core.base_app import BaseApp, InputType

class MyApp(BaseApp): ...

# CORRECT — import inside execute_logic where the venv is active
class MyApp(BaseApp):
    def execute_logic(self, inputs):
        import requests  # available because venv is active in the subprocess
        ...
```

### The execute_logic Return Value

Always return a dict. The minimum is:

```python
return {"status": "success", "message": "Done."}
```

On error:

```python
return {"status": "error", "message": "Something went wrong: detailed reason here."}
```

You may include any additional keys. They are passed through to `on_finalize(result)`.

```python
return {
    "status": "success",
    "message": "Processed 42 features.",
    "output_path": "/tmp/result.geojson",
    "feature_count": 42,
}
```

---

## 6. All InputTypes

Declare inputs in `__init__` using:

```python
self.add_input(key, label, input_type, **kwargs)
```

### Full InputType Reference

| InputType | Auto-generated Widget | Value type in execute_logic | Common kwargs |
|---|---|---|---|
| `STRING` | `QLineEdit` | `str` | `default="hello"` |
| `INTEGER` | `QSpinBox` | `int` | `default=1`, `min_value=0`, `max_value=9999` |
| `FLOAT` | `QDoubleSpinBox` | `float` | `default=1.0`, `min_value=0.0`, `max_value=100.0` |
| `BOOLEAN` | `QCheckBox` | `bool` | `default=True` |
| `CHOICE` | `QComboBox` | `str` (selected text) | `choices=["A", "B", "C"]`, `default="A"` |
| `FILE_PATH` | `QgsFileWidget` (file picker) | `str` (absolute path) | `file_filter="GeoTIFF (*.tif);;All Files (*.*)"` |
| `FOLDER_PATH` | `QgsFileWidget` (folder picker) | `str` (absolute path) | — |
| `VECTOR_LAYER` | `QgsMapLayerComboBox` | Shim object (see §7) | — |
| `RASTER_LAYER` | `QgsMapLayerComboBox` | Shim object (see §7) | — |
| `ANY_LAYER` | `QgsMapLayerComboBox` | Shim object (see §7) | — |
| `FIELD` | `QgsFieldComboBox` | `str` (field name) | `linked_layer_key="input_layer"` |
| `CRS` | `QgsProjectionSelectionWidget` | Shim with `.authid()` | — |
| `TEXT_AREA` | `QTextEdit` | `str` | `default="some text"` |

### Shared kwargs for all InputTypes

| kwarg | Type | Default | Purpose |
|---|---|---|---|
| `default` | matches InputType | `None` | Pre-filled value |
| `tooltip` | `str` | `""` | Hover tooltip on the widget |
| `required` | `bool` | `True` | If True, Run is blocked when this field is empty |
| `group` | `str` | `""` | Group label; inputs with the same group share a `QGroupBox` |

### Declarations Examples

```python
# Text input with a default
self.add_input("api_key", "API Key", InputType.STRING,
               tooltip="Your service API key", required=True)

# Integer with bounds
self.add_input("zoom", "Zoom Level", InputType.INTEGER,
               default=12, min_value=0, max_value=22)

# Dropdown
self.add_input("format", "Output Format", InputType.CHOICE,
               choices=["GeoTIFF", "PNG", "JPEG"], default="GeoTIFF")

# File picker filtered to specific types
self.add_input("input_file", "Input File", InputType.FILE_PATH,
               file_filter="GeoTIFF (*.tif *.tiff);;All Files (*.*)")

# Layer input
self.add_input("boundary", "Boundary Layer", InputType.VECTOR_LAYER)

# Field that auto-populates from the selected layer
self.add_input("label_field", "Label Field", InputType.FIELD,
               linked_layer_key="boundary")

# Grouped inputs (creates QGroupBox sections)
self.add_input("input_layer", "Input", InputType.VECTOR_LAYER, group="Input")
self.add_input("filter_field", "Filter Field", InputType.FIELD,
               linked_layer_key="input_layer", group="Input")
self.add_input("output_folder", "Output Folder", InputType.FOLDER_PATH, group="Output")
self.add_input("output_name", "File Name", InputType.STRING,
               default="result", group="Output")
```

---

## 7. Layer and CRS Shim Objects in execute_logic

When a layer input reaches your `execute_logic`, it is **not** a real QGIS layer. It is a lightweight Python object (a "shim") that was deserialised from `inputs.json`. The framework creates these automatically.

### Vector Layer Shim

```python
layer = inputs["my_vector_layer"]

layer.name()          # → str: layer display name
layer.source()        # → str: absolute path to a TEMPORARY GeoJSON export of the layer
layer.crs().authid()  # → str: e.g. "EPSG:4326"
layer.extent().xMinimum()   # → float
layer.extent().xMaximum()   # → float
layer.extent().yMinimum()   # → float
layer.extent().yMaximum()   # → float
layer.featureCount()  # → int
layer.isValid()       # → bool
```

**Important:** `layer.source()` points to a temporary GeoJSON file, not the original data source. Use it as the input to GDAL/OGR/geopandas processing.

### Raster Layer Shim

```python
layer = inputs["my_raster_layer"]

layer.name()          # → str
layer.source()        # → str: path to the ORIGINAL raster file (no conversion)
layer.crs().authid()  # → str
layer.isValid()       # → bool
```

Raster layers pass their original path through unchanged. You can hand `layer.source()` directly to `gdal.Open()`, `gdal.Warp()`, etc.

### CRS Shim

```python
crs = inputs["my_crs"]
crs.authid()    # → str: e.g. "EPSG:32632"
crs.isValid()   # → bool
```

### Reading Vector Features

Do **not** use `QgsVectorLayer` to read features inside `execute_logic`. Instead, use the GeoJSON file that the framework exported:

```python
def execute_logic(self, inputs):
    import json

    layer = inputs["my_layer"]
    geojson_path = layer.source()  # temp GeoJSON file

    with open(geojson_path) as f:
        geojson = json.load(f)

    for feature in geojson["features"]:
        props = feature["properties"]
        geom = feature["geometry"]
        # process...

    return {"status": "success", "message": f"Processed {len(geojson['features'])} features."}
```

Or with geopandas (add `geopandas` to requirements.txt):

```python
def execute_logic(self, inputs):
    import geopandas as gpd

    layer = inputs["my_layer"]
    gdf = gpd.read_file(layer.source())  # reads the temp GeoJSON

    result = gdf[gdf["population"] > 1000]
    output_path = inputs["output_folder"] + "/filtered.geojson"
    result.to_file(output_path, driver="GeoJSON")

    return {"status": "success", "message": f"Saved {len(result)} features.", "output_path": output_path}
```

---

## 8. Returning Results and Loading Layers

### Loading Layers from execute_logic (the easy way)

The recommended method uses `QgsProject.instance().addMapLayer()` inside `execute_logic`. The stub intercepts these calls and replays them on the QGIS main thread after the subprocess exits.

```python
def execute_logic(self, inputs):
    from osgeo import gdal

    # ... processing ...
    output_path = "/tmp/result.tif"
    gdal.Warp(output_path, inputs["dem"].source())

    # This is intercepted and replayed on the QGIS main thread:
    from qgis.core import QgsProject, QgsRasterLayer
    QgsProject.instance().addMapLayer(QgsRasterLayer(output_path, "Result"))

    return {"status": "success", "message": f"Saved to {output_path}"}
```

### Loading Layers from on_finalize (the preferred way)

For cleaner code, return the output path in the result dict and load it in `on_finalize()`, which runs on the QGIS main thread:

```python
def execute_logic(self, inputs):
    # ... processing ...
    return {
        "status": "success",
        "message": "Processing complete.",
        "output_path": "/tmp/result.tif",
        "layer_name": "My Result",
    }

def on_finalize(self, result: dict) -> None:
    if result.get("status") == "success" and result.get("output_path"):
        self.add_output_layer(
            result["output_path"],
            name=result.get("layer_name", "Result"),
        )
```

### add_output_layer Signature

```python
self.add_output_layer(
    source,          # str or Path — file path or data source URI
    name=None,       # str — display name (defaults to file stem)
    provider="ogr",  # str — QGIS provider key
    layer_type="auto",  # "vector", "raster", or "auto"
)
```

`layer_type="auto"` tries raster (gdal) first, then vector (ogr). For explicit control:

```python
self.add_output_layer(output_path, "My Raster", provider="gdal", layer_type="raster")
self.add_output_layer(output_path, "My Vector", provider="ogr", layer_type="vector")
```

### Multiple Output Layers

```python
def execute_logic(self, inputs):
    # ... create multiple output files ...
    return {
        "status": "success",
        "message": "Created 3 output layers.",
        "outputs": [
            {"path": "/tmp/a.tif", "name": "Elevation"},
            {"path": "/tmp/b.tif", "name": "Slope"},
            {"path": "/tmp/c.geojson", "name": "Contours"},
        ],
    }

def on_finalize(self, result: dict) -> None:
    for item in result.get("outputs", []):
        self.add_output_layer(item["path"], item["name"])
```

---

## 9. Good Python Practice — Keep Logic in src/

`main.py` should be a thin wrapper. Real logic belongs in a `src/` package inside your app directory. This makes your code:
- Testable without running QGIS at all
- Reusable across other tools
- Easier to read and maintain
- Easier to review and debug

### Recommended Layout

```
qgarage/apps/my_tool/
├── app_meta.json
├── main.py           ← thin wrapper: only add_input() + delegate to src
├── requirements.txt
└── src/
    ├── __init__.py
    ├── processing.py     ← core algorithm(s)
    ├── downloader.py     ← network I/O
    └── utils.py          ← helpers, constants
```

### How sys.path Works in the Subprocess

The runner adds two paths to `sys.path` before importing your app:
1. The **QGarage plugin parent directory** — so `from qgarage.core.base_app import BaseApp` works.
2. The **app directory** — so `from src.processing import run_analysis` works.

Because `app_dir` is on `sys.path`, any package directory inside your app (like `src/`) is importable by name from within `execute_logic`. You do **not** need to manually manipulate `sys.path`.

```
my_tool/
└── src/
    └── __init__.py   ← makes src a package importable as "src"
    └── logic.py
```

```python
# Inside execute_logic:
from src.logic import do_the_thing   # works because app_dir is on sys.path
```

### Example: Clean main.py

```python
# main.py — keep this file as short as possible
from qgarage.core.base_app import BaseApp, InputType


class SlopeCalculatorApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input("dem", "DEM Raster", InputType.RASTER_LAYER,
                       tooltip="Input digital elevation model")
        self.add_input("output_folder", "Output Folder", InputType.FOLDER_PATH)
        self.add_input("method", "Algorithm", InputType.CHOICE,
                       choices=["Horn", "ZevenbergenThorne"], default="Horn")

    def execute_logic(self, inputs: dict) -> dict:
        from src.slope import calculate_slope   # import inside execute_logic
        return calculate_slope(
            dem_path=inputs["dem"].source(),
            output_folder=inputs["output_folder"],
            method=inputs["method"],
            log=self.log,
        )

    def on_finalize(self, result: dict) -> None:
        if result.get("status") == "success" and result.get("output_path"):
            self.add_output_layer(result["output_path"], "Slope")
```

### Example: src/slope.py

```python
# src/slope.py — real logic, no QGIS, no Qt, testable in isolation
from __future__ import annotations

import os
from pathlib import Path


def calculate_slope(
    dem_path: str,
    output_folder: str,
    method: str,
    log=print,
) -> dict:
    """Calculate slope from a DEM raster.

    Args:
        dem_path: Path to the DEM file (original raster path from shim.source()).
        output_folder: Directory to write the output.
        method: Algorithm name ("Horn" or "ZevenbergenThorne").
        log: Callable used for progress messages (defaults to print for testing).

    Returns:
        QGarage result dict with at least {"status": ..., "message": ...}.
    """
    from osgeo import gdal  # uv apps: gdal available from QGIS Python
                             # pixi apps: must be in pixi.toml [dependencies]

    output_path = os.path.join(output_folder, "slope.tif")
    log(f"Reading DEM: {dem_path}")
    log(f"Writing slope to: {output_path}")

    alg_flag = 1 if method == "ZevenbergenThorne" else 0

    gdal.DEMProcessing(
        destName=output_path,
        srcDS=dem_path,
        processing="slope",
        options=gdal.DEMProcessingOptions(alg=alg_flag),
    )

    if not Path(output_path).exists():
        return {"status": "error", "message": "GDAL DEMProcessing produced no output."}

    log("Done.")
    return {
        "status": "success",
        "message": f"Slope raster written to {output_path}.",
        "output_path": output_path,
    }
```

### Benefits of this pattern

- `calculate_slope()` is a plain Python function — test it with `pytest` without QGIS.
- The `log` parameter defaults to `print`, so tests don't need to mock anything.
- Swapping or upgrading the GDAL call requires no changes to `main.py`.
- Type hints and docstrings live where the code is complex, not in the thin wrapper.

---

## 10. Dependency Backends — uv vs pixi

### When to use uv (requirements.txt)

- Your app needs only pure-Python packages (pandas, requests, geojson, etc.).
- You want to use GDAL, numpy, or scipy as they are already bundled by QGIS Python — you get them for free without listing them.
- You want the fastest possible first-run startup.

**Create `requirements.txt`:**

```
requests>=2.28
pandas>=2.0
geojson>=3.0
# DO NOT list: qgis, PyQt5, PyQt6, gdal, numpy (provided by QGIS Python)
```

The framework runs `uv pip install -r requirements.txt` into a per-app `.venv/` on first run. Subsequent runs reuse the cached venv.

### When to use pixi (pixi.toml)

- Your app needs compiled packages not bundled with QGIS: rasterio, scipy with specific builds, custom GDAL, etc.
- You need a specific Python version independent of QGIS.

**Create `pixi.toml`:**

```toml
[project]
name = "my_tool"
channels = ["conda-forge"]
platforms = ["win-64", "linux-64", "osx-64", "osx-arm64"]

[dependencies]
python = ">=3.11,<3.13"
gdal = ">=3.6"        # must explicitly declare gdal for pixi apps
numpy = "*"           # must explicitly declare numpy for pixi apps
scipy = "*"
rasterio = "*"

[pypi-dependencies]
# Pure-Python PyPI packages:
requests = ">=2.28"
```

**Critical pixi difference:** QGIS's bundled packages (GDAL, numpy, etc.) are **NOT** available in a pixi app's subprocess. Pixi provides its own Python interpreter that knows nothing about the QGIS installation. You must declare every dependency, including ones that are free in uv apps.

### Backend Auto-Detection

The framework checks the app directory:
- `pixi.toml` present → pixi is used (takes precedence if both exist).
- `requirements.txt` present, no `pixi.toml` → uv is used.
- Neither present → uv is used with an empty venv (only stdlib and QGIS Python).

### Environment Location

| Backend | Location |
|---|---|
| uv | `qgarage/apps/my_tool/.venv/` |
| pixi | `qgarage/apps/my_tool/.pixi/envs/default/` |

These are created on first run and cached. Never commit them to version control — add `.venv/` and `.pixi/` to `.gitignore`.

---

## 11. Optional Hooks and Advanced Patterns

### validate_inputs(inputs) → Optional[str]

Called on the QGIS main thread before the subprocess is launched. Return a string to block execution with an error message, or `None` to allow it.

```python
def validate_inputs(self, inputs: dict) -> str | None:
    api_key = inputs.get("api_key", "").strip()
    if not api_key:
        return "API key is required. Enter your key in the API Key field."
    output = inputs.get("output_folder", "")
    if not output:
        return "Please select an output folder."
    return None   # allow execution
```

### on_finalize(result)

Called on the QGIS main thread after the subprocess writes `output.json`. `result` is the dict returned by `execute_logic`. Use this to load output layers, update the project, or display a summary.

```python
def on_finalize(self, result: dict) -> None:
    if result.get("status") == "success":
        for layer_info in result.get("output_files", []):
            self.add_output_layer(layer_info["path"], layer_info["name"])
    elif result.get("status") == "error":
        # The output area already shows the error. Add extra context here if needed.
        pass
```

### on_load() / on_unload()

Called when the app is loaded or unloaded by the registry. Rarely needed.

```python
def on_load(self) -> None:
    # Called once when QGarage registers this app. Use for one-time setup.
    pass

def on_unload(self) -> None:
    # Called when the plugin shuts down or the app is removed.
    pass
```

### Persistent Config / API Key Management

Use `self.app_dir` to read and write a JSON config file alongside your app:

```python
def execute_logic(self, inputs: dict) -> dict:
    import json
    from pathlib import Path

    config_path = Path(str(self.app_dir)) / "config.json"
    api_key = inputs.get("api_key", "").strip()

    if api_key:
        # Save provided key for future runs
        config_path.write_text(json.dumps({"api_key": api_key}))
    elif config_path.exists():
        # Load previously saved key
        api_key = json.loads(config_path.read_text()).get("api_key", "")

    if not api_key:
        return {"status": "error", "message": "No API key provided or saved."}

    # Use api_key ...
    return {"status": "success", "message": "Done."}
```

### Progress Reporting

```python
def execute_logic(self, inputs: dict) -> dict:
    files = [...]  # list of files to process
    total = len(files)

    for i, f in enumerate(files):
        self.log(f"Processing {f} ({i + 1}/{total})")
        # ... process f ...
        self.set_progress(i + 1, total)   # updates the progress bar

    return {"status": "success", "message": f"Processed {total} files."}
```

### Declaring Outputs for the Processing Toolbox

Declarative apps automatically appear in the QGIS Processing Toolbox. To expose specific output values as named Processing outputs, use `add_output()`:

```python
from qgarage.core.base_app import BaseApp, InputType, OutputType

class MyApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input("input_layer", "Input", InputType.VECTOR_LAYER)
        self.add_output("feature_count", "Feature Count", OutputType.INTEGER)
        self.add_output("output_file", "Output File", OutputType.FILE)

    def execute_logic(self, inputs):
        count = inputs["input_layer"].featureCount()
        # ... save output ...
        return {
            "status": "success",
            "message": f"Done: {count} features.",
            "feature_count": count,
            "output_file": "/tmp/result.geojson",
        }
```

Output keys in the return dict must match the `key` argument to `add_output()`.

---

## 12. Dynamic Mode — Custom UI

If you need a multi-step wizard, interactive canvas tool, or live dashboard, override `build_dynamic_widget()` and return a `QWidget`. In this mode:
- `execute_logic()` is **never called** by the framework.
- All logic runs on the QGIS main thread (or threads you manage yourself).
- You have **full access** to the live QGIS API (`iface`, `QgsProject`, `QgsMapCanvas`, etc.).
- The app will **not** appear in the Processing Toolbox (dynamic apps are excluded).

```python
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit
)
from qgarage.core.base_app import BaseApp


class MyInteractiveTool(BaseApp):
    def build_dynamic_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel(self.app_name))

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        layout.addWidget(self._output)

        btn = QPushButton("Analyse Current Project")
        btn.clicked.connect(self._analyse)
        layout.addWidget(btn)

        return widget

    def _analyse(self) -> None:
        # Runs on QGIS main thread — full QGIS API available
        from qgis.core import QgsProject
        project = QgsProject.instance()
        layers = project.mapLayers()
        self._output.setText(f"Project has {len(layers)} layer(s).")

        # You can also use add_output_layer() from here
        # self.add_output_layer("/some/path.tif", "My Layer")
```

**Rules for dynamic mode:**
1. Return a valid `QWidget` from `build_dynamic_widget()`. If any code path returns `None`, the dashboard will silently snap back to the card grid.
2. Do not call QGIS APIs in `build_dynamic_widget()` itself before the widget is fully constructed — do it in slots or `on_load()`.
3. Import from `qgis.PyQt`, never from `PyQt5` or `PyQt6` directly.
4. You are responsible for all threading if you do background work.

---

## 13. Toolboxes — Grouping Multiple Apps

A toolbox is a folder that contains multiple apps, identified by a `toolbox_meta.json` file instead of `app_meta.json`. Apps in a toolbox are displayed under a collapsible card in the dashboard.

### Structure

```
qgarage/apps/
└── hydrology_tools/               ← toolbox folder (id = "hydrology_tools")
    ├── toolbox_meta.json          ← identifies this as a toolbox
    ├── flow_direction/            ← first app
    │   ├── app_meta.json
    │   ├── main.py
    │   └── requirements.txt
    └── watershed_delineation/     ← second app
        ├── app_meta.json
        ├── main.py
        └── requirements.txt
```

### toolbox_meta.json

```json
{
    "name": "Hydrology Tools",
    "id": "hydrology_tools",
    "version": "1.0.0",
    "author": "Your Name",
    "description": "Tools for hydrological analysis.",
    "icon_path": "",
    "tags": ["hydrology", "terrain"]
}
```

The toolbox `id` must match the folder name. Individual apps inside the toolbox follow all the same rules as standalone apps.

---

## 14. Testing Your App Without QGIS

Because `execute_logic()` is plain Python, it is fully testable with `pytest` outside QGIS. The QGarage test suite already mocks the entire `qgis` package — you can use the same approach.

### Minimal Test for src/ Logic

The best tests call your `src/` functions directly. They need no QGIS mocking at all:

```python
# tests/test_my_tool.py
from pathlib import Path
import pytest

# Import directly — no QGIS dependency
from qgarage.apps.my_tool.src.processing import run_analysis


def test_run_analysis_success(tmp_path):
    logs = []
    result = run_analysis(
        dem_path="tests/fixtures/sample_dem.tif",
        output_folder=str(tmp_path),
        method="Horn",
        log=logs.append,   # capture log output without printing
    )
    assert result["status"] == "success"
    assert Path(result["output_path"]).exists()
    assert any("Done" in msg for msg in logs)


def test_run_analysis_missing_file(tmp_path):
    result = run_analysis(
        dem_path="/nonexistent/file.tif",
        output_folder=str(tmp_path),
        method="Horn",
    )
    assert result["status"] == "error"
```

### Testing execute_logic with a Fake Layer

To test `execute_logic` itself, you need to mock the qgis package and provide shim-like objects for layer inputs. The project's `conftest.py` installs the mock automatically when you run `pytest`.

```python
# tests/test_my_app.py
import json
from pathlib import Path
from qgarage.apps.my_tool.main import MyToolApp

MINIMAL_META = {
    "id": "my_tool",
    "name": "My Tool",
    "version": "1.0.0",
    "description": "Test",
    "entry_point": "main.py",
    "class_name": "MyToolApp",
    "tags": [],
}


class FakeLayer:
    """Minimal shim matching what the subprocess runner provides."""
    def __init__(self, source_path):
        self._source = source_path

    def source(self): return self._source
    def name(self): return "test_layer"
    def featureCount(self): return 3
    def isValid(self): return True
    def crs(self):
        class FakeCrs:
            def authid(self): return "EPSG:4326"
        return FakeCrs()


def test_execute_logic(tmp_path):
    app = MyToolApp(app_meta=MINIMAL_META, app_dir=Path("qgarage/apps/my_tool"))

    # Provide a fake GeoJSON file for the layer source
    geojson = {"type": "FeatureCollection", "features": []}
    layer_path = tmp_path / "layer.geojson"
    layer_path.write_text(json.dumps(geojson))

    inputs = {
        "input_layer": FakeLayer(str(layer_path)),
        "output_folder": str(tmp_path),
    }

    result = app.execute_logic(inputs)
    assert result["status"] == "success"
```

### Run the Tests

```bash
uv run pytest
```

---

## 15. Complete Reference App (Well-Structured)

This example demonstrates all best practices in a real-world scenario. The app downloads elevation data for a selected area and returns the raster.

### File Layout

```
qgarage/apps/dem_downloader/
├── app_meta.json
├── main.py           ← thin wrapper only
├── requirements.txt
└── src/
    ├── __init__.py
    ├── downloader.py     ← HTTP download logic
    └── postprocess.py    ← GDAL reprojection
```

### app_meta.json

```json
{
    "name": "DEM Downloader",
    "id": "dem_downloader",
    "version": "1.0.0",
    "author": "Your Name",
    "description": "Downloads a DEM tile for a selected area and loads it into QGIS.",
    "icon_path": "",
    "entry_point": "main.py",
    "class_name": "DemDownloaderApp",
    "tags": ["elevation", "download", "raster"]
}
```

### requirements.txt

```
requests>=2.28
# gdal and numpy are provided by QGIS Python — do NOT list them here
```

### main.py

```python
"""DEM Downloader — thin app wrapper.

All business logic lives in src/. This file only declares inputs,
delegates to src/, and handles post-run layer loading.
"""

from qgarage.core.base_app import BaseApp, InputType


class DemDownloaderApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input(
            "area",
            "Area of Interest",
            InputType.VECTOR_LAYER,
            tooltip="Vector layer defining the bounding box for the download.",
        )
        self.add_input(
            "output_folder",
            "Output Folder",
            InputType.FOLDER_PATH,
            tooltip="Where to save the downloaded DEM file.",
        )
        self.add_input(
            "output_name",
            "Output Name",
            InputType.STRING,
            default="dem",
            tooltip="Filename (without extension) for the output raster.",
        )
        self.add_input(
            "target_crs",
            "Target CRS",
            InputType.CRS,
            tooltip="Reproject the output to this CRS. Leave as EPSG:4326 for no reprojection.",
        )

    def validate_inputs(self, inputs: dict) -> str | None:
        if not inputs.get("output_folder"):
            return "Please select an output folder."
        return None

    def execute_logic(self, inputs: dict) -> dict:
        # Import src modules here — inside execute_logic where the venv is active
        from src.downloader import download_dem
        from src.postprocess import reproject_raster

        area = inputs["area"]
        extent = area.extent()
        bbox = (
            extent.xMinimum(),
            extent.yMinimum(),
            extent.xMaximum(),
            extent.yMaximum(),
        )
        crs = area.crs().authid()

        self.log(f"Area: {bbox} ({crs})")
        self.log(f"Downloading DEM tiles...")

        raw_path = download_dem(
            bbox=bbox,
            source_crs=crs,
            output_folder=inputs["output_folder"],
            name=inputs["output_name"],
            log=self.log,
        )
        if raw_path is None:
            return {"status": "error", "message": "Download failed. Check the console for details."}

        target_crs = inputs["target_crs"].authid()
        if target_crs != "EPSG:4326":
            self.log(f"Reprojecting to {target_crs}...")
            final_path = reproject_raster(raw_path, target_crs, log=self.log)
        else:
            final_path = raw_path

        self.log("Done!")
        return {
            "status": "success",
            "message": f"DEM saved to {final_path}",
            "output_path": final_path,
            "layer_name": inputs["output_name"],
        }

    def on_finalize(self, result: dict) -> None:
        if result.get("status") == "success" and result.get("output_path"):
            self.add_output_layer(
                result["output_path"],
                name=result.get("layer_name", "DEM"),
                layer_type="raster",
            )
```

### src/__init__.py

```python
# Empty — makes src/ a Python package so `from src.downloader import ...` works.
```

### src/downloader.py

```python
"""HTTP download logic for DEM tiles.

Pure Python — no QGIS, no Qt. Fully testable in isolation.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable
from urllib.request import urlretrieve


def download_dem(
    bbox: tuple[float, float, float, float],
    source_crs: str,
    output_folder: str,
    name: str,
    log: Callable[[str], None] = print,
) -> str | None:
    """Download a DEM tile covering bbox and save it to output_folder.

    Returns the absolute path of the downloaded file, or None on failure.
    """
    xmin, ymin, xmax, ymax = bbox
    url = (
        f"https://example.com/dem?bbox={xmin},{ymin},{xmax},{ymax}&crs={source_crs}"
    )

    output_path = os.path.join(output_folder, f"{name}.tif")
    log(f"Fetching: {url}")

    try:
        urlretrieve(url, output_path)
    except Exception as exc:
        log(f"[ERROR] Download failed: {exc}")
        return None

    if not Path(output_path).exists():
        log("[ERROR] Download produced no file.")
        return None

    size_mb = Path(output_path).stat().st_size / 1_048_576
    log(f"Downloaded {size_mb:.1f} MB → {output_path}")
    return output_path
```

### src/postprocess.py

```python
"""GDAL-based raster postprocessing.

Pure Python — no QGIS, no Qt. GDAL is available in uv apps for free.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable


def reproject_raster(
    input_path: str,
    target_crs: str,
    log: Callable[[str], None] = print,
) -> str:
    """Reproject a raster to target_crs using GDAL.

    Returns the path to the reprojected raster.
    """
    from osgeo import gdal

    output_path = str(Path(input_path).with_suffix("")) + f"_{target_crs.replace(':', '_')}.tif"
    log(f"Reprojecting to {target_crs} → {output_path}")

    warp_options = gdal.WarpOptions(dstSRS=target_crs, format="GTiff")
    result = gdal.Warp(output_path, input_path, options=warp_options)
    if result is None:
        raise RuntimeError(f"gdal.Warp failed for {input_path}")

    result.FlushCache()
    result = None  # close file handle
    log("Reprojection complete.")
    return output_path
```

---

## 16. Diagnostic Guide — Why Doesn't It Open?

Work through these checks in order. Each one corresponds to a real failure mode in the framework source.

### Check 1: Error or Crashed badge on the card

The app failed to **load** (import or `__init__` raised an exception). Most common causes:

| Symptom | Cause | Fix |
|---|---|---|
| `TypeError: __init__() got unexpected keyword argument 'app_meta'` | `super().__init__(**kwargs)` missing or `**kwargs` not passed | Add `super().__init__(**kwargs)` as the very first line |
| `AttributeError: 'MyApp' object has no attribute '_input_specs'` | `add_input()` called before `super().__init__()` | Move `super().__init__(**kwargs)` above all `add_input()` calls |
| `AttributeError: type object '...' has no attribute '...'` | `"class_name"` in `app_meta.json` does not match the class in `main.py` | Fix the spelling — it is case-sensitive |
| `FileNotFoundError: Entry point main.py not found` | The `entry_point` file doesn't exist, or `id` doesn't match the folder | Rename folder or fix `"id"` field |
| `ImportError: No module named 'mypackage'` at load time | Top-level import of a third-party package | Move the import inside `execute_logic()` |
| `SyntaxError` | Python syntax error in `main.py` | Run `python -m py_compile main.py` to find it |
| `json.JSONDecodeError` | Invalid `app_meta.json` | Validate with a JSON linter (no trailing commas) |

To see the full error traceback, open the QGIS Python Console (Plugins → Python Console) — QGarage logs exceptions there.

### Check 2: No badge, but clicking Open snaps back to the card grid

The app loaded successfully but `build_widget()` (or `build_dynamic_widget()`) crashed. Check the QGIS Python Console for the traceback. Common causes:
- `build_dynamic_widget()` returns `None` on some code path instead of a `QWidget`.
- An exception is raised inside `build_dynamic_widget()`.

### Check 3: Run button does nothing

- A required input is empty. Fill all required fields before clicking Run.
- `validate_inputs()` returned an error. Check the output area below the form.

### Check 4: Console window never appears

- `uv` or `pixi` is not installed or the path in QGarage settings is wrong.
- `requirements.txt` has an unresolvable package. Run `uv pip install -r requirements.txt` manually to check.
- `pixi.toml` has an invalid dependency. Run `pixi install --manifest-path pixi.toml` manually.

### Check 5: Console window appears but immediately crashes

Open the console window (it stays open after failure). Look for the traceback. Common causes:
- An import at module top-level in `main.py` failed in the subprocess.
- `app_meta.json` `"class_name"` doesn't match the class (detected at runtime inside the runner).
- A `src/` import fails because `src/__init__.py` is missing (not a package).

### Check 6: execute_logic runs but returns wrong results

- Check `layer.source()` — for vector layers this is a temporary GeoJSON path, not the original file.
- For pixi apps, remember GDAL/numpy must be declared in `pixi.toml`.
- Make sure `execute_logic` returns a dict (not `None`, not a string).

---

## 17. Quick Checklist

Use this before considering an app complete.

**app_meta.json**
- [ ] `"id"` exactly matches the folder name (lowercase, underscores only).
- [ ] `"class_name"` exactly matches the class in `main.py` (case-sensitive).
- [ ] `"entry_point"` file exists in the app folder.
- [ ] File is valid JSON (no trailing commas, all strings double-quoted).

**main.py**
- [ ] `super().__init__(**kwargs)` is the very first line of `__init__`.
- [ ] All `add_input()` calls come after `super().__init__(**kwargs)`.
- [ ] No third-party imports at module top-level.
- [ ] No Qt widget creation, no QGIS API calls in `__init__`.
- [ ] `execute_logic` returns a dict with at least `{"status": ..., "message": ...}`.
- [ ] `execute_logic` delegates to `src/` — it is short and readable.

**src/ layout**
- [ ] `src/__init__.py` exists (makes `from src.module import X` work).
- [ ] Each `src/` function accepts a `log=print` parameter for testability.
- [ ] No Qt or QGIS imports in `src/` files (they run in the subprocess).
- [ ] Third-party imports (`from osgeo import gdal`) are inside functions, not at module top-level (in case the module is also used in tests).

**Dependencies**
- [ ] `requirements.txt` or `pixi.toml` exists (even if empty).
- [ ] QGIS-bundled packages (gdal, numpy) are NOT in `requirements.txt` (they are free for uv apps).
- [ ] Pixi apps declare every dependency including gdal and numpy.
- [ ] If you have both `requirements.txt` and `pixi.toml`, know that pixi takes precedence.

**Layer handling**
- [ ] Vector layer data is read from `layer.source()` (a GeoJSON path), not via QGIS API.
- [ ] Raster layer data is read from `layer.source()` (original file path).
- [ ] Output layers are loaded in `on_finalize()` via `self.add_output_layer()`, or via `QgsProject.instance().addMapLayer()` inside `execute_logic`.

**Testing**
- [ ] `src/` functions can be imported and called from `pytest` without QGIS running.
- [ ] Tests pass with `uv run pytest`.
