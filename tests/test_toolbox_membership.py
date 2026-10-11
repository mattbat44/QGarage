from __future__ import annotations

import json

from qgarage.core import app_update
from qgarage.core.toolbox_membership import (
    ensure_toolbox_shell,
    find_parent_toolbox_meta,
    reconcile_installed_apps,
    relocate_standalone_conflict,
)


def _write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_find_parent_toolbox_meta_detects_sibling_file(tmp_path):
    toolbox_dir = tmp_path / "MyToolbox"
    app_dir = toolbox_dir / "my_app"
    app_dir.mkdir(parents=True)
    _write_json(toolbox_dir / "toolbox_meta.json", {"id": "my_toolbox"})

    result = find_parent_toolbox_meta(app_dir)

    assert result == toolbox_dir / "toolbox_meta.json"


def test_find_parent_toolbox_meta_returns_none_when_absent(tmp_path):
    app_dir = tmp_path / "standalone_app"
    app_dir.mkdir()

    assert find_parent_toolbox_meta(app_dir) is None


def test_ensure_toolbox_shell_creates_new_toolbox_dir(tmp_path):
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    source_toolbox_dir = tmp_path / "source" / "MyToolbox"
    source_toolbox_dir.mkdir(parents=True)
    toolbox_meta_file = source_toolbox_dir / "toolbox_meta.json"
    _write_json(toolbox_meta_file, {"id": "my_toolbox", "name": "My Toolbox"})

    toolbox_id = ensure_toolbox_shell(apps_dir, toolbox_meta_file)

    assert toolbox_id == "my_toolbox"
    assert (apps_dir / "my_toolbox" / "toolbox_meta.json").exists()


def test_ensure_toolbox_shell_does_not_overwrite_existing(tmp_path):
    apps_dir = tmp_path / "apps"
    dest_toolbox_dir = apps_dir / "my_toolbox"
    dest_toolbox_dir.mkdir(parents=True)
    _write_json(
        dest_toolbox_dir / "toolbox_meta.json", {"id": "my_toolbox", "version": "2.0.0"}
    )

    source_toolbox_dir = tmp_path / "source" / "MyToolbox"
    source_toolbox_dir.mkdir(parents=True)
    toolbox_meta_file = source_toolbox_dir / "toolbox_meta.json"
    _write_json(toolbox_meta_file, {"id": "my_toolbox", "version": "1.0.0"})

    ensure_toolbox_shell(apps_dir, toolbox_meta_file)

    on_disk = json.loads((dest_toolbox_dir / "toolbox_meta.json").read_text())
    assert on_disk["version"] == "2.0.0"


def test_reconcile_installed_apps_moves_app_into_toolbox(tmp_path):
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()

    # Original source layout: a toolbox folder containing one app.
    source_toolbox_dir = tmp_path / "source" / "MyToolbox"
    source_app_dir = source_toolbox_dir / "my_app"
    source_app_dir.mkdir(parents=True)
    _write_json(source_toolbox_dir / "toolbox_meta.json", {"id": "my_toolbox"})
    _write_json(source_app_dir / "app_meta.json", {"id": "my_app"})

    # Standalone-installed copy in apps_dir, stamped with its local source.
    installed_app_dir = apps_dir / "my_app"
    installed_app_dir.mkdir()
    app_meta = {"id": "my_app", "name": "My App"}
    app_update.stamp_install_source(
        app_meta, source_type="local", source_locator=str(source_app_dir)
    )
    _write_json(installed_app_dir / "app_meta.json", app_meta)

    migrated = reconcile_installed_apps(apps_dir)

    assert migrated == [("my_app", "my_toolbox")]
    assert not installed_app_dir.exists()
    assert (apps_dir / "my_toolbox" / "my_app" / "app_meta.json").exists()
    assert (apps_dir / "my_toolbox" / "toolbox_meta.json").exists()


def test_reconcile_installed_apps_skips_url_installs(tmp_path):
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()

    installed_app_dir = apps_dir / "my_app"
    installed_app_dir.mkdir()
    app_meta = {"id": "my_app", "name": "My App"}
    app_update.stamp_install_source(
        app_meta, source_type="url", source_locator="https://example.com/app.zip"
    )
    _write_json(installed_app_dir / "app_meta.json", app_meta)

    migrated = reconcile_installed_apps(apps_dir)

    assert migrated == []
    assert installed_app_dir.exists()


def test_reconcile_installed_apps_skips_when_destination_exists(tmp_path):
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()

    source_toolbox_dir = tmp_path / "source" / "MyToolbox"
    source_app_dir = source_toolbox_dir / "my_app"
    source_app_dir.mkdir(parents=True)
    _write_json(source_toolbox_dir / "toolbox_meta.json", {"id": "my_toolbox"})
    _write_json(source_app_dir / "app_meta.json", {"id": "my_app"})

    (apps_dir / "my_toolbox" / "my_app").mkdir(parents=True)

    installed_app_dir = apps_dir / "my_app"
    installed_app_dir.mkdir()
    app_meta = {"id": "my_app", "name": "My App"}
    app_update.stamp_install_source(
        app_meta, source_type="local", source_locator=str(source_app_dir)
    )
    _write_json(installed_app_dir / "app_meta.json", app_meta)

    migrated = reconcile_installed_apps(apps_dir)

    assert migrated == []
    assert installed_app_dir.exists()


def test_relocate_standalone_conflict_removes_stale_dir(tmp_path):
    apps_dir = tmp_path / "apps"
    stale_dir = apps_dir / "my_app"
    stale_dir.mkdir(parents=True)
    keep_dir = apps_dir / "my_toolbox" / "my_app"
    keep_dir.mkdir(parents=True)

    relocate_standalone_conflict(apps_dir, "my_app", keep_dir)

    assert not stale_dir.exists()
    assert keep_dir.exists()
