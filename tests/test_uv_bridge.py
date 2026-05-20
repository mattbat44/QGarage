"""Tests for UvBridge Windows launch quoting and SSL env sanitization."""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from qgarage.core.uv_bridge import (
    UvBridge,
    _build_subprocess_env,
    _normalize_ssl_cert_dir,
    _wrap_windowed_command,
)


@pytest.fixture
def uv_bridge():
    """Return a UvBridge whose executable verification is mocked."""
    with patch("subprocess.run") as mock_run, patch(
        "shutil.which", return_value="/usr/bin/uv"
    ):
        mock_run.return_value = MagicMock(stdout="uv 0.8.0")
        return UvBridge("uv")


def test_wrap_windowed_command_wraps_full_command_for_cmd():
    command = [
        r"C:\Program Files\uv\uv.exe",
        "run",
        "--python",
        r"C:\Program Files\QGIS\apps\Python312\python.exe",
        "runner.py",
    ]

    with patch("qgarage.core.uv_bridge.platform.system", return_value="Windows"):
        assert _wrap_windowed_command(command, keep_open_on_failure=True) == [
            "cmd.exe",
            "/d",
            "/s",
            "/c",
            f'"{subprocess.list2cmdline(command)} || pause"',
        ]


def test_normalize_ssl_cert_dir_accepts_existing_directories(tmp_path):
    certs_a = tmp_path / "certs-a"
    certs_b = tmp_path / "certs-b"
    certs_a.mkdir()
    certs_b.mkdir()

    value = f'"{certs_a}"{subprocess.os.pathsep}"{certs_b}"'

    assert _normalize_ssl_cert_dir(value) == f"{certs_a}{subprocess.os.pathsep}{certs_b}"


def test_build_subprocess_env_drops_invalid_ssl_cert_dir(tmp_path):
    missing = tmp_path / "missing-certs"

    with (
        patch("qgarage.core.uv_bridge.platform.system", return_value="Windows"),
        patch.dict(
            "qgarage.core.uv_bridge.os.environ",
            {"SSL_CERT_DIR": str(missing), "PATH": ""},
            clear=True,
        ),
    ):
        env = _build_subprocess_env()

    assert "SSL_CERT_DIR" not in env


def test_launch_app_isolated_wraps_windows_command_and_sanitizes_env(
    uv_bridge, tmp_path
):
    runner = tmp_path / "runner.py"
    runner.write_text("pass", encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"app_dir": str(tmp_path)}), encoding="utf-8")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("requests\n", encoding="utf-8")
    invalid_certs = tmp_path / "invalid certs"

    uv_bridge.uv_exe = r"C:\Program Files\uv\uv.exe"
    python_exe = r"C:\Program Files\QGIS\apps\Python312\python.exe"

    with (
        patch("qgarage.core.uv_bridge.platform.system", return_value="Windows"),
        patch("qgarage.core.uv_bridge._resolve_headless_python_executable", return_value=python_exe),
        patch.dict(
            "qgarage.core.uv_bridge.os.environ",
            {"SSL_CERT_DIR": str(invalid_certs), "PATH": ""},
            clear=True,
        ),
        patch("subprocess.Popen") as mock_popen,
    ):
        mock_popen.return_value = MagicMock(pid=123)

        process = uv_bridge.launch_app_isolated(
            runner_path=runner,
            config_path=config,
            requirements_path=requirements,
            venv_site_packages=str(tmp_path / "site-packages"),
            show_window=True,
        )

    assert process.pid == 123

    cmd = mock_popen.call_args[0][0]
    inner_command = [
        uv_bridge.uv_exe,
        "run",
        "--isolated",
        "--python",
        python_exe,
        "--with-requirements",
        str(requirements),
        str(runner),
        str(config),
    ]
    assert cmd == [
        "cmd.exe",
        "/d",
        "/s",
        "/c",
        f'"{subprocess.list2cmdline(inner_command)} || pause"',
    ]

    env = mock_popen.call_args.kwargs["env"]
    assert "SSL_CERT_DIR" not in env
    assert str(tmp_path / "site-packages") in env["PYTHONPATH"]
