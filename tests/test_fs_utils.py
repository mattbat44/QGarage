from __future__ import annotations

import os
import stat
from pathlib import Path

from qgarage.core.fs_utils import remove_tree


def test_remove_tree_deletes_read_only_files_and_folders(tmp_path: Path):
    app_dir = tmp_path / "ToCApp"
    plugins = app_dir / "tools" / "WBT" / "plugins"
    plugins.mkdir(parents=True)
    exe = plugins / "tool.exe"
    exe.write_text("x")
    os.chmod(exe, stat.S_IREAD)
    os.chmod(plugins, stat.S_IREAD | stat.S_IEXEC)

    remove_tree(app_dir)

    assert not app_dir.exists()
