from __future__ import annotations

import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .subprocess_runner import RUNNER_SCRIPT, serialize_inputs

if TYPE_CHECKING:
    import subprocess

    from .base_app import BaseApp
    from .uv_bridge import UvBridge


@dataclass
class IsolatedAppRun:
    process: "subprocess.Popen"
    output_path: Path
    stderr_log_path: Path
    tmp_dir: tempfile.TemporaryDirectory
    tmp_path: Path


POLL_INTERVAL_SECONDS = 0.1
PROCESS_TIMEOUT_SECONDS = 900
TERMINATE_GRACE_SECONDS = 2


def start_isolated_app_run(
    app: "BaseApp",
    uv_bridge: "UvBridge",
    inputs: dict[str, Any],
    show_console: bool = True,
) -> IsolatedAppRun:
    """Prepare and launch an isolated subprocess for an app run."""
    tmp_dir = tempfile.TemporaryDirectory(prefix="qgarage_run_")
    tmp_path = Path(tmp_dir.name)

    serialised = serialize_inputs(inputs, tmp_path)

    inputs_path = tmp_path / "inputs.json"
    output_path = tmp_path / "output.json"
    runner_path = tmp_path / "runner.py"
    config_path = tmp_path / "config.json"
    stderr_log_path = tmp_path / "stderr.log"

    inputs_path.write_text(json.dumps(serialised, default=str), encoding="utf-8")
    runner_path.write_text(RUNNER_SCRIPT, encoding="utf-8")

    import qgarage

    plugin_dir = Path(qgarage.__file__).parent
    requirements_path = app.app_dir / "requirements.txt"
    venv_site_packages = uv_bridge.get_site_packages(app.app_dir)

    config = {
        "inputs_path": str(inputs_path),
        "output_path": str(output_path),
        "plugin_dir": str(plugin_dir),
        "app_dir": str(app.app_dir),
        "module_path": str(app.app_dir / app.app_meta.get("entry_point", "main.py")),
        "class_name": app.app_meta.get("class_name", "App"),
        "app_meta": dict(app.app_meta),
        "stderr_log_path": str(stderr_log_path),
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")

    process = uv_bridge.launch_app_isolated(
        runner_path=runner_path,
        config_path=config_path,
        requirements_path=requirements_path if requirements_path.exists() else None,
        venv_site_packages=venv_site_packages,
        show_console=show_console,
    )

    return IsolatedAppRun(
        process=process,
        output_path=output_path,
        stderr_log_path=stderr_log_path,
        tmp_dir=tmp_dir,
        tmp_path=tmp_path,
    )


def run_app_isolated(
    app: "BaseApp",
    uv_bridge: "UvBridge",
    inputs: dict[str, Any],
    show_console: bool = True,
) -> dict[str, Any]:
    """Run an app to completion in an isolated subprocess and return its result."""
    run = start_isolated_app_run(app, uv_bridge, inputs, show_console=show_console)
    try:
        start_time = time.monotonic()
        while True:
            if run.output_path.exists():
                with open(run.output_path, encoding="utf-8") as f:
                    result = json.load(f)
                _stop_lingering_process(run.process)
                return result

            exit_code = run.process.poll()
            if exit_code is not None:
                break

            if time.monotonic() - start_time > PROCESS_TIMEOUT_SECONDS:
                _stop_lingering_process(run.process)
                result = {
                    "status": "error",
                    "message": (
                        "Isolated app process timed out before producing output "
                        f"({PROCESS_TIMEOUT_SECONDS}s)"
                    ),
                }
                if run.stderr_log_path.exists():
                    stderr_text = run.stderr_log_path.read_text(
                        encoding="utf-8"
                    ).strip()
                    if stderr_text:
                        result["traceback"] = stderr_text
                return result

            time.sleep(POLL_INTERVAL_SECONDS)

        if run.output_path.exists():
            with open(run.output_path, encoding="utf-8") as f:
                return json.load(f)

        stderr_text = ""
        if run.stderr_log_path.exists():
            stderr_text = run.stderr_log_path.read_text(encoding="utf-8").strip()

        message = (
            "Isolated app process exited before producing output"
            if exit_code == 0
            else f"Isolated app process exited with code {exit_code}"
        )
        result = {"status": "error", "message": message}
        if stderr_text:
            result["traceback"] = stderr_text
        return result
    finally:
        run.tmp_dir.cleanup()


def _stop_lingering_process(process: "subprocess.Popen") -> None:
    """Best-effort shutdown for orphaned runner processes."""
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=TERMINATE_GRACE_SECONDS)
    except Exception:
        try:
            process.kill()
        except Exception:
            return
