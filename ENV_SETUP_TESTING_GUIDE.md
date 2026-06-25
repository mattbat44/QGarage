# Environment Setup Landing Screen — Testing Guide

## Quick Summary

**What to test:** When `uv` and/or `pixi` are unavailable, QGarage should:
1. Display a landing screen with tool installation options
2. Allow one-click installation of missing tools
3. Automatically detect when tools are installed
4. Transition to the normal app grid once tools are ready

---

## Prerequisites

- QGarage plugin installed (from this branch)
- QGIS 3.28+ (with Python 3.10+)
- macOS, Linux, or Windows
- Internet connection (for downloading tools)

---

## Test Scenario 1: Both Tools Missing (Cleanest Test)

### Setup
Run QGIS in a clean environment without uv or pixi:

**On Windows (PowerShell as Admin):**
```powershell
# Option A: Temporary PATH override
$env:Path = "C:\Windows\System32;C:\Windows"
# Then start QGIS
```

**On macOS/Linux (Terminal):**
```bash
# Option A: Start QGIS with minimal PATH
PATH=/usr/bin:/bin:/usr/sbin:/sbin /Applications/QGIS.app/Contents/MacOS/QGIS
# or
PATH=/usr/bin:/bin:/usr/sbin:/sbin qgis
```

**Option B (All platforms): Use Docker or VM**
- Create a minimal Python environment without uv/pixi
- Install QGarage plugin only
- Start QGIS

### Expected Behavior

1. **On startup:**
   - QGarage dock appears on right side
   - Should be collapsed or showing landing screen

2. **Click "QGarage Dashboard" toolbar button:**
   - Dock expands and shows `EnvSetupWidget`
   - Landing screen has title: "QGarage Environment Setup"
   - Shows description: "QGarage requires environment managers..."

3. **Tool status display:**
   - Two tool cards appear: **UV** and **PIXI**
   - Both show:
     - ✗ Not installed (red text)
     - Red-tinted background
     - "Install uv" and "Install pixi" buttons
   - Refresh button appears at bottom

### Testing Installation

4. **Install uv:**
   - Click "Install uv" button
   - Button becomes disabled (grayed out)
   - Status briefly shows "Installing..."
   - After 30-60 seconds:
     - Status changes to "✓ Available" (green)
     - Background becomes normal
     - Install button disappears
   - "Pixi" card still shows "✗ Not installed"

5. **Install pixi:**
   - Click "Install pixi" button
   - Same behavior as uv
   - After installation completes:
     - Both cards show "✓ Available"
     - Dashboard **automatically transitions** to app cards grid
     - "Refresh / Retry" button is gone
     - Landing screen replaced with normal dashboard

6. **Verify apps are accessible:**
   - If apps are installed, they should appear in the cards grid
   - Click an app → app UI opens
   - Click back arrow → returns to cards grid

---

## Test Scenario 2: One Tool Available

### Setup

**Windows (with uv, without pixi):**
```powershell
# Install uv
powershell -Command "irm https://astral.sh/uv/install.ps1 | iex"

# Hide pixi from PATH
$env:Path = "C:\Users\$env:USERNAME\.cargo\bin;C:\Windows\System32;C:\Windows"

# Start QGIS
```

**macOS/Linux (with uv, without pixi):**
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Hide pixi from PATH
PATH="$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin" qgis
```

### Expected Behavior

1. **Landing screen shows:**
   - **UV**: ✓ Available (green, no install button)
   - **PIXI**: ✗ Not installed (red, install button present)

2. **Install pixi:**
   - Click "Install pixi"
   - After completion:
     - **Both tools** show ✓ Available
     - Dashboard transitions to app cards

3. **Partial installation scenario:**
   - If installation fails partway through:
     - Landing screen shows partial status
     - Both install buttons remain visible
     - User can retry either tool

---

## Test Scenario 3: Both Tools Available Already

### Setup

**Windows:**
```powershell
# Verify both tools are in PATH
uv --version    # Should work
pixi --version  # Should work

# Start QGIS
```

**macOS/Linux:**
```bash
uv --version    # Should work
pixi --version  # Should work

qgis
```

### Expected Behavior

1. **On plugin load:**
   - DashboardDock shows app cards grid immediately
   - No landing screen appears
   - Only `EnvSetupWidget` is created but never shown (page 0 is hidden)

2. **Apps are fully functional:**
   - All apps available in cards
   - Install button works
   - New App button works
   - Processing toolbox integration works

---

## Test Scenario 4: Refresh / Retry Button

### Setup

1. Start with both tools missing (see Scenario 1)
2. Landing screen appears

### Expected Behavior

1. **Click "Refresh / Retry":**
   - No network activity
   - Just re-checks if tools are in PATH
   - Status remains "✗ Not installed" (tools still aren't there)
   - Install buttons remain visible

2. **After installing uv manually** (outside QGIS):
   - Click "Refresh / Retry" in landing screen
   - **UV** immediately updates to "✓ Available"
   - **PIXI** still shows "✗ Not installed"
   - Dashboard does NOT transition (only pixi installed)

3. **After installing pixi manually:**
   - Click "Refresh / Retry" again
   - Both show "✓ Available"
   - Dashboard automatically transitions to app grid

---

## Test Scenario 5: Installation Failure Handling

### Setup

1. Start with both tools missing
2. Landing screen appears
3. Simulate network failure or script error

### Expected Behavior

1. **Click "Install uv":**
   - (Simulate network error during download)
   - Status shows: "✗ Not installed"
   - Error message appears in console
   - Install button re-enabled
   - User can retry

2. **Click "Install pixi":**
   - (Script times out or fails)
   - Status shows: "✗ Not installed"
   - Error in QGIS Python console
   - Install button re-enabled

3. **Click "Refresh / Retry":**
   - Just checks PATH again
   - Does not retry installation

---

## Test Scenario 6: PATH Auto-Discovery After Install

### What to verify

The tool detection uses `subprocess.run()` to check availability, not by reading PATH directly. This means:

1. **After installation**, there's a 1-second delay before re-checking
   - This gives time for the system to register the new executable
   - If you see "Available" immediately, the PATH was already updated

2. **If status doesn't update after install:**
   - It likely means the script ran successfully but didn't add to PATH
   - Manual restart of QGIS might help
   - Or user can manually add to PATH and click "Refresh / Retry"

---

## Manual Testing Checklist

### Checklist 1: UI Appearance

- [ ] Landing screen appears when both tools missing
- [ ] Title says "QGarage Environment Setup"
- [ ] Description text is present and readable
- [ ] Two tool cards displayed (UV and PIXI)
- [ ] Card styling matches theme (dark/light mode)
- [ ] Install buttons present for unavailable tools
- [ ] Install buttons absent for available tools
- [ ] Refresh button present at bottom
- [ ] Layout doesn't break at different window sizes

### Checklist 2: Tool Detection

- [ ] UV detection correctly identifies installed uv
- [ ] Pixi detection correctly identifies installed pixi
- [ ] Tools marked "Available" in green with ✓ symbol
- [ ] Tools marked "Not installed" in red with ✗ symbol
- [ ] Refresh button updates status correctly
- [ ] Status updates within 2 seconds of refresh click

### Checklist 3: Installation Process

- [ ] Install button becomes disabled during installation
- [ ] Installation runs in background (UI remains responsive)
- [ ] Installation completes within 2 minutes
- [ ] Status updates to "Available" after install
- [ ] Card color changes from red to green
- [ ] Install button disappears after tool becomes available
- [ ] Error messages are clear if installation fails

### Checklist 4: Dashboard Transition

- [ ] Dashboard transitions to app cards once both tools available
- [ ] Apps are discovered and displayed
- [ ] App installation works
- [ ] App execution works
- [ ] Processing toolbox registration works

### Checklist 5: Edge Cases

- [ ] Partial installation (one tool) shows correct status
- [ ] Refresh button works without reinstalling
- [ ] Manual PATH changes are detected on refresh
- [ ] Window resize doesn't break UI
- [ ] Rapid clicks don't cause multiple installs
- [ ] Installation cancellation/stopping is handled gracefully

---

## Debug Information

If something goes wrong, check these logs:

### QGIS Python Console
```
Plugins → Python Console
```
Look for messages starting with:
- `qgarage.env_setup` — EnvSetupWidget debug messages
- `qgarage.dashboard` — Dashboard navigation messages
- `qgarage.plugin` — Plugin initialization messages

### System Console (QGIS startup)
Run QGIS from terminal to see stdout:
```bash
# macOS/Linux
qgis 2>&1 | grep -i "qgarage\|uv\|pixi"

# Windows (PowerShell)
qgis 2>&1 | Select-String "qgarage|uv|pixi"
```

### Key diagnostic messages to look for

**Successful tool detection:**
```
[qgarage.env_setup] Checking for available tools...
[qgarage.env_setup] uv detected at: /usr/local/bin/uv
[qgarage.env_setup] pixi detected at: /usr/local/bin/pixi
```

**Missing tools:**
```
[qgarage.env_setup] uv not available: [Errno 2] No such file...
[qgarage.env_setup] pixi not available: [Errno 2] No such file...
```

**Installation success:**
```
[qgarage.env_setup] Starting uv installation from /path/to/install_uv.sh
[qgarage.env_setup] Installation finished: True - uv installed successfully!
```

**Script not found:**
```
[qgarage.env_setup] Install script not found. Checked: ... and ...
```

---

## Reporting Issues

When reporting issues, include:

1. **OS and version:** Windows 10, macOS 12.3, Ubuntu 22.04, etc.
2. **QGIS version:** 3.28, 4.0, etc.
3. **Tool status at start:** Neither installed / One installed / Both installed
4. **What happened:** (describe the issue)
5. **What should happen:** (expected behavior)
6. **Screenshots:** If UI is broken or showing errors
7. **Console output:** From QGIS Python console (copy/paste relevant lines)
8. **Steps to reproduce:** Clear numbered steps

---

## Performance Notes

- **Tool detection:** ~1-2 seconds total (5 second timeout per tool)
- **Installation time:** 30-60 seconds depending on internet speed
- **Re-detection after install:** 1 second delay + ~1-2 seconds for detection = ~2-3 seconds
- **UI responsiveness:** All installation happens in background thread (non-blocking)

---

## Success Criteria

✅ **All tests pass if:**

1. Landing screen appears when tools are missing
2. Installation buttons work and tools are installed
3. Dashboard auto-transitions when both tools available
4. Tool detection is accurate and responsive
5. Error handling is graceful
6. UI layout works at various window sizes
7. Apps function normally after tools are installed
8. No crashes or unhandled exceptions

---

## Known Limitations

- **Timeout:** If installation takes >5 minutes, script will be killed
- **Offline mode:** Installation requires internet (downloads from astral.sh and pixi.sh)
- **Manual PATH updates:** If tools are added by something other than installer, might need refresh
- **Elevated privileges:** Windows may require admin/UAC prompt for PATH updates
- **Multiple users:** Installation is per-user, not system-wide (by design for security)

---

## Next Steps After Testing

If this branch passes all tests:

1. Merge into `main` or `test-dist`
2. Update plugin version
3. Update changelog
4. Create release notes
5. Package and deploy to QGIS plugin repository
6. Announce feature in documentation
