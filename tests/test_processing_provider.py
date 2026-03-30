from unittest.mock import MagicMock

from qgarage.core.app_registry import AppEntry, ToolboxEntry
from qgarage.core.base_app import BaseApp, InputType, OutputType
from qgarage.core.processing_provider import (
    QGarageProcessingAlgorithm,
    QGarageProcessingProvider,
    SHOW_CONSOLE_PARAM,
)


class ExampleApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input("distance", "Distance", InputType.FLOAT, default=25.0)

    def execute_logic(self, inputs):
        return {"status": "success", "message": str(inputs["distance"])}


class DummyRegistry:
    def __init__(self, entries, toolboxes, apps):
        self.entries = entries
        self.toolbox_entries = toolboxes
        self.uv_bridge = MagicMock()
        self._apps = apps

    def load_app(self, app_id):
        return self._apps.get(app_id)


def _make_app(app_id, name):
    return ExampleApp(app_meta={"id": app_id, "name": name}, app_dir=MagicMock())


def test_provider_groups_algorithms_by_toolbox():
    toolbox_entry = ToolboxEntry(
        MagicMock(),
        {"id": "sample_toolbox", "name": "Sample Toolbox"},
    )
    toolbox_app_entry = AppEntry(
        MagicMock(),
        {"id": "buffer_tool", "name": "Buffer Tool", "description": "Buffers data"},
        parent_toolbox_id="sample_toolbox",
    )
    standalone_entry = AppEntry(
        MagicMock(),
        {"id": "hello_world", "name": "Hello World"},
    )

    registry = DummyRegistry(
        entries={
            toolbox_app_entry.app_id: toolbox_app_entry,
            standalone_entry.app_id: standalone_entry,
        },
        toolboxes={toolbox_entry.toolbox_id: toolbox_entry},
        apps={
            toolbox_app_entry.app_id: _make_app("buffer_tool", "Buffer Tool"),
            standalone_entry.app_id: _make_app("hello_world", "Hello World"),
        },
    )

    provider = QGarageProcessingProvider(registry)
    provider.loadAlgorithms()
    algorithms = provider.algorithms()

    grouped = {algorithm.name(): algorithm.group() for algorithm in algorithms}
    assert grouped["buffer_tool"] == "Sample Toolbox"
    assert grouped["hello_world"] == "Apps"


def test_algorithm_process_uses_isolated_runner(monkeypatch):
    entry = AppEntry(
        MagicMock(),
        {"id": "buffer_tool", "name": "Buffer Tool"},
        parent_toolbox_id="sample_toolbox",
    )
    toolbox_entry = ToolboxEntry(
        MagicMock(),
        {"id": "sample_toolbox", "name": "Sample Toolbox"},
    )
    app = _make_app("buffer_tool", "Buffer Tool")
    registry = DummyRegistry(
        entries={entry.app_id: entry},
        toolboxes={toolbox_entry.toolbox_id: toolbox_entry},
        apps={entry.app_id: app},
    )

    captured = {}

    def fake_run(app_instance, uv_bridge, inputs, show_console=True):
        captured["app"] = app_instance
        captured["uv_bridge"] = uv_bridge
        captured["inputs"] = inputs
        captured["show_console"] = show_console
        return {"status": "success", "message": "done"}

    monkeypatch.setattr("qgarage.core.processing_provider.run_app_isolated", fake_run)

    algorithm = QGarageProcessingAlgorithm(registry, entry)
    algorithm.initAlgorithm({})
    feedback = MagicMock()

    result = algorithm.processAlgorithm({"distance": 42.5}, None, feedback)

    assert captured["app"] is app
    assert captured["uv_bridge"] is registry.uv_bridge
    assert captured["inputs"] == {"distance": 42.5}
    assert captured["show_console"] is False
    assert result == {"STATUS": "success", "MESSAGE": "done"}


def test_algorithm_process_can_show_console(monkeypatch):
    entry = AppEntry(
        MagicMock(),
        {"id": "buffer_tool", "name": "Buffer Tool"},
        parent_toolbox_id="sample_toolbox",
    )
    toolbox_entry = ToolboxEntry(
        MagicMock(),
        {"id": "sample_toolbox", "name": "Sample Toolbox"},
    )
    app = _make_app("buffer_tool", "Buffer Tool")
    registry = DummyRegistry(
        entries={entry.app_id: entry},
        toolboxes={toolbox_entry.toolbox_id: toolbox_entry},
        apps={entry.app_id: app},
    )

    captured = {}

    def fake_run(app_instance, uv_bridge, inputs, show_console=True):
        captured["show_console"] = show_console
        return {"status": "success", "message": "done"}

    monkeypatch.setattr("qgarage.core.processing_provider.run_app_isolated", fake_run)

    algorithm = QGarageProcessingAlgorithm(registry, entry)
    algorithm.initAlgorithm({})

    algorithm.processAlgorithm(
        {"distance": 10.0, SHOW_CONSOLE_PARAM: True}, None, MagicMock()
    )

    assert captured["show_console"] is True


def test_algorithm_exposes_declared_outputs(monkeypatch):
    """Test that apps with add_output() declarations expose those outputs."""

    class AppWithOutputs(BaseApp):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.add_input("input_value", "Input", InputType.INTEGER, default=10)
            self.add_output("result_count", "Result Count", OutputType.INTEGER)
            self.add_output("result_file", "Result File", OutputType.FILE)

        def execute_logic(self, inputs):
            return {
                "status": "success",
                "message": "Processed",
                "result_count": inputs["input_value"] * 2,
                "result_file": "/path/to/output.txt",
            }

    entry = AppEntry(
        MagicMock(),
        {"id": "output_test", "name": "Output Test"},
    )
    app = AppWithOutputs(
        app_meta={"id": "output_test", "name": "Output Test"}, app_dir=MagicMock()
    )
    registry = DummyRegistry(
        entries={entry.app_id: entry}, toolboxes={}, apps={entry.app_id: app}
    )

    def fake_run(app_instance, uv_bridge, inputs, show_console=True):
        return app_instance.execute_logic(inputs)

    monkeypatch.setattr("qgarage.core.processing_provider.run_app_isolated", fake_run)

    algorithm = QGarageProcessingAlgorithm(registry, entry)
    algorithm.initAlgorithm({})

    # Check that outputs were registered
    output_defs = algorithm.outputDefinitions()
    output_names = [o.name() for o in output_defs]
    assert "result_count" in output_names
    assert "result_file" in output_names
    assert (
        "STATUS" not in output_names
    )  # STATUS/MESSAGE are returned but not registered as outputs
    assert "MESSAGE" not in output_names

    # Check that outputs are returned correctly
    result = algorithm.processAlgorithm({"input_value": 5}, None, MagicMock())
    assert result["result_count"] == 10  # 5 * 2
    assert result["result_file"] == "/path/to/output.txt"
    assert result["STATUS"] == "success"
    assert result["MESSAGE"] == "Processed"


def test_algorithm_without_outputs_maintains_backward_compatibility(monkeypatch):
    """Test that apps without add_output() calls still work as before."""
    entry = AppEntry(
        MagicMock(),
        {"id": "buffer_tool", "name": "Buffer Tool"},
    )
    app = _make_app("buffer_tool", "Buffer Tool")
    registry = DummyRegistry(
        entries={entry.app_id: entry}, toolboxes={}, apps={entry.app_id: app}
    )

    def fake_run(app_instance, uv_bridge, inputs, show_console=True):
        return {"status": "success", "message": "done", "extra_key": "ignored"}

    monkeypatch.setattr("qgarage.core.processing_provider.run_app_isolated", fake_run)

    algorithm = QGarageProcessingAlgorithm(registry, entry)
    algorithm.initAlgorithm({})

    # No custom outputs should be registered
    output_defs = algorithm.outputDefinitions()
    assert len(output_defs) == 0

    # Should still return STATUS and MESSAGE
    result = algorithm.processAlgorithm({"distance": 42.5}, None, MagicMock())
    assert result == {"STATUS": "success", "MESSAGE": "done"}
    # extra_key is not exposed because no output was declared for it
    assert "extra_key" not in result
