"""Tests for AppRegistry discovery and app_meta.json validation."""

import json
from pathlib import Path

import pytest

from qhub.core.app_state import AppHealth, AppState


class TestAppEntry:
    def test_app_id_from_meta(self):
        from qhub.core.app_registry import AppEntry

        entry = AppEntry(Path("/fake"), {"id": "my_app", "name": "My App"})
        assert entry.app_id == "my_app"
        assert entry.app_name == "My App"

    def test_app_name_falls_back_to_id(self):
        from qhub.core.app_registry import AppEntry

        entry = AppEntry(Path("/fake"), {"id": "my_app"})
        assert entry.app_name == "my_app"

    def test_fresh_entry_is_discovered(self):
        from qhub.core.app_registry import AppEntry

        entry = AppEntry(Path("/fake"), {"id": "x"})
        assert entry.health.state == AppState.DISCOVERED
        assert entry.instance is None


class TestRegistryDiscover:
    """Test the pure discovery phase (no loading, no uv)."""

    def _make_registry(self, apps_dir: Path):
        """Create a registry with a stubbed UvBridge (discovery doesn't need uv)."""
        from unittest.mock import MagicMock
        from qhub.core.app_registry import AppRegistry

        mock_uv = MagicMock()
        return AppRegistry(apps_dir, mock_uv)

    def test_discover_valid_app(self, tmp_apps_dir, make_app_dir):
        make_app_dir({"id": "alpha", "name": "Alpha"})
        registry = self._make_registry(tmp_apps_dir)
        found = registry.discover()
        assert len(found) == 1
        assert found[0].app_id == "alpha"

    def test_discover_multiple_apps(self, tmp_apps_dir, make_app_dir):
        make_app_dir({"id": "a", "name": "A"})
        make_app_dir({"id": "b", "name": "B"})
        registry = self._make_registry(tmp_apps_dir)
        found = registry.discover()
        assert len(found) == 2
        assert {e.app_id for e in found} == {"a", "b"}

    def test_skip_missing_id(self, tmp_apps_dir):
        d = tmp_apps_dir / "bad_app"
        d.mkdir()
        (d / "app_meta.json").write_text(
            json.dumps({"name": "No ID"}), encoding="utf-8"
        )
        registry = self._make_registry(tmp_apps_dir)
        found = registry.discover()
        assert len(found) == 0

    def test_skip_invalid_json(self, tmp_apps_dir):
        d = tmp_apps_dir / "broken"
        d.mkdir()
        (d / "app_meta.json").write_text("{not valid json", encoding="utf-8")
        registry = self._make_registry(tmp_apps_dir)
        found = registry.discover()
        assert len(found) == 0

    def test_skip_directory_without_meta(self, tmp_apps_dir):
        (tmp_apps_dir / "random_folder").mkdir()
        registry = self._make_registry(tmp_apps_dir)
        found = registry.discover()
        assert len(found) == 0

    def test_creates_apps_dir_if_missing(self, tmp_path):
        apps_dir = tmp_path / "nonexistent"
        registry = self._make_registry(apps_dir)
        found = registry.discover()
        assert found == []
        assert apps_dir.exists()

    def test_duplicate_id_ignored(self, tmp_apps_dir, make_app_dir):
        make_app_dir({"id": "dup", "name": "First"})
        # Manually create a second directory with the same id
        d2 = tmp_apps_dir / "dup_copy"
        d2.mkdir()
        (d2 / "app_meta.json").write_text(
            json.dumps({"id": "dup", "name": "Second"}), encoding="utf-8"
        )
        registry = self._make_registry(tmp_apps_dir)
        found = registry.discover()
        assert len(found) == 1
        assert found[0].app_id == "dup"
