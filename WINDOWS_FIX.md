# Windows Console Error 1 - Root Cause and Fix

## Problem

QGarage apps on Windows were failing immediately with **"Error 1"** when launching the subprocess console window. This happened on every run, even for apps with no dependencies.

## Root Cause

The issue was in `qgarage/core/uv_bridge.py` in the `_wrap_windowed_command()` function. The code was creating **nested double-quotes** when wrapping commands for `cmd.exe`:

### OLD (Buggy) Code:
```python
def _wrap_windowed_command(command: Sequence[str], keep_open_on_failure: bool) -> list[str]:
    if platform.system() != "Windows" or not keep_open_on_failure:
        return list(command)

    quoted = subprocess.list2cmdline(list(command))
    return ["cmd.exe", "/d", "/s", "/c", f'"{quoted} || pause"']  # ❌ Extra quotes!
```

When the command contained paths with spaces (e.g., `C:\Program Files\Python312\python.exe`), this produced:

```
cmd.exe /d /s /c ""C:\Program Files\Python312\python.exe" runner.py config.json || pause"
                 ^^--- Double quotes at start cause parsing error
```

The double-quotes at the start confused `cmd.exe`'s parser, causing it to fail with exit code 1.

### NEW (Fixed) Code:
```python
def _wrap_windowed_command(command: Sequence[str], keep_open_on_failure: bool) -> list[str]:
    if platform.system() != "Windows" or not keep_open_on_failure:
        return list(command)

    quoted = subprocess.list2cmdline(list(command))
    return ["cmd.exe", "/d", "/s", "/c", f"{quoted} || pause"]  # ✅ No extra quotes
```

Now it produces:

```
cmd.exe /d /s /c "C:\Program Files\Python312\python.exe" runner.py config.json || pause
                 ^--- Single quote level - works correctly
```

## Additional Fixes

While investigating, we also found and fixed a **major documentation inconsistency**:

### Documentation Said: "Ephemeral `uv run --isolated`"

The CLAUDE.md documentation claimed QGarage uses `uv run --isolated` to resolve dependencies at runtime on every execution (ephemeral model).

### Reality: "Persistent venvs with `uv venv` + `uv pip install`"

The actual implementation:
1. Creates a persistent `.venv/` directory in each app folder
2. Runs `uv venv .venv` to create the environment (once)
3. Runs `uv pip install -r requirements.txt` to install dependencies (once)
4. Reuses the venv on subsequent runs (fast)

### What We Updated

1. **Fixed the Windows quoting bug** in `uv_bridge.py`
2. **Updated all documentation** to accurately describe the persistent venv model
3. **Added detailed comments** explaining the actual execution flow
4. **Updated tests** to match the new quoting behavior

## Files Changed

- `qgarage/core/uv_bridge.py` - Fixed `_wrap_windowed_command()` quoting + docs
- `qgarage/core/subprocess_runner.py` - Updated comments to say "persistent venv" not "uv run --isolated"
- `qgarage/core/base_app.py` - Updated comment to match reality
- `CLAUDE.md` - Comprehensive documentation update (7 locations)
- `tests/test_uv_bridge.py` - Updated tests for new quoting behavior

## Testing

All 94 tests pass, including the specific Windows qu