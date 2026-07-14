from pathlib import Path

from qgarage.core.base_app import BaseApp, InputType
from qgarage.core.subprocess_runner import build_app_state_snapshot, build_isolated_run_config


class SnapshotApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input("name", "Name", InputType.STRING, default="demo")
        self.custom_path = Path("/tmp/demo")
        self.custom_flag = True

    def execute_logic(self, inputs):
        return {"status": "success", "message": inputs.get("name", "")}


def test_build_isolated_run_config_prefers_app_dir_before_plugin_parent(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    plugin_dir = tmp_path / "plugins" / "qgarage"
    plugin_dir.mkdir(parents=True)

    config = build_isolated_run_config(
        app_dir=app_dir,
        app_meta={"id": "demo", "name": "Demo"},
        plugin_dir=plugin_dir,
        inputs_path=tmp_path / "inputs.json",
        output_path=tmp_path / "output.json",
        stderr_log_path=tmp_path / "stderr.log",
        keep_open=False,
    )

    assert config["import_paths"] == [str(app_dir), str(plugin_dir.parent)]


def test_build_isolated_run_config_includes_pixi_snapshot(tmp_path):
    app_dir = tmp_path / "pixi_app"
    app_dir.mkdir()
    (app_dir / "pixi.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    plugin_dir = tmp_path / "plugins" / "qgarage"
    plugin_dir.mkdir(parents=True)

    app = SnapshotApp(app_meta={"id": "demo", "name": "Demo"}, app_dir=app_dir)

    config = build_isolated_run_config(
        app_dir=app_dir,
        app_meta=app.app_meta,
        plugin_dir=plugin_dir,
        inputs_path=tmp_path / "inputs.json",
        output_path=tmp_path / "output.json",
        stderr_log_path=tmp_path / "stderr.log",
        keep_open=False,
        app_instance=app,
    )

    assert config["skip_subclass_init"] is True
    assert config["app_state"]["custom_flag"] is True
    assert config["app_state"]["custom_path"] == {
        "__qgarage_type__": "path",
        "value": str(Path("/tmp/demo")),
    }


def test_build_app_state_snapshot_skips_qt_runtime_fields(tmp_path):
    app = SnapshotApp(app_meta={"id": "demo", "name": "Demo"}, app_dir=tmp_path)
    app._widget = object()
    app._monitor = object()

    snapshot = build_app_state_snapshot(app)

    assert "_widget" not in snapshot
    assert "_monitor" not in snapshot
    assert snapshot["custom_flag"] is True