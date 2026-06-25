"""Tests for UvBridge Windows launch quoting and SSL env sanitization."""

import json
import os
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
    with (
        patch("subprocess.run") as mock_run,
        patch("shutil.which", return_value="/usr/bin/uv"),
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
            f"{subprocess.list2cmdline(command)} || pause",
        ]


def test_normalize_ssl_cert_dir_accepts_existing_directories(tmp_path):
    certs_a = tmp_path / "certs-a"
    certs_b = tmp_path / "certs-b"
    certs_a.mkdir()
    certs_b.mkdir()

    value = f'"{certs_a}"{os.pathsep}"{certs_b}"'

    assert _normalize_ssl_cert_dir(value) == f"{certs_a}{os.pathsep}{certs_b}"


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


def test_install_requirements_reports_context_on_failure(uv_bridge, tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("requests\n", encoding="utf-8")
    venv_path = tmp_path / ".venv"
    venv_path.mkdir()

    error = subprocess.CalledProcessError(
        1,
        ["uv", "pip", "install"],
        output="download log",
        stderr="resolution failed",
    )

    with patch("subprocess.run", side_effect=error):
        with pytest.raises(RuntimeError) as exc:
            uv_bridge.install_requirements(tmp_path)

    message = str(exc.value)
    assert "install uv requirements" in message
    assert "download log" in message
    assert "resolution failed" in message


def test_verify_uv_falls_back_to_candidate_dirs_on_windows(tmp_path):
    """Test that _verify_uv checks candidate directories when 'uv' is not on PATH."""
    fake_uv_dir = tmp_path / ".local" / "bin"
    fake_uv_dir.mkdir(parents=True)
    fake_uv_exe = fake_uv_dir / "uv.exe"
    fake_uv_exe.write_text("", encoding="utf-8")

    # Mock the candidate dirs list to use our tmp_path
    fake_candidates = [
        tmp_path / ".local" / "bin",
        tmp_path / "AppData" / "Roaming" / "uv" / "bin",
    ]

    with (
        patch("qgarage.core.uv_bridge.platform.system", return_value="Windows"),
        patch("qgarage.core.uv_bridge._UV_CANDIDATE_DIRS_WIN", fake_candidates),
        patch("shutil.which", return_value=None),  # Simulate uv not on PATH
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(stdout="uv 0.8.0")
        bridge = UvBridge("uv")
        # Should not raise, should find it in .local/bin
        assert bridge.uv_exe == str(fake_uv_exe)


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
    python_exe = tmp_path / ".venv" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_text("", encoding="utf-8")

    with (
        patch("qgarage.core.uv_bridge.platform.system", return_value="Windows"),
        patch.object(uv_bridge, "ensure_env") as ensure_env,
        patch.object(uv_bridge, "_python_exe", return_value=python_exe),
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
    ensure_env.assert_called_once_with(tmp_path)

    inner_command = [
        str(python_exe),
        str(runner),
        str(config),
    ]
    assert cmd == [
        "cmd.exe",
        "/d",
        "/s",
        "/c",
        f"{subprocess.list2cmdline(inner_command)} || pause",
    ]

    env = mock_popen.call_args.kwargs["env"]
    assert "SSL_CERT_DIR" not in env
    assert str(tmp_path / "site-packages") in env["PYTHONPATH"]
