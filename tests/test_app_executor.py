import tempfile
from pathlib import Path
from typing import Any, cast

from qgarage.core.app_executor import IsolatedAppRun, run_app_isolated


class FakeProcess:
    def __init__(self, poll_values=None):
        self._poll_values = list(poll_values or [])
        self.terminate_called = False
        self.kill_called = False

    def poll(self):
        if self._poll_values:
            return self._poll_values.pop(0)
        return None

    def terminate(self):
        self.terminate_called = True

    def wait(self, timeout=None):
        if self.terminate_called:
            return 0
        return None

    def kill(self):
        self.kill_called = True


def test_run_app_isolated_stops_lingering_process(monkeypatch, tmp_path):
    output_path = tmp_path / "output.json"
    output_path.write_text('{"status":"success","message":"done"}', encoding="utf-8")

    stderr_path = tmp_path / "stderr.log"
    stderr_path.write_text("", encoding="utf-8")

    fake_process = FakeProcess(poll_values=[None])
    temp_dir = tempfile.TemporaryDirectory()

    def fake_start(app, uv_bridge, inputs, show_console=True):
        return IsolatedAppRun(
            process=cast(Any, fake_process),
            output_path=output_path,
            stderr_log_path=stderr_path,
            tmp_dir=temp_dir,
            tmp_path=Path(temp_dir.name),
        )

    monkeypatch.setattr("qgarage.core.app_executor.start_isolated_app_run", fake_start)

    result = run_app_isolated(
        app=cast(Any, object()),
        uv_bridge=cast(Any, object()),
        inputs={},
    )

    assert result == {"status": "success", "message": "done"}
    assert fake_process.terminate_called is True


def test_run_app_isolated_times_out_without_output(monkeypatch, tmp_path):
    stderr_path = tmp_path / "stderr.log"
    stderr_path.write_text("runner stuck", encoding="utf-8")

    fake_process = FakeProcess(poll_values=[None, None, None])
    temp_dir = tempfile.TemporaryDirectory()

    def fake_start(app, uv_bridge, inputs, show_console=True):
        return IsolatedAppRun(
            process=cast(Any, fake_process),
            output_path=tmp_path / "missing_output.json",
            stderr_log_path=stderr_path,
            tmp_dir=temp_dir,
            tmp_path=Path(temp_dir.name),
        )

    # Force immediate timeout path.
    monkeypatch.setattr("qgarage.core.app_executor.start_isolated_app_run", fake_start)
    monkeypatch.setattr("qgarage.core.app_executor.PROCESS_TIMEOUT_SECONDS", 0)

    result = run_app_isolated(
        app=cast(Any, object()),
        uv_bridge=cast(Any, object()),
        inputs={},
    )

    assert result["status"] == "error"
    assert "timed out" in result["message"]
    assert result["traceback"] == "runner stuck"
    assert fake_process.terminate_called is True
