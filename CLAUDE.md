# QGarage - QGIS Plugin Architecture

## Overview
QGarage is a modular app-hosting framework for QGIS (3.28+ / 4.0). It provides a dashboard where users install, manage, and run isolated mini-tools ("Apps"). Apps can be accessed both via the QGarage dashboard UI and the QGIS Processing Toolbox.

## Key Files
- `qgarage/plugin.py` — QGIS plugin entry (initGui/unload), wires all components
- `qgarage/core/base_app.py` — BaseApp ABC with declarative `add_input()` + `execute_logic()`
- `qgarage/core/app_loader.py` — Dynamic importlib loading with try/except fault isolation
- `qgarage/core/uv_bridge.py` — uv venv creation, pip install, SysPathContext for sys.path injection
- `qgarage/core/app_registry.py` — Discovers apps in `qgarage/apps/`, tracks AppEntry + AppHealth
- `qgarage/processing/processing_provider.py` — QgsProcessingProvider that registers declarative apps
- `qgarage/processing/algorithm_wrapper.py` — Wraps BaseApp as QgsProcessingAlgorithm
- `qgarage/processing/parameter_mapper.py` — Maps InputType to QgsProcessingParameter types
- `qgarage/ui/dashboard_dock.py` — Main QgsDockWidget with card grid + app host (QStackedWidget)
- `qgarage/ui/app_card_widget.py` — Individual app cards with state badges
- `qgarage/ui/app_host_widget.py` — Container for running app's auto-generated UI
- `qgarage/themes/theme_manager.py` — Dark/light detection via QPalette luminance
- `qgarage/workers/download_worker.py` — QThread workers for ZIP download + local folder install

## Conventions
- All Qt imports via `qgis.PyQt` (never `PyQt5`/`PyQt6` directly) for QGIS 3.x/4.0 compat
- QSS applied at widget level only (never QApplication global)
- Each app gets its own `.venv/` managed by `uv`
- App contract: `app_meta.json` + `main.py` (BaseApp subclass) + `requirements.txt`
- Declarative apps (with `add_input()` + `execute_logic()`) automatically appear in both the dashboard and Processing Toolbox
- Dynamic apps (with `build_dynamic_widget()`) only appear in the dashboard, not in Processing

## Processing Framework Integration
QGarage apps with declarative inputs are automatically exposed as QGIS Processing algorithms:
- `QGarageProcessingProvider` registers with `QgsApplication.processingRegistry()`
- Each declarative BaseApp becomes a `BaseAppAlgorithm` (subclass of `QgsProcessingAlgorithm`)
- InputType → QgsProcessingParameter mapping in `parameter_mapper.py`
- Apps can be used in batch mode, graphical models, and Python scripts via `processing.run()`
- The same `execute_logic()` method is called whether run from dashboard or Processing

## Deploying
```powershell
.\install-qgarage-plugin.ps1
```

## Testing
```bash
uv run pytest
```
