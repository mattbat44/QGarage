from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path


def _clear_readonly_and_retry(func, path, excinfo) -> None:
    """Retry a filesystem operation after clearing read-only bits."""
    exc_value = excinfo[1] if excinfo else None
    if not isinstance(exc_value, PermissionError):
        raise exc_value

def _clear_readonly_and_retry(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
    parent = Path(path).parent
    if parent.exists():
        os.chmod(parent, os.stat(parent).st_mode | stat.S_IWRITE | stat.S_IEXEC)
    func(path)


def remove_tree(path: Path) -> None:
    """Delete a directory tree, including read-only entries (e.g. bundled WhiteboxTools folders)."""
    shutil.rmtree(path, onerror=_clear_readonly_and_retry)
