from __future__ import annotations

import json
from pathlib import Path

from qgarage.core.marketplace import scan_marketplace


def _write_metadata(directory: Path, filename: str, metadata: dict) -> None:
    directory.mkdir(parents=True)
    (directory / filename).write_text(json.dumps(metadata), encoding="utf-8")


def test_scan_marketplace_discovers_apps_and_toolboxes_without_installing(tmp_path):
    source_dir = tmp_path / "source"
    managed_apps_dir = tmp_path / "managed_apps"
    _write_metadata(
        source_dir / "sample_app",
        "app_meta.json",
        {"id": "sample_app", "name": "Sample App", "description": "An app"},
    )
    _write_metadata(
        source_dir / "sample_toolbox",
        "toolbox_meta.json",
        {"id": "sample_toolbox", "name": "Sample Toolbox"},
    )
    _write_metadata(
        source_dir / "sample_toolbox" / "first_tool",
        "app_meta.json",
        {"id": "first_tool", "name": "First Tool"},
    )

    items = scan_marketplace([source_dir])

    assert [(item.item_id, item.is_toolbox, item.app_count) for item in items] == [
        ("first_tool", False, 0),
        ("sample_app", False, 0),
        ("sample_toolbox", True, 1),
    ]
    assert items[0].parent_toolbox_name == "Sample Toolbox"
    assert all(item.source_dir.is_relative_to(source_dir) for item in items)
    assert not managed_apps_dir.exists()


def test_scan_marketplace_ignores_invalid_metadata_and_includes_toolbox_apps(tmp_path):
    source_dir = tmp_path / "source"
    _write_metadata(
        source_dir / "toolbox",
        "toolbox_meta.json",
        {"id": "toolbox", "name": "Toolbox"},
    )
    _write_metadata(
        source_dir / "toolbox" / "nested_app",
        "app_meta.json",
        {"id": "nested_app", "name": "Nested App"},
    )
    invalid_dir = source_dir / "invalid"
    invalid_dir.mkdir()
    (invalid_dir / "app_meta.json").write_text("not JSON", encoding="utf-8")

    items = scan_marketplace([source_dir])

    assert [item.item_id for item in items] == ["nested_app", "toolbox"]
    assert items[0].parent_toolbox_name == "Toolbox"


def test_scan_marketplace_keeps_only_newest_toolbox_and_tool_versions(tmp_path):
    older_root = tmp_path / "older"
    newer_root = tmp_path / "newer"
    for root, version in ((older_root, "1.2.0"), (newer_root, "1.10.0")):
        _write_metadata(
            root / "toolbox",
            "toolbox_meta.json",
            {"id": "toolbox", "name": "Toolbox", "version": version},
        )
        _write_metadata(
            root / "toolbox" / "tool",
            "app_meta.json",
            {"id": "tool", "name": "Tool", "version": version},
        )
        _write_metadata(
            root / "standalone",
            "app_meta.json",
            {"id": "standalone", "name": "Standalone", "version": version},
        )

    items = scan_marketplace([older_root, newer_root])

    assert [(item.item_id, item.metadata.get("version")) for item in items] == [
        ("standalone", "1.10.0"),
        ("tool", "1.10.0"),
        ("toolbox", "1.10.0"),
    ]
    assert all(item.source_dir.is_relative_to(newer_root) for item in items)


def test_scan_marketplace_stops_when_cancelled(tmp_path):
    source_dir = tmp_path / "source"
    _write_metadata(
        source_dir / "app",
        "app_meta.json",
        {"id": "app", "name": "App", "version": "1.0.0"},
    )

    assert scan_marketplace([source_dir], is_cancelled=lambda: True) == []