# Environment Setup Architecture

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  QGIS Plugin Initialization (plugin.py::initGui)                │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┴────────────────────┐
        │                                         │
   ┌────▼─────┐                            ┌──────▼──────┐
   │ UvBridge │                            │ PixiBridge  │
   └────┬─────┘                            └──────┬──────┘
        │                                         │
        └─── Both fail? ───────────────────────┬──┘
                                               │
                                    ┌──────────▼──────────┐
                                    │  registry = None    │
                                    └──────────┬──────────┘
                                               │
                        ┌──────────────────────▼──────────────────────┐
                        │  dashboard.set_registry(registry)           │
                        │  (called regardless of registry status)     │
                        └──────────────────────┬──────────────────────┘
                                               │
                        ┌──────────────────────▼──────────────────────┐
                        │  Registry is None AND tools not ready?      │
                        └──────────┬───────────────────────┬──────────┘
                                   │                       │
                              Yes  │                       │ No
                                   │                       │
                    ┌──────────────▼──┐          ┌─────────▼──────────┐
                    │  Show Page 0:    │          │  Show Page 1:      │
                    │ EnvSetupWidget   │          │ App Cards Grid     │
                    └──────────────────┘          └────────────────────┘
```

## EnvSetupWidget State Machine

```
┌─────────────────────────────┐
│  Initial Load               │
│  Check uv, pixi availability│
└──────────────┬──────────────┘
               │
        ┌──────▼────────┐
        │  Display Idle │
        └──────┬─────┬──┘
               │     │
        ┌──────┘     └──────┐
        │                   │
   ┌────▼────────┐    ┌─────▼──────┐
   │ Click       │    │ Click       │
   │ Install uv  │    │ Install     │
   │             │    │ pixi        │
   └────┬────────┘    └─────┬───────┘
        │                   │
   ┌────▼───────────────────▼────┐
   │  InstallWorker runs script   │
   │  (background QThread)        │
   └────┬─────────────────────────┘
        │
   ┌────▼────────────────────┐
   │  Installation complete  │
   │  (success or failure)    │
   └────┬────────────────────┘
        │
   ┌────▼────────────────────────────┐
   │  Wait 1000ms for PATH update     │
   └────┬────────────────────────────┘
        │
   ┌────▼────────────────────────────┐
   │  _check_and_refresh()            │
   │  Re-check tool availability      │
   │  Rebuild UI                      │
   └────┬───────────────────────────┬─┘
        │                           │
   ┌────▼──────────┐          ┌─────▼──────┐
   │ Both ready?   │          │ Not ready  │
   │ Yes           │          │            │
   └────┬──────────┘          └─────┬──────┘
        │                           │
   ┌────▼──────────────────┐  ┌─────▼────────────┐
   │ Emit tools_ready()    │  │ Enable UI, show  │
   │                       │  │ install buttons  │
   └────┬──────────────────┘  └──────────────────┘
        │
   ┌────▼──────────────────┐
   │ Dashboard receives    │
   │ tools_ready signal    │
   └────┬──────────────────┘
        │
   ┌────▼──────────────────┐
   │ Switch to Page 1       │
   │ (App Cards Grid)       │
   └───────────────────────┘
```

## File Organization

```
QGarage/
├── scripts/                              # Installation scripts (repo root)
│   ├── install_uv.ps1                   # Windows uv installer
│   ├── install_uv.sh                    # Unix uv installer
│   ├── install_pixi.ps1                 # Windows pixi installer
│   └── install_pixi.sh                  # Unix pixi installer
│
└── qgarage/
    ├── plugin.py                         # [MODIFIED] Always call set_registry()
    │
    └── ui/
        ├── dashboard_dock.py             # [MODIFIED] 3-page stack + env_setup integration
        │
        └── env_setup_widget.py           # [NEW] EnvSetupWidget + InstallWorker
```

## Class Hierarchy

```
QWidget
├── EnvSetupWidget
│   ├── _check_uv_available()
│   ├── _check_pixi_available()
│   ├── is_ready()
│   ├── _build_ui()
│   ├── _build_tool_section()
│   ├── _on_install_clicked()
│   ├── _on_install_finished()
│   ├── _check_and_refresh()
│   ├── _on_refresh_clicked()
│   ├── _rebuild_ui()
│   │
│   └── signals:
│       └── tools_ready = pyqtSignal()
│
└── QThread
    └── InstallWorker
        ├── run()
        │
        └── signals:
            └── finished = pyqtSignal(bool, str)
```

## Dashboard Stacked Widget Pages

```
┌─────────────────────────────────────────────────────┐
│  DashboardDock._stack (QStackedWidget)              │
├─────────────────────────────────────────────────────┤
│  [0] EnvSetupWidget                                 │
│      - Shows when: registry is None AND tools not   │
│        ready                                        │
│      - Contains: Install buttons, status display    │
│      - Emits: tools_ready signal                    │
├─────────────────────────────────────────────────────┤
│  [1] _cards_page (QWidget)                          │
│      - Shows when: registry exists OR tools ready   │
│      - Contains: Card grid with scrollarea          │
│      - Populated by: refresh_cards()                │
├─────────────────────────────────────────────────────┤
│  [2] AppHostWidget                                  │
│      - Shows when: user opens an app                │
│      - Contains: Running app's UI                   │
│      - Populated by: show_app()                     │
└─────────────────────────────────────────────────────┘
```

## Data Flow: Installation Process

```
User clicks "Install uv"
        │
        ▼
_on_install_clicked(tool_name="uv", script_name="uv.ps1")
        │
        ├─ Find script path
        │  ├─ Try: qgarage/../scripts/install_uv.ps1
        │  └─ Fallback: qgarage/scripts/install_uv.ps1
        │
        ├─ Validate script exists
        │
        ├─ Disable UI (setEnabled(False))
        │
        └─ Create & start InstallWorker(tool_name, script_path)
                │
                ▼
            InstallWorker.run() [in background thread]
                │
                ├─ Detect OS
                │  ├─ Windows: powershell -NoProfile -ExecutionPolicy Bypass
                │  └─ Unix: bash
                │
                ├─ Run installation script
                │  └─ Script fetches from official source:
                │     ├─ uv: https://astral.sh/uv/install.ps1 | iex
                │     └─ pixi: https://pixi.sh/install.ps1 | iex
                │
                ├─ Capture stdout/stderr
                │
                └─ Emit finished(success, message)
                        │
                        ▼
                _on_install_finished(success, message)
                        │
                        ├─ If success:
                        │  └─ QTimer.singleShot(1000, _check_and_refresh)
                        │
                        └─ If failure:
                           └─ setEnabled(True)
                                   │
                                   ▼
                            _check_and_refresh()
                                   │
                                   ├─ _check_uv_available()
                                   ├─ _check_pixi_available()
                                   ├─ _rebuild_ui()
                                   │
                                   └─ If both ready:
                                      └─ tools_ready.emit()
                                              │
                                              ▼
                                    dashboard._on_tools_ready()
                                              │
                                              ├─ _stack.setCurrentIndex(1)
                                              └─ refresh_cards()
```

## Tool Detection Logic

```
is_ready() returns True only when BOTH are available:

┌────────────────────────────────┬────────────────────────────────┐
│  _check_uv_available()         │  _check_pixi_available()       │
├────────────────────────────────┼────────────────────────────────┤
│  try:                          │  try:                          │
│    subprocess.run(              │    subprocess.run(             │
│      ["uv", "--version"],       │      ["pixi", "--version"],    │
│      timeout=5                  │      timeout=5                 │
│    )                            │    )                           │
│    return True                  │    return True                 │
│  except (FileNotFoundError,     │  except (FileNotFoundError,    │
│          TimeoutExpired):       │          TimeoutExpired):      │
│    return False                 │    return False                │
└────────────────────────────────┴────────────────────────────────┘
         │                                      │
         └──────────────────┬───────────────────┘
                            │
              ┌─────────────▼──────────────┐
              │  is_ready() = True?        │
              │  (both checks returned ok) │
              └─────────────┬──────────────┘
                            │
            ┌───────────────▼──────────────┐
            │  Only show env setup landing │
            │  when is_ready() = False     │
            └────────────────────────────┘
```

## PATH Handling

After installation, the scripts add tools to PATH:

**uv (Windows):**
```powershell
# Installed to: C:\Users\<user>\.cargo\bin
# PowerShell automatically picks it up after installer runs
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + ...
```

**uv (Unix):**
```bash
# Installed to: ~/.local/bin
source "$HOME/.cargo/env"
export PATH="$HOME/.local/bin:$PATH"
```

**pixi (Windows):**
```powershell
# Installed to: C:\Users\<user>\AppData\Local\pixi\bin
# PowerShell automatically picks it up
```

**pixi (Unix):**
```bash
# Installed to: ~/.pixi/bin
export PATH="$HOME/.pixi/bin:$PATH"
```

**Delay Logic:**
- After script runs, PATH may not be immediately updated
- EnvSetupWidget waits 1000ms via `QTimer.singleShot()`
- Gives time for system to register new executables
- Then retries tool detection with `subprocess.run(["uv", "--version"])`

## Error Handling

```
Installation Failure Paths:

1. Script not found
   └─ Log error, return early
   └─ User can retry with Refresh button

2. Script execution failed
   └─ InstallWorker captures stderr
   └─ Passes error message back to UI
   └─ User sees failure notification
   └─ Install buttons remain visible for retry

3. Tool detection still fails after install
   └─ _check_and_refresh() detects unavailability
   └─ UI rebuilt with install button still visible
   └─ User can retry immediately

4. Timeout during installation (5 minutes)
   └─ InstallWorker thread kills subprocess
   └─ Returns False with timeout message
   └─ User can retry
```

## Integration Points

```
QGarage Plugin Lifecycle:

initGui()
├─ Create UvBridge/PixiBridge
├─ Create AppRegistry (if at least one tool available)
├─ Create DashboardDock
├─ Call dashboard.set_registry(registry) ← Always called
│  │
│  ├─ If registry is None AND tools not ready:
│  │  └─ Show EnvSetupWidget (page 0)
│  │
│  └─ If registry is None BUT tools ready:
│     └─ Show empty app cards (page 1)
│
├─ Connect signals:
│  ├─ dashboard.install_requested → _on_install_requested
│  ├─ dashboard.new_app_requested → _on_new_app_requested
│  └─ env_setup_widget.tools_ready → dashboard._on_tools_ready
│
└─ Add dock to QGIS interface

When tools_ready signal fires:
└─ dashboard._on_tools_ready()
   ├─ set_registry(1)  ← Switch to cards page
   └─ refresh_cards()  ← Now we can show apps (registry is re-created)
```
