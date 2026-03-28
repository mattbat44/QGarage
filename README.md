# QGarage — Modular App-Hosting Framework for QGIS

A lightweight plugin for QGIS (3.28+) that provides a unified dashboard for installing, managing, and running isolated mini-tools ("Apps"). QGarage enables rapid development and deployment of geospatial analysis tools without the overhead of traditional QGIS plugin architecture.

## ✨ Key Features

- **📦 Modular App System** — Install and manage multiple self-contained tools from a single dashboard
- **🔒 Process Isolation** — Each app runs in its own subprocess with a clean Python environment (via `uv`)
- **⚡ Zero-Install Dependencies** — Python packages are resolved at runtime; no pre-installation overhead
- **🎨 Auto-Generated UI** — Declarative input system automatically creates professional Qt forms
- **🎯 Simplified Development** — Write a `BaseApp` subclass with `add_input()` + `execute_logic()` — no QGIS boilerplate needed
- **🔧 Dynamic Mode** — For advanced use cases, build custom multi-step wizards and interactive tools
- **💾 Smart Parameter Caching** — Automatically remember last-used parameters and maintain run history
- **📂 Rich Input Types** — Vector layers, raster layers, CRS, files, folders, fields, text areas, dropdowns, and more
- **🗺️ Direct Layer Delivery** — Return results directly to the QGIS map canvas via `add_output_layer()`
- **🔌 Easy Installation** — Install apps from ZIP files or local folders without manual setup

## 📋 Requirements

- **QGIS** 3.28 or later (including QGIS 4.0)
- **Python** 3.10+ (included with QGIS)
- **uv** — Fast Python package manager ([installation](https://github.com/astral-sh/uv))
  - On Windows: `python -m pip install uv` or download from [uv releases](https://github.com/astral-sh/uv/releases)
  - On Windows with PowerShell: `.\install-qgarage-plugin.ps1` detects and configures uv automatically

## 🚀 Installation

Use the QGIS Plugin Manager and install the latest version of QGarage

## 📖 Quick Start

### 1. Launch QGarage

In QGIS, click the QGarage icon in the toolbar (or **Plugins → QGarage → QGarage Dashboard**). A docked panel appears on the right showing available apps.

### 2. Install a Sample App

Click **"+ Install"** to open the installer dialog. Select:

- **From ZIP**: Download an app as a ZIP file and install it directly
- **From Folder**: Point to a local folder containing `app_meta.json` + `main.py`

The sample **Hello World** app is included — try it to understand the app structure.

### 3. Run an App

Click an app card to view its UI. Fill in the inputs and click **Run**. The app:
- Validates your inputs
- Executes business logic in an isolated subprocess
- Returns results and optionally adds layers to your map

### 4. Create Your Own App

See [Creating Your First App](#creating-your-first-app) below.

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────┐
│         QGIS (Main Thread)                  │
│  ┌─────────────────────────────────────────┐│
│  │ QGarage Plugin (qgarage/plugin.py)      ││
│  ├─────────────────────────────────────────┤│
│  │ Dashboard Dock | App Cards | App Host  ││
│  └─────────────────────────────────────────┘│
│                                             │
│  Registry | Loader | Theme Manager         │
└─────────────────────────────────────────────┘
           ↓ (launches)
┌─────────────────────────────────────────────┐
│   App Subprocess (uv run --isolated)        │
│                                             │
│  Business Logic | QGIS Stubs | File I/O   │
│                                             │
│  (Input JSON) ← (Output JSON)               │
└─────────────────────────────────────────────┘
```

### Key Components

| Component                          | Purpose                                                  |
|:-----------------------------------|:---------------------------------------------------------|
| `qgarage/plugin.py`                | QGIS entry point; wires UI, registry, and app loader   |
| `qgarage/core/base_app.py`         | Abstract base class for all apps (`add_input()` + `execute_logic()`) |
| `qgarage/core/app_registry.py`     | Discovers, loads, and tracks app health                |
| `qgarage/core/app_loader.py`       | Dynamic import with fault isolation                    |
| `qgarage/core/uv_bridge.py`        | Manages `uv` venv creation and subprocess execution    |
| `qgarage/ui/dashboard_dock.py`     | Main QgsDockWidget with app card grid                  |
| `qgarage/ui/app_host_widget.py`    | Container for running app's auto-generated UI          |
| `qgarage/themes/theme_manager.py`  | Dark/light theme detection and application            |
| `qgarage/workers/download_worker.py` | QThread workers for app installation                   |

## 📱 Creating Your First App

### Minimal Example

Create a folder `qgarage/apps/hello_world/` with three files:

#### 1. `app_meta.json`
```json
{
  "name": "Hello World",
  "id": "hello_world",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "A simple introductory app.",
  "icon_path": "",
  "entry_point": "main.py",
  "class_name": "HelloWorldApp",
  "tags": ["example"]
}
```

#### 2. `main.py`
```python
from qgarage.core.base_app import BaseApp, InputType


class HelloWorldApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input("name", "Your Name", InputType.STRING, default="World")
        self.add_input("count", "Repeat Count", InputType.INTEGER, default=1, min_value=1, max_value=10)

    def execute_logic(self, inputs):
        name = inputs["name"]
        count = inputs["count"]

        for i in range(count):
            self.log(f"Hello, {name}! (iteration {i + 1})")

        return {
            "status": "success",
            "message": f"Greeted {name} {count} time(s)."
        }
```

#### 3. `requirements.txt` (optional)
```
# Leave empty if your app uses only standard library + QGIS
```

### Deploy & Run

```powershell
.\install-qgarage-plugin.ps1
```

Then in QGIS:
1. Open the QGarage dashboard
2. Look for "Hello World" in the app grid
3. Fill in your name and click **Run**
4. Watch the console window and the results in QGarage

## 💡 Common App Patterns

### Pattern 1: Vector/Raster Processing

```python
class ProcessVectorApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input("input_layer", "Input Vector", InputType.VECTOR_LAYER)
        self.add_input("output_folder", "Output Folder", InputType.FOLDER_PATH)

    def execute_logic(self, inputs):
        # The layer arrives as a shim with .source() (GeoJSON path), .name(), .crs(), etc.
        layer = inputs["input_layer"]
        output_folder = inputs["output_folder"]

        self.log(f"Processing layer: {layer.name()}")

        # Read GeoJSON from layer.source()
        import json
        with open(layer.source()) as f:
            geojson = json.load(f)

        # Process features...
        feature_count = len(geojson.get("features", []))
        self.log(f"Found {feature_count} features")

        return {"status": "success", "message": "Processing complete"}
```

### Pattern 2: Download + Process + Load to Map

```python
def execute_logic(self, inputs):
    # ... download and process ...

    # Auto-load result to QGIS (on main thread after subprocess completes)
    from qgis.core import QgsProject, QgsRasterLayer
    QgsProject.instance().addMapLayer(QgsRasterLayer(output_path, "My Result"))

    return {"status": "success", "message": f"Saved and loaded: {output_path}"}
```

Or prefer `on_finalize()` for cleaner code:

```python
def execute_logic(self, inputs):
    # ... processing ...
    return {"status": "success", "output_path": "/tmp/result.tif"}

def on_finalize(self, result):
    if result.get("status") == "success":
        self.add_output_layer(result["output_path"], "Result")
```

### Pattern 3: API Key Management

```python
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

### Pattern 4: Dynamic Custom UI

For multi-step wizards, interactive tools, or live dashboards:

```python
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit
from qgarage.core.base_app import BaseApp

class DynamicApp(BaseApp):
    def build_dynamic_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel("Custom UI"))

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        layout.addWidget(self._output)

        run_btn = QPushButton("Run Analysis")
        run_btn.clicked.connect(self._on_run)
        layout.addWidget(run_btn)

        return widget

    def _on_run(self):
        # Runs on QGIS main thread — full QGIS API access
        from qgis.core import QgsProject
        layer_count = len(QgsProject.instance().mapLayers())
        self._output.setText(f"Project has {layer_count} layers")
```

In dynamic mode:
- `execute_logic()` is **not** called
- You have **full QGIS API** access
- You manage your own UI and threading
- Perfect for interactive or real-time tools

## 📚 Input Types

The declarative system supports these input types:

| InputType      | Widget                         | Python Type | Example                                  |
|:---------------|:-------------------------------|:------------|:-----------------------------------------|
| `STRING`       | `QLineEdit`                    | `str`       | `self.add_input("name", "Name", InputType.STRING)` |
| `INTEGER`      | `QSpinBox`                     | `int`       | `self.add_input("count", "Count", InputType.INTEGER, min_value=1, max_value=10)` |
| `FLOAT`        | `QDoubleSpinBox`               | `float`     | `self.add_input("threshold", "Threshold", InputType.FLOAT)` |
| `BOOLEAN`      | `QCheckBox`                    | `bool`      | `self.add_input("apply_filter", "Apply Filter", InputType.BOOLEAN, default=True)` |
| `CHOICE`       | `QComboBox`                    | `str`       | `self.add_input("method", "Method", InputType.CHOICE, choices=["A", "B", "C"])` |
| `FILE_PATH`    | `QgsFileWidget`                | `str`       | `self.add_input("file", "Input File", InputType.FILE_PATH, file_filter="GeoTIFF (*.tif)")` |
| `FOLDER_PATH`  | `QgsFileWidget`                | `str`       | `self.add_input("output", "Output Folder", InputType.FOLDER_PATH)` |
| `VECTOR_LAYER` | `QgsMapLayerComboBox`          | Shim        | `self.add_input("layer", "Vector Layer", InputType.VECTOR_LAYER)` |
| `RASTER_LAYER` | `QgsMapLayerComboBox`          | Shim        | `self.add_input("dem", "DEM Raster", InputType.RASTER_LAYER)` |
| `ANY_LAYER`    | `QgsMapLayerComboBox`          | Shim        | `self.add_input("layer", "Any Layer", InputType.ANY_LAYER)` |
| `FIELD`        | `QgsFieldComboBox`             | `str`       | `self.add_input("field", "Attribute Field", InputType.FIELD, linked_layer_key="layer")` |
| `CRS`          | `QgsProjectionSelectionWidget` | Shim        | `self.add_input("crs", "Coordinate System", InputType.CRS)` |
| `TEXT_AREA`    | `QTextEdit`                    | `str`       | `self.add_input("notes", "Notes", InputType.TEXT_AREA)` |

**Layer and CRS shims** in the subprocess have:
- `.name()` — layer/CRS name
- `.source()` — file path (for vectors: temporary GeoJSON export)
- `.crs().authid()` — CRS code like `"EPSG:4326"`
- `.extent()` — bounding box (vectors only), with `.xMinimum()`, `.yMinimum()`, etc.
- `.featureCount()` — number of features (vectors only)

## 🔍 Key Concepts

### Subprocess Isolation

Each app's `execute_logic()` runs in a **separate Python process** via `uv run --isolated`:

- **Inputs** are serialized to `inputs.json` (layers → GeoJSON exports)
- **Outputs** are written to `output.json` and read back on the main thread
- **QGIS objects are stubbed** — you get lightweight shims, not live QGIS APIs
- **Progress is live** — `self.log()` calls appear in real time in a subprocess console window
- **No blocking** — the QGIS main thread remains responsive

### Parameter Caching & History

Every app automatically:
- **Remembers last-used parameters** (saved to `QgsSettings`)
- **Maintains run history** (up to 20 recent parameter sets)
- Shows a **History dropdown** to restore previous runs

No code changes needed — it's automatic.

### App Lifecycle

1. **Discovery**: `AppRegistry` scans `qgarage/apps/` for folders with `app_meta.json`
2. **Load**: App class is imported, `__init__` runs, inputs are declared
3. **Build UI**: For declarative apps, a form is auto-generated; for dynamic apps, `build_dynamic_widget()` is called
4. **Run**: User clicks **Run**
   - `validate_inputs()` is called (optional; block execution if needed)
   - Inputs are serialized and passed to subprocess
   - `execute_logic()` runs in subprocess (or you handle it in dynamic mode)
   - Results are written to JSON
   - `on_finalize()` is called on main thread (optional; use to load layers)
5. **Unload**: App is unloaded when the plugin shuts down

## 🧪 Testing & Development

### Run Tests

```bash
uv run pytest
```

### Develop Locally

1. Install dependencies:
   ```bash
   uv pip install -e .
   ```

2. Deploy plugin:
   ```powershell
   .\install-qgarage-plugin.ps1
   ```

3. Reload plugin in QGIS (Plugins → Manage and Install Plugins → Reinstall)

### Example Test

```python
# tests/test_hello_world.py
from qgarage.apps.hello_world.main import HelloWorldApp

def test_hello_world_app():
    app = HelloWorldApp()
    result = app.execute_logic({"name": "Test", "count": 2})

    assert result["status"] == "success"
    assert "Greeted Test 2 time(s)" in result["message"]
```

## 📦 File Structure

```
qgarage/
├── plugin.py                           # QGIS plugin entry point
├── core/
│   ├── base_app.py                     # BaseApp ABC + InputType enum
│   ├── app_registry.py                 # App discovery & loading
│   ├── app_loader.py                   # Dynamic import with error handling
│   ├── uv_bridge.py                    # uv venv/subprocess management
│   ├── subprocess_runner.py            # Subprocess execution & communication
│   ├── settings.py                     # QgsSettings integration
│   ├── logger.py                       # Logging utilities
│   └── ...
├── ui/
│   ├── dashboard_dock.py               # Main docked widget
│   ├── app_card_widget.py              # Individual app card
│   ├── app_host_widget.py              # App UI container
│   ├── install_dialog.py               # App installer dialog
│   ├── scaffold_dialog.py              # New app scaffolder
│   └── ...
├── themes/
│   └── theme_manager.py                # Dark/light theme support
├── workers/
│   └── download_worker.py              # Async download/install
├── resources/
│   ├── icon.svg                        # Plugin icon
│   └── templates/
│       └── app_template/               # New app scaffolder template
├── apps/
│   ├── hello_world/                    # Example app
│   │   ├── app_meta.json
│   │   ├── main.py
│   │   └── requirements.txt
│   ├── ...
└── pyproject.toml                      # Project config
```

## 🛠️ Advanced Topics

### Input Grouping

Group related inputs in a `QGroupBox`:

```python
self.add_input("input_layer", "Input", InputType.VECTOR_LAYER, group="Input")
self.add_input("field", "Field", InputType.FIELD, linked_layer_key="input_layer", group="Input")
self.add_input("output_path", "Output Path", InputType.FILE_PATH, group="Output")
```

### Linked Inputs

For `FIELD` type, use `linked_layer_key` to auto-update field choices when a layer changes:

```python
self.add_input("layer", "Layer", InputType.VECTOR_LAYER)
self.add_input("field", "Attribute Field", InputType.FIELD, linked_layer_key="layer")
```

### Input Validation

Override `validate_inputs()` to block execution:

```python
def validate_inputs(self, inputs):
    if not inputs.get("output_folder"):
        return "Output folder is required"
    if not inputs.get("input_layer"):
        return "Please select a layer"
    return None  # Allow execution
```

### Custom Progress Tracking

In `execute_logic()`:

```python
def execute_logic(self, inputs):
    total_steps = 100
    for i in range(total_steps):
        # ... do work ...
        self.set_progress(i + 1, total_steps)

    return {"status": "success", "message": "Done"}
```

### Working with GDAL

Since the subprocess uses QGIS's Python interpreter, GDAL/OSGeo4W libraries are available:

```python
def execute_logic(self, inputs):
    from osgeo import gdal

    dem = inputs["dem"]
    output_path = inputs["output_path"]

    # GDAL operations
    gdal.Warp(output_path, dem.source(), format="GTiff")

    return {"status": "success", "message": f"Saved to {output_path}"}
```

## 🐛 Troubleshooting

### App doesn't appear in dashboard

1. Check that the folder is in `qgarage/apps/<app_id>/`
2. Verify `app_meta.json` is valid JSON (no trailing commas)
3. Ensure `"id"` matches the folder name
4. Restart QGIS or click the **Refresh** button

### App shows "Error" or "Crashed" badge

1. Open QGIS → **Plugins → Python Console**
2. Look for error messages logged by QGarage
3. Common fixes:
   - Check that `super().__init__(**kwargs)` is the first line of `__init__`
   - Ensure `"class_name"` in `app_meta.json` matches the class name exactly (case-sensitive)
   - Move third-party imports inside `execute_logic()` if they aren't on QGIS's `sys.path`
   - Run `python -m py_compile main.py` to check for syntax errors

### Subprocess window never appears or closes immediately

1. Check that `uv` is installed and configured in QGarage settings
2. Verify `requirements.txt` contains only resolvable pure-Python packages
3. Look for errors in the QGIS Python Console

### Layer inputs return `None`

1. Ensure a layer is selected in the input widget before clicking **Run**
2. For `FIELD` type, verify `linked_layer_key` matches the layer input key
3. Check that layer is a valid QGIS layer (not a broken reference)

## 📚 Documentation

For detailed development guides, see:

- `qgarage/QHUB_APP_DEVELOPMENT.instructions.md` — Comprehensive app development guide with patterns and troubleshooting
- `CLAUDE.md` — Project architecture & conventions

## 🤝 Contributing

Contributions are welcome! Areas for enhancement:

- **New input types** (e.g., `MULTI_SELECT_LAYER`, `DATE_PICKER`)
- **App marketplace** — centralized app repository
- **Enhanced caching** — smarter parameter recall and UI state
- **Performance improvements** — faster app discovery, subprocess startup
- **Documentation** — examples, tutorials, video walkthroughs
- **Bug reports & fixes** — issue triaging and PR reviews

To contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Add tests for new functionality
4. Run `uv run pytest` to verify
5. Submit a pull request

## 📜 License

QGarage is licensed under the **GNU General Public License v2.0** — see `LICENSE` for details.

This ensures that QGarage and all apps built with it remain free and open-source software.

## 🙋 Support

- **Issues & Feature Requests** — Use the GitHub Issues tab
- **Documentation** — See `qgarage/QHUB_APP_DEVELOPMENT.instructions.md` for app development

---
