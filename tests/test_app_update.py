from __future__ import annotations

import json
from datetime import datetime, timezone

from qgarage.core import app_update


def _write_meta(path, **overrides):
    meta = {
        "id": "demo_app",
        "name": "Demo App",
        "version": "1.0.0",
        "description": "demo",
    }
    meta.update(overrides)
    path.write_text(json.dumps(meta), encoding="utf-8")


def test_check_for_app_update_detects_newer_local_source(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    _write_meta(source_dir / "app_meta.json", version="1.2.0")

    installed_meta = {
        "id": "demo_app",
        "version": "1.0.0",
    }
    app_update.stamp_install_source(
        installed_meta,
        source_type="local",
        source_locator=str(source_dir),
    )

    result = app_update.check_for_app_update(installed_meta)

    assert result.available is True
    assert result.available_version == "1.2.0"


def test_apply_update_from_source_preserves_env_and_detects_manifest_changes(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    _write_meta(source_dir / "app_meta.json", version="2.0.0")
    (source_dir / "main.py").write_text("print('new')\n", encoding="utf-8")
    (source_dir / "requirements.txt").write_text("requests==2.32.0\n", encoding="utf-8")
    (source_dir / "data.txt").write_text("payload\n", encoding="utf-8")

    installed_dir = tmp_path / "installed"
    installed_dir.mkdir()
    installed_meta = {
        "id": "demo_app",
        "version": "1.0.0",
    }
    app_update.stamp_install_source(
        installed_meta,
        source_type="local",
        source_locator=str(source_dir),
    )
    (installed_dir / "app_meta.json").write_text(
        json.dumps(installed_meta), encoding="utf-8"
    )
    (installed_dir / "main.py").write_text("print('old')\n", encoding="utf-8")
    (installed_dir / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (installed_dir / "stale.txt").write_text("remove me\n", encoding="utf-8")
    (installed_dir / ".venv").mkdir()
    (installed_dir / ".venv" / "keep.txt").write_text("keep\n", encoding="utf-8")

    result = app_update.apply_update_from_source(installed_dir, installed_meta)

    assert result.requirements_changed is True
    assert result.pixi_changed is False
    assert json.loads((installed_dir / "app_meta.json").read_text(encoding="utf-8"))[
        "version"
    ] == "2.0.0"
    assert (installed_dir / "main.py").read_text(encoding="utf-8") == "print('new')\n"
    assert (installed_dir / "data.txt").exists()
    assert not (installed_dir / "stale.txt").exists()
    assert (installed_dir / ".venv" / "keep.txt").exists()


def test_should_check_for_updates_honors_recent_timestamp(monkeypatch):
    store = {}
    monkeypatch.setattr("qgarage.core.app_update.get_setting", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr("qgarage.core.app_update.set_setting", lambda key, value: store.__setitem__(key, value))

    assert app_update.should_check_for_updates("demo_app") is True

    app_update.record_update_check("demo_app")

    assert app_update.should_check_for_updates("demo_app") is False

    store["app_update/demo_app/last_checked"] = (
        datetime.now(timezone.utc) - app_update.UPDATE_CHECK_INTERVAL * 2
    ).isoformat()

    assert app_update.should_check_for_updates("demo_app") is True
