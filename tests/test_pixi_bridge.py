"""Tests for PixiBridge command construction and site-packages resolution."""

import json
import platform
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from qgarage.core.pixi_bridge import (
    PixiBridge,
    _build_pixi_env,
    _resolve_pixi_executable,
)

# ---------------------------------------------------------------------------
# _resolve_pixi_executable
# ---------------------------------------------------------------------------


class TestResolvePixiExecutable:
    def test_returns_requested_when_which_finds_it(self):
        with patch("shutil.which", return_value="/usr/bin/pixi"):
            assert _resolve_pixi_executable("pixi") == "pixi"

    def test_falls_back_to_augmented_path(self, tmp_path):
        """When default PATH fails but augmented PATH succeeds."""
        pixi_bin = tmp_path / "pixi_bin"
        pixi_bin.mkdir()
        exe = pixi_bin / ("pixi.exe" if platform.system() == "Windows" else "pixi")
        exe.write_text("fake", encoding="utf-8")

        def which_side_effect(name, path=None):
            if path is None:
                return None
            # Simulate finding it in augmented PATH
            if str(pixi_bin) in (path or ""):
                return str(exe)
            return None

        with patch("shutil.which", side_effect=which_side_effect), patch(
            "qgarage.core.pixi_bridge._PIXI_CANDIDATE_DIRS_WIN"
            if platform.system() == "Windows"
            else "qgarage.core.pixi_bridge._PIXI_CANDIDATE_DIRS_UNIX",
            [pixi_bin],
        ):
            result = _resolve_pixi_executable("pixi")
            assert result == str(exe)

    def test_returns_requested_as_fallback(self, tmp_path):
        """When nothing is found, return raw value for _verify_pixi to raise."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with patch("shutil.which", return_value=None), patch(
            "qgarage.core.pixi_bridge._PIXI_CANDIDATE_DIRS_WIN", [empty_dir]
        ), patch(
            "qgarage.core.pixi_bridge._PIXI_CANDIDATE_DIRS_UNIX", [empty_dir]
        ):
            result = _resolve_pixi_executable("pixi")
            assert result == "pixi"


# ---------------------------------------------------------------------------
# PixiBridge construction
# ---------------------------------------------------------------------------


class TestPixiBridgeInit:
    def test_verify_pixi_called(self):
        """PixiBridge() should call pixi --version to verify."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="pixi 0.40.0")
            with patch("shutil.which", return_value="/usr/bin/pixi"):
                bridge = PixiBridge("pixi")
                assert bridge.pixi_exe == "pixi"
                mock_run.assert_called_once()
                cmd = mock_run.call_args[0][0]
                assert cmd == ["pixi", "--version"]

    def test_raises_when_pixi_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with patch("shutil.which", return_value=None):
                with pytest.raises(RuntimeError, match="pixi executable not found"):
                    PixiBridge("nonexistent_pixi")


# ---------------------------------------------------------------------------
# Helper: create a PixiBridge with mocked verification
# ---------------------------------------------------------------------------


@pytest.fixture
def pixi_bridge():
    """Return a PixiBridge whose __init__ verification is bypassed."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="pixi 0.40.0")
        with patch("shutil.which", return_value="/usr/bin/pixi"):
            return PixiBridge("pixi")


# ---------------------------------------------------------------------------
# ensure_env
# ---------------------------------------------------------------------------


def test_build_pixi_env_removes_python_poisoning_vars(monkeypatch):
    monkeypatch.setenv("PYTHONHOME", "bad-home")
    monkeypatch.setenv("PYTHONPATH", "bad-path")
    monkeypatch.setenv("PATH", "ok")

    env = _build_pixi_env()

    assert "PYTHONHOME" not in env
    assert "PYTHONPATH" not in env
    assert env["PATH"] == "ok"


class TestEnsureEnv:
    def test_runs_pixi_install(self, pixi_bridge, tmp_path):
        manifest = tmp_path / "pixi.toml"
        manifest.write_text("[project]\nname = 'test'\n", encoding="utf-8")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ready", stderr="")
            pixi_bridge.ensure_env(tmp_path)
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "pixi"
            assert "install" in cmd
            assert "--manifest-path" in cmd
            assert str(manifest) in cmd
            assert mock_run.call_args.kwargs["cwd"] == str(tmp_path)
            assert "PYTHONHOME" not in mock_run.call_args.kwargs["env"]

    def test_skips_when_no_pixi_toml(self, pixi_bridge, tmp_path):
        """No pixi.toml → no subprocess call."""
        with patch("subprocess.run") as mock_run:
            pixi_bridge.ensure_env(tmp_path)
            mock_run.assert_not_called()

    def test_ensure_env_error_includes_command_context(self, pixi_bridge, tmp_path):
        manifest = tmp_path / "pixi.toml"
        manifest.write_text("[project]\nname = 'test'\n", encoding="utf-8")

        with patch("subprocess.run") as mock_run:
            error = subprocess.CalledProcessError(
                1,
                ["pixi", "install"],
                output="solver log",
                stderr="dependency failure",
            )
            mock_run.side_effect = error
            with pytest.raises(RuntimeError) as exc:
                pixi_bridge.ensure_env(tmp_path)

        message = str(exc.value)
        assert "Failed to install pixi environment" in message
        assert "solver log" in message
        assert "dependency failure" in message


# ---------------------------------------------------------------------------
# get_site_packages
# ---------------------------------------------------------------------------


class TestGetSitePackages:
    def test_returns_path_when_exists(self, pixi_bridge, tmp_path):
        if platform.system() == "Windows":
            sp = tmp_path / ".pixi" / "envs" / "default" / "Lib" / "site-packages"
        else:
            sp = (
                tmp_path
                / ".pixi"
                / "envs"
                / "default"
                / "lib"
                / "python3.11"
                / "site-packages"
            )
        sp.mkdir(parents=True)

        result = pixi_bridge.get_site_packages(tmp_path)
        assert result == str(sp)

    def test_returns_none_when_missing(self, pixi_bridge, tmp_path):
        result = pixi_bridge.get_site_packages(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# launch_app_isolated — command construction
# ---------------------------------------------------------------------------


class TestLaunchAppIsolated:
    def test_command_includes_pixi_run(self, pixi_bridge, tmp_path):
        runner = tmp_path / "runner.py"
        runner.write_text("pass", encoding="utf-8")

        config_data = {
            "app_dir": str(tmp_path),
            "inputs_path": str(tmp_path / "inputs.json"),
            "output_path": str(tmp_path / "output.json"),
            "plugin_dir": str(tmp_path),
            "module_path": str(tmp_path / "main.py"),
            "class_name": "App",
            "app_meta": {},
        }
        config = tmp_path / "config.json"
        config.write_text(json.dumps(config_data), encoding="utf-8")

        manifest = tmp_path / "pixi.toml"
        manifest.write_text("[project]\nname = 'test'\n", encoding="utf-8")

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            process = pixi_bridge.launch_app_isolated(
                runner_path=runner,
                config_path=config,
                show_window=False,
            )

            assert process.pid == 12345
            call_args = mock_popen.call_args
            cmd = call_args[0][0]

            # Verify command structure: pixi run --manifest-path <path> python <runner> <config>
            assert cmd[0] == "pixi"
            assert cmd[1] == "run"
            assert "--manifest-path" in cmd
            manifest_idx = cmd.index("--manifest-path")
            assert cmd[manifest_idx + 1] == str(manifest)
            assert "python" in cmd
            assert str(runner) in cmd
            assert str(config) in cmd

    def test_explicit_manifest_path(self, pixi_bridge, tmp_path):
        runner = tmp_path / "runner.py"
        runner.write_text("pass", encoding="utf-8")
        config = tmp_path / "config.json"
        config.write_text("{}", encoding="utf-8")
        manifest = tmp_path / "custom_pixi.toml"
        manifest.write_text("[project]\nname = 'test'\n", encoding="utf-8")

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=1)

            pixi_bridge.launch_app_isolated(
                runner_path=runner,
                config_path=config,
                manifest_path=manifest,
                show_window=False,
            )

            cmd = mock_popen.call_args[0][0]
            manifest_idx = cmd.index("--manifest-path")
            assert cmd[manifest_idx + 1] == str(manifest)

    def test_pythonpath_set_for_site_packages(self, pixi_bridge, tmp_path):
        runner = tmp_path / "runner.py"
        runner.write_text("pass", encoding="utf-8")

        config_data = {"app_dir": str(tmp_path)}
        config = tmp_path / "config.json"
        config.write_text(json.dumps(config_data), encoding="utf-8")

        manifest = tmp_path / "pixi.toml"
        manifest.write_text("[project]\nname = 'test'\n", encoding="utf-8")

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=1)

            pixi_bridge.launch_app_isolated(
                runner_path=runner,
                config_path=config,
                venv_site_packages="/fake/site-packages",
                show_window=False,
            )

            env = mock_popen.call_args[1].get("env", {})
            assert "/fake/site-packages" in env.get("PYTHONPATH", "")

    def test_no_uv_flags_in_command(self, pixi_bridge, tmp_path):
        """Pixi commands must not include uv-specific flags."""
        runner = tmp_path / "runner.py"
        runner.write_text("pass", encoding="utf-8")

        config_data = {"app_dir": str(tmp_path)}
        config = tmp_path / "config.json"
        config.write_text(json.dumps(config_data), encoding="utf-8")

        manifest = tmp_path / "pixi.toml"
        manifest.write_text("[project]\nname = 'test'\n", encoding="utf-8")

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=1)

            pixi_bridge.launch_app_isolated(
                runner_path=runner,
                config_path=config,
                requirements_path=tmp_path / "requirements.txt",
                show_window=False,
            )

            cmd = mock_popen.call_args[0][0]
            assert "--isolated" not in cmd
            assert "--python" not in cmd
            assert "--with-requirements" not in cmd
            assert "uv" not in cmd
