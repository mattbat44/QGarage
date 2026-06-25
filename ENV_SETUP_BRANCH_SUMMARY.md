# Environment Setup Landing Screen — Branch Summary

**Branch:** `env-setup-landing-screen`  
**Created from:** `test-dist`  
**Commit:** `5de8010`

## Overview

This branch implements a landing screen that appears in QGarage when required environment tools (`uv` or `pixi`) are unavailable. Users can install missing tools directly from the dashboard using one-click buttons that run embedded installation scripts.

## What Changed

### New Files

1. **`scripts/install_uv.ps1`** — PowerShell script to install uv on Windows
2. **`scripts/install_uv.sh`** — Bash script to install uv on Linux/macOS
3. **`scripts/install_pixi.ps1`** — PowerShell script to install pixi on Windows
4. **`scripts/install_pixi.sh`** — Bash script to install pixi on Linux/macOS
5. **`qgarage/ui/env_setup_widget.py`** — New EnvSetupWidget class (300+ lines)

### Modified Files

1. **`qgarage/plugin.py`**
   - Simplified `initGui()` to always call `dock.set_registry(self.registry)` (even if None)
   - This ensures the env setup page is shown when tools are unavailable

2. **`qgarage/ui/dashboard_dock.py`**
   - Added import for `EnvSetupWidget`
   - Modified stacked widget to have 3 pages instead of 2:
     - **Page 0:** Environment setup landing screen
     - **Page 1:** App cards grid
     - **Page 2:** App host (running app)
   - Updated `set_registry()` to show env setup page if registry is None and tools aren't ready
   - Updated all index references from 0/1 to 1/2 accordingly
   - Added `_on_tools_ready()` handler to transition from env setup to app grid

## How It Works

### Detection
When the plugin initializes (`initGui()`), it attempts to create `UvBridge` and `PixiBridge`:
- If both fail, `self.registry` remains `None`
- The `set_registry(None)` call triggers the dashboard to show the env setup page

### Installation Flow
1. **User clicks "Install uv" or "Install pixi"** on the landing screen
2. `EnvSetupWidget._on_install_clicked()` finds the appropriate installation script:
   - Tries `qgarage/../scripts/install_uv.ps1` (for plugin in dist folder)
   - Falls back to `qgarage/scripts/install_uv.ps1` (if scripts in plugin source)
3. **InstallWorker thread** runs the script in the background:
   - Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File <script>`
   - Unix: `bash <script>`
4. **Script executes** the official installation command:
   - uv: `irm https://astral.sh/uv/install.ps1 | iex` (Windows) or `curl -LsSf https://astral.sh/uv/install.sh | sh` (Unix)
   - pixi: `irm https://pixi.sh/install.ps1 | iex` (Windows) or `curl -fsSL https://pixi.sh/install.sh | bash` (Unix)
5. **After installation**, the worker emits `finished(success, message)`
6. **EnvSetupWidget rechecks** tool availability after a 1-second delay (gives PATH time to update)
7. If both tools are now available, `tools_ready` signal is emitted
8. **Dashboard transitions** to the app cards grid and enables normal operation

### UI Features
- **Tool cards** show status (✓ Available or ✗ Not installed)
- **Install buttons** appear only for unavailable tools
- **Refresh / Retry button** allows manual re-checking without reinstalling
- **Responsive design** with scrollable content for smaller windows
- **Color-coded sections**: Green background for available, red for unavailable

## Key Implementation Details

### EnvSetupWidget (`qgarage/ui/env_setup_widget.py`)
- **`_check_uv_available()` / `_check_pixi_available()`** — Run `<tool> --version` with 5-second timeout
- **`is_ready()`** — Returns True only if both tools are detected
- **`_build_ui()`** — Creates the landing screen with tool sections
- **`_on_install_clicked()`** — Launches InstallWorker thread
- **`_check_and_refresh()`** — Rechecks tools and updates UI after installation
- **`_rebuild_ui()`** — Clears and regenerates UI to show updated status

### InstallWorker (inside `env_setup_widget.py`)
- Runs installation in a background QThread to prevent UI freezing
- Handles both Windows (PowerShell) and Unix (Bash) scripts
- Captures stdout/stderr and reports success/failure via Qt signal
- 5-minute timeout per installation to prevent hanging

### Dashboard Integration
- New property `_env_setup_widget` stores the widget instance
- Stacked widget pages restructured: env setup (0), cards (1), host (2)
- `set_registry()` intelligently decides which page to show:
  - If registry is `None` and tools aren't ready → page 0 (env setup)
  - If registry is `None` but tools are ready → page 1 (cards, empty state)
  - If registry is not `None` → page 1 (cards with apps)
- `_on_tools_ready()` transitions to page 1 and calls `refresh_cards()`

## Scripts Location & Packaging

The scripts are placed at the **repo root** (`scripts/` directory) rather than inside the plugin, because:
1. **Installation scripts** are meta-level tools that live outside the versioned plugin code
2. **Build process** uses `shutil.copytree()` with `rglob('*')`, which will automatically include them in the plugin ZIP
3. **Fallback logic** in `env_setup_widget.py` handles both locations (repo root and inside plugin)

For local testing:
```bash
ls -la scripts/
# install_pixi.ps1
# install_pixi.sh
# install_uv.ps1
# install_uv.sh
```

## Testing Checklist

1. **Simulate missing tools:**
   ```bash
   # Temporarily hide uv from PATH
   export PATH=/usr/bin:/bin:/usr/sbin:/sbin
   # Start QGIS with the test plugin
   ```

2. **Verify landing screen appears:**
   - Click "QGarage Dashboard" — env setup page should appear
   - Both uv and pixi should show "✗ Not installed"
   - Both should have "Install" buttons

3. **Test uv installation:**
   - Click "Install uv"
   - Button becomes disabled, worker runs
   - After ~30-60 seconds, check status updates to "✓ Available"
   - Click "Refresh / Retry" — both tools now available
   - `tools_ready` signal emits, dashboard transitions to app cards

4. **Test pixi installation:**
   - Repeat above for pixi

5. **Test refresh without reinstalling:**
   - Click "Refresh / Retry" with both tools already available
   - Should emit `tools_ready` immediately

6. **Test partial install:**
   - Install only uv (leave pixi unavailable)
   - Dashboard should stay on env setup page
   - Both install buttons should be available until both tools exist

## OS Compatibility

- **Windows:** Uses PowerShell scripts with `-ExecutionPolicy Bypass`
- **macOS:** Uses Bash scripts, sets up PATH for `~/.local/bin` and `~/.pixi/bin`
- **Linux:** Uses Bash scripts, same PATH setup as macOS

Scripts auto-detect OS and refuse to run on incompatible platforms.

## Future Enhancements

1. **Progress bar** during installation (parse stdout)
2. **Manual PATH configuration** if auto-discovery fails
3. **Link to documentation** for troubleshooting manual installs
4. **Store installation preference** to remember skipped tools
5. **Version checking** to warn if installed tool is outdated

## Files Summary

| File | Lines | Purpose |
|------|-------|---------|
| `scripts/install_uv.ps1` | ~25 | Windows uv installer |
| `scripts/install_uv.sh` | ~28 | Unix uv installer |
| `scripts/install_pixi.ps1` | ~25 | Windows pixi installer |
| `scripts/install_pixi.sh` | ~28 | Unix pixi installer |
| `qgarage/ui/env_setup_widget.py` | ~330 | EnvSetupWidget + InstallWorker |
| `qgarage/plugin.py` | +2 lines | Always call set_registry() |
| `qgarage/ui/dashboard_dock.py` | +20 lines | Integrate env setup, 3-page stack |
