"""Tests for EnvBridge protocol and resolve_bridge_for_app factory."""

from __future__ import annotations

import json
import sys
import types
from unittest.mock import MagicMock

import pytest

from qgarage.core.env_bridge import (
    resolve_backend_for_app,
    resolve_bridge_for_app,
    resolve_env_dir_for_app,
)

# ---------------------------------------------------------------------------
# resolve_bridge_for_app
# ---------------------------------------------------------------------------


class TestResolveBridgeForApp:
    def test_returns_pixi_when_pixi_toml_exists(self, tmp_path):
        (tmp_path / "pixi.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
        pixi = MagicMock()
        uv = MagicMock()

        result = resolve_bridge_for_app(tmp_path, pixi, uv)
        assert result is pixi

    def test_returns_uv_when_no_pixi_toml(self, tmp_path):
        uv = MagicMock()
        pixi = MagicMock()

        result = resolve_bridge_for_app(tmp_path, pixi, uv)
        assert result is uv

    def test_returns_uv_when_only_requirements_txt(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")
        uv = MagicMock()
        pixi = MagicMock()

        result = resolve_bridge_for_app(tmp_path, pixi, uv)
        assert result is uv

    def test_pixi_takes_precedence_when_both_exist(self, tmp_path):
        """When both pixi.toml and requirements.txt exist, pixi wins."""
        (tmp_path / "pixi.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
        (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")
        pixi = MagicMock()
        uv = MagicMock()

        result = resolve_bridge_for_app(tmp_path, pixi, uv)
        assert result is pixi

    def test_falls_back_to_uv_when_pixi_bridge_is_none(self, tmp_path):
        """If pixi bridge isn't available, use uv even with pixi.toml."""
        (tmp_path / "pixi.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
        uv = MagicMock()

        result = resolve_bridge_for_app(tmp_path, None, uv)
        assert result is uv

    def test_returns_pixi_when_uv_bridge_is_none(self, tmp_path):
        """If only pixi is available and pixi.toml exists, use it."""
        (tmp_path / "pixi.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
        pixi = MagicMock()

        result = resolve_bridge_for_app(tmp_path, pixi, None)
        assert result is pixi

    def test_raises_when_both_bridges_none(self, tmp_path):
        with pytest.raises(RuntimeError, match="No environment backend available"):
            resolve_bridge_for_app(tmp_path, None, None)

    def test_raises_when_pixi_toml_exists_but_only_pixi_none_and_uv_none(
        self, tmp_path
    ):
        (tmp_path / "pixi.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
        with pytest.raises(RuntimeError, match="No environment backend available"):
            resolve_bridge_for_app(tmp_path, None, None)


class TestResolveEnvDirAndBackend:
    def test_prefers_app_local_env_over_toolbox(self, tmp_path):
        toolbox = tmp_path / "demo_toolbox"
        toolbox.mkdir()
        (toolbox / "toolbox_meta.json").write_text(
            '{"id":"demo_toolbox","name":"Demo"}', encoding="utf-8"
        )
        (toolbox / "pixi.toml").write_text("[project]\nname='tb'\n", encoding="utf-8")

        app_dir = toolbox / "special_app"
        app_dir.mkdir()
        (app_dir / "requirements.txt").write_text("requests\n", encoding="utf-8")

        assert resolve_env_dir_for_app(app_dir) == app_dir
        assert resolve_backend_for_app(app_dir) == "uv"

    def test_falls_back_to_toolbox_shared_env(self, tmp_path):
        toolbox = tmp_path / "shared_toolbox"
        toolbox.mkdir()
        (toolbox / "toolbox_meta.json").write_text(
            '{"id":"shared_toolbox","name":"Shared"}', encoding="utf-8"
        )
        (toolbox / "pixi.toml").write_text(
            "[project]\nname='shared'\n", encoding="utf-8"
        )

        app_dir = toolbox / "child_app"
        app_dir.mkdir()

        assert resolve_env_dir_for_app(app_dir) == toolbox
        assert resolve_backend_for_app(app_dir) == "pixi"

    def test_defaults_to_app_dir_when_no_configs_exist(self, tmp_path):
        app_dir = tmp_path / "plain_app"
        app_dir.mkdir()

        assert resolve_env_dir_for_app(app_dir) == app_dir
        assert resolve_backend_for_app(app_dir) == "uv"


# ---------------------------------------------------------------------------
# EnvBridge protocol conformance (structural checks)
# ---------------------------------------------------------------------------


def test_alias_active_qgarage_package_maps_side_by_side_namespace(monkeypatch):
    from qgarage.core.app_loader import _alias_active_qgarage_package

    root = types.ModuleType("qgarage_test")
    core = types.ModuleType("qgarage_test.core")
    base_app = types.ModuleType("qgarage_test.core.base_app")

    monkeypatch.setattr(
        "qgarage.core.app_loader.__package__", "qgarage_test.core", raising=False
    )
    monkeypatch.setitem(sys.modules, "qgarage_test", root)
    monkeypatch.setitem(sys.modules, "qgarage_test.core", core)
    monkeypatch.setitem(sys.modules, "qgarage_test.core.base_app", base_app)

    monkeypatch.delitem(sys.modules, "qgarage", raising=False)
    monkeypatch.delitem(sys.modules, "qgarage.core", raising=False)
    monkeypatch.delitem(sys.modules, "qgarage.core.base_app", raising=False)

    _alias_active_qgarage_package()

    assert sys.modules["qgarage"] is root
    assert sys.modules["qgarage.core"] is core
    assert sys.modules["qgarage.core.base_app"] is base_app


class TestProtocolConformance:
    """Verify that UvBridge and PixiBridge satisfy the EnvBridge protocol."""

    def test_uv_bridge_has_required_methods(self):
        from qgarage.core.uv_bridge import UvBridge

        assert hasattr(UvBridge, "ensure_env")
        assert hasattr(UvBridge, "get_site_packages")
        assert hasattr(UvBridge, "launch_app_isolated")

    def test_pixi_bridge_has_required_methods(self):
        from qgarage.core.pixi_bridge import PixiBridge

        assert hasattr(PixiBridge, "ensure_env")
        assert hasattr(PixiBridge, "get_site_packages")
        assert hasattr(PixiBridge, "launch_app_isolated")


# ---------------------------------------------------------------------------
# Integration: AppLoader uses resolve_bridge_for_app
# ---------------------------------------------------------------------------


class TestAppLoaderBridgeResolution:
    """Verify AppLoader picks the right bridge per-app."""

    def test_loader_uses_pixi_for_pixi_app(self, tmp_path):

        from qgarage.core.app_loader import AppLoader

        pixi = MagicMock()
        pixi.ensure_env = MagicMock()
        pixi.get_site_packages = MagicMock(return_value=None)
        uv = MagicMock()
        uv.ensure_env = MagicMock()
        uv.get_site_packages = MagicMock(return_value=None)

        app_dir = tmp_path / "pixi_app"
        app_dir.mkdir()
        (app_dir / "pixi.toml").write_text(
            "[project]\nname = 'test'\n", encoding="utf-8"
        )
        (app_dir / "app_meta.json").write_text(
            json.dumps(
                {
                    "id": "pixi_app",
                    "name": "Pixi App",
                    "entry_point": "main.py",
                    "class_name": "App",
                }
            ),
            encoding="utf-8",
        )
        (app_dir / "main.py").write_text(
            "from qgarage.core.base_app import BaseApp\n"
            "class App(BaseApp):\n"
            "    def __init__(self, **kw): super().__init__(**kw)\n"
            "    def execute_logic(self, inputs): return {'status':'ok','message':''}\n",
            encoding="utf-8",
        )

        loader = AppLoader(uv, pixi)
        from qgarage.core.app_state import AppHealth

        health = AppHealth()

        loader.load_app(
            app_dir,
            {
                "id": "pixi_app",
                "name": "Pixi App",
                "entry_point": "main.py",
                "class_name": "App",
            },
            health,
        )

        pixi.ensure_env.assert_not_called()
        uv.ensure_env.assert_not_called()

    def test_loader_uses_uv_for_requirements_only_app(self, tmp_path):
        from qgarage.core.app_loader import AppLoader

        pixi = MagicMock()
        pixi.ensure_env = MagicMock()
        pixi.get_site_packages = MagicMock(return_value=None)
        uv = MagicMock()
        uv.ensure_env = MagicMock()
        uv.get_site_packages = MagicMock(return_value=None)

        app_dir = tmp_path / "uv_app"
        app_dir.mkdir()
        (app_dir / "requirements.txt").write_text("requests\n", encoding="utf-8")
        (app_dir / "app_meta.json").write_text(
            json.dumps(
                {
                    "id": "uv_app",
                    "name": "UV App",
                    "entry_point": "main.py",
                    "class_name": "App",
                }
            ),
            encoding="utf-8",
        )
        (app_dir / "main.py").write_text(
            "from qgarage.core.base_app import BaseApp\n"
            "class App(BaseApp):\n"
            "    def __init__(self, **kw): super().__init__(**kw)\n"
            "    def execute_logic(self, inputs): return {'status':'ok','message':''}\n",
            encoding="utf-8",
        )

        loader = AppLoader(uv, pixi)
        from qgarage.core.app_state import AppHealth

        health = AppHealth()

        loader.load_app(
            app_dir,
            {
                "id": "uv_app",
                "name": "UV App",
                "entry_point": "main.py",
                "class_name": "App",
            },
            health,
        )

        uv.ensure_env.assert_not_called()
        pixi.ensure_env.assert_not_called()
