# Branch: `env-setup-landing-screen`

A new QGarage feature that provides a guided setup experience when required environment tools (`uv` or `pixi`) are missing.

## Branch Information

- **Branch name:** `env-setup-landing-screen`
- **Created from:** `test-dist`
- **Latest commit:** `670d15e`
- **Total commits:** 4 new commits
- **Files changed:** 8 files (3 modified, 5 new)
- **Net additions:** +643 lines

## What's New

### 🎯 Core Feature: Environment Setup Landing Screen

When QGarage initializes and finds that `uv` and/or `pixi` are unavailable, instead of showing an empty dashboard or error, users see a professional landing screen with:

- **Tool status display** — Shows which tools are installed (✓) and which are missing (✗)
- **One-click installation** — Install missing tools directly from the dashboard
- **Cross-platform support** — Automatic detection and installation for Windows, macOS, and Linux
- **Background installation** — Tools install in a background thread without freezing the UI
- **Automatic detection** — After installation completes, the dashboard automatically checks for and loads newly installed tools
- **Manual refresh** — Users can click "Refresh / Retry" to re-check without reinstalling

### 📦 Installation Scripts

Four new installation scripts automatically handle tool setup:
- `scripts/install_uv.ps1` — Windows PowerShell installer for uv
- `scripts/install_uv.sh` — Linux/macOS Bash installer for uv
- `scripts/install_pixi.ps1` — Windows PowerShell installer for pixi
- `scripts/install_pixi.sh` — Linux/macOS Bash installer for pixi

These scripts:
- Download and run official installers from `astral.sh` and `pixi.sh`
- Handle platform-specific PATH configuration
- Include error handling and informative messages
- Are included in the plugin package automatically

### 💻 Code Changes

**New files:**
- `qgarage/ui/env_setup_widget.py` (331 lines)
  - `EnvSetupWidget` class — Landing screen UI and logic
  - `InstallWorker` class — Background thread for non-blocking installation

**Modified files:**
- `qgarage/plugin.py` (+3 lines)
  - Always call `dock.set_registry()` to trigger environment check
- `qgarage/ui/dashboard_dock.py` (+33 lines)
  - Restructured stacked widget from 2 pages to 3 pages
  - Added integration with `EnvSetupWidget`
  - Implemented `_on_tools_ready()` handler for transition from setup to app grid

## Behavior

### Before (Without This Feature)

```
User opens QGarage without uv/pixi installed
    ↓
Plugin fails to initialize properly
    ↓
Dashboard shows empty grid or error
    ↓
User must manually install uv/pixi from external documentation
```

### After (With This Feature)

```
User opens QGarage without uv/pixi installed
    ↓
Landing screen appears with installation options
    ↓
User clicks "Install uv" / "Install pixi"
    ↓
Background thread runs installation script
    ↓
After ~30-60 seconds, tools are installed
    ↓
Dashboard automatically detects and transitions to app grid
    ↓
QGarage is ready to use
```

## Quick Start

### For End Users

1. Update to this version of QGarage
2. Open QGarage Dashboard
3. If you see a setup screen, click the installation buttons
4. Wait for tools to install (30-60 seconds)
5. Dashboard automatically transitions to app grid
6. Start using QGarage!

### For Developers

1. Checkout this branch:
   ```bash
   git checkout env-setup-landing-screen
   ```

2. Test locally:
   ```bash
   # Verify new files exist
   ls -la scripts/
   ls qgarage/ui/env_setup_widget.py
   
   # Run tests
   uv run pytest
   ```

3. Review documentation:
   - `ENV_SETUP_BRANCH_SUMMARY.md` — Overview and implementation details
   - `ENV_SETUP_ARCHITECTURE.md` — Technical architecture and flow diagrams
   - `ENV_SETUP_TESTING_GUIDE.md` — Comprehensive testing procedures

## Files Overview

### Core Implementation

```
qgarage/ui/env_setup_widget.py          331 lines
├── EnvSetupWidget                      Main UI widget for landing screen
│   ├── _check_uv_available()           Detects uv in PATH
│   ├── _check_pixi_available()         Detects pixi in PATH
│   ├── _build_ui()                     Constructs the landing screen layout
│   ├── _on_install_clicked()           Launches installation
│   └── _on_install_finished()          Handles installation completion
│
└── InstallWorker                       Background thread for installation
    ├── run()                           Executes installation script
    └── finished signal                 Emits success/failure + message
```

### Installation Scripts

```
scripts/install_uv.ps1                  ~25 lines (Windows)
scripts/install_uv.sh                   ~28 lines (Unix)
scripts/install_pixi.ps1                ~25 lines (Windows)
scripts/install_pixi.sh                 ~28 lines (Unix)
```

### Modified Core Files

```
qgarage/plugin.py                       +3 lines
└── Always call set_registry() to trigger env check

qgarage/ui/dashboard_dock.py            +33 lines
└── Integrate EnvSetupWidget as stacked page 0
```

## Testing

Before merging, verify:

- [ ] Landing screen appears when tools are missing
- [ ] Installation buttons work and install tools correctly
- [ ] Dashboard transitions automatically when both tools available
- [ ] Refresh button re-checks without reinstalling
- [ ] Apps load and function normally after tools installed
- [ ] Error handling gracefully handles installation failures
- [ ] UI is responsive during installation
- [ ] All platforms tested (Windows, macOS, Linux)

See `ENV_SETUP_TESTING_GUIDE.md` for detailed testing procedures.

## Documentation

Three comprehensive documentation files are included:

1. **`ENV_SETUP_BRANCH_SUMMARY.md`**
   - Overview of changes
   - How it works
   - File organization
   - Future enhancements

2. **`ENV_SETUP_ARCHITECTURE.md`**
   - Flow diagrams
   - State machines
   - Data flow
   - Integration points
   - Error handling paths

3. **`ENV_SETUP_TESTING_GUIDE.md`**
   - Test scenarios
   - Expected behavior
   - Manual testing checklist
   - Debug information
   - Success criteria

## Compatibility

- **QGIS:** 3.28+ (including 4.0)
- **Python:** 3.10+
- **OS:** Windows, macOS, Linux
- **Internet:** Required for installation (downloads from astral.sh, pixi.sh)

## Known Limitations

- Installation requires internet connection
- 5-minute timeout if installation hangs
- Tools must be added to PATH (typically automatic by installers)
- UAC/admin prompt may appear on Windows
- Installation is per-user, not system-wide

## Integration with Main Branch

This feature is **opt-in** — it only activates when tools are missing. Existing behavior is preserved:
- If both tools already installed → no setup screen shown, normal operation
- If at least one tool available → registry created, apps available
- Only when both tools missing → setup screen appears

## Version Information

- **Plugin version:** (inherited from plugin.py::metadata.txt)
- **Feature availability:** QGarage 2.1.3+
- **Minimum QGIS:** 3.28

## Questions & Support

Refer to the included documentation files for:
- **How it works:** See `ENV_SETUP_ARCHITECTURE.md`
- **Testing procedures:** See `ENV_SETUP_TESTING_GUIDE.md`
- **Implementation details:** See `ENV_SETUP_BRANCH_SUMMARY.md`

---

**Ready to merge? Check the testing guide and run the full test suite!**
