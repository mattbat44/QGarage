# QHub - QGIS Plugin Architecture

## Overview
QHub is a modular app-hosting framework for QGIS (3.28+ / 4.0). It provides a dashboard where users install, manage, and run isolated mini-tools ("Apps").

## Key Files
- `qhub/plugin.py` — QGIS plugin entry (initGui/unload), wires all components
- `qhub/core/base_app.py` — BaseApp ABC with declarative `add_input()` + `execute_logic()`
- `qhub/core/app_loader.py` — Dynamic importlib loading with try/except fault isolation
- `qhub/core/uv_bridge.py` — uv venv creation, pip install, SysPathContext for sys.path injection
- `qhub/core/app_registry.py` — Discovers apps in `qhub/apps/`, tracks AppEntry + AppHealth
- `qhub/ui/dashboard_dock.py` — Main QgsDockWidget with card grid + app host (QStackedWidget)
- `qhub/ui/app_card_widget.py` — Individual app cards with state badges
- `qhub/ui/app_host_widget.py` — Container for running app's auto-generated UI
- `qhub/themes/theme_manager.py` — Dark/light detection via QPalette luminance
- `qhub/workers/download_worker.py` — QThread workers for ZIP download + local folder install

## Conventions
- All Qt imports via `qgis.PyQt` (never `PyQt5`/`PyQt6` directly) for QGIS 3.x/4.0 compat
- QSS applied at widget level only (never QApplication global)
- Each app gets its own `.venv/` managed by `uv`
- App contract: `app_meta.json` + `main.py` (BaseApp subclass) + `requirements.txt`

## Deploying
```powershell
.\install-qhub-plugin.ps1
```

## Testing
```bash
uv run pytest
```
