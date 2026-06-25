import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Optional

from .constants import REQUIREMENTS_FILENAME, VENV_DIR
from .logger import log_error, log_info


class _EnvSetupError(RuntimeError):
    """Raised when a persistent app environment cannot be prepared."""


_CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0
_CREATE_NEW_CONSOLE = 0x00000010 if platform.system() == "Windows" else 0

# Common uv install dirs that may not appear in QGIS's stripped PATH
_UV_CANDIDATE_DIRS_WIN = [
    Path.home() / ".local" / "bin",
    Path(os.environ.get("APPDATA", "")) / "uv" / "bin",
    Path(os.environ.get("LOCALAPPDATA", "")) / "uv" / "bin",
    Path(os.environ.get("CARGO_HOME", str(Path.home() / ".cargo"))) / "bin",
]


def _wrap_windowed_command(
    command: Sequence[str], keep_open_on_failure: bool
) -> list[str]:
    """Wrap a Windows console command so startup failures remain visible.

    IMPORTANT: Do NOT use subprocess.list2cmdline on the command before passing it here.
    This function handles all necessary quoting internally.
    """
    if platform.system() != "Windows" or not keep_open_on_failure:
        return list(command)

    # Use list2cmdline to properly quote the command components
    quoted = subprocess.list2cmdline(list(command))
    # Wrap in cmd.exe with pause on failure
    # Note: We use a single outer quote pair, not nested quotes
    return ["cmd.exe", "/d", "/s", "/c", f"{quoted} || pause"]


def _normalize_ssl_cert_dir(value: str) -> str | None:
    """Return a normalized SSL_CERT_DIR value, or None when it is unusable.

    Accepts a single directory or an ``os.pathsep``-delimited directory list,
    trims surrounding whitespace/quotes, and rejects empty or non-existent
    entries.
    """
    cleaned = value.strip().strip('"')
    if not cleaned:
        return None

    cert_dirs = [part.strip().strip('"') for part in cleaned.split(os.pathsep)]
    cert_dirs = [part for part in cert_dirs if part]
    if not cert_dirs:
        return None

    if all(Path(part).is_dir() for part in cert_dirs):
        return os.pathsep.join(cert_dirs)
    return None


def _build_subprocess_env(
    *,
    env: Optional[Mapping[str, str]] = None,
    venv_site_packages: Optional[str] = None,
) -> dict[str, str]:
    """Build a subprocess environment for uv child processes."""
    launch_env = os.environ.copy()
    if env:
        launch_env.update({k: str(v) for k, v in env.items()})

    for var in (
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONCASEOK",
        "PYTHONIOENCODING",
        "PYTHONFAULTHANDLER",
    ):
        launch_env.pop(var, None)

    if platform.system() == "Windows" and "SSL_CERT_DIR" in launch_env:
        normalized = _normalize_ssl_cert_dir(launch_env["SSL_CERT_DIR"])
        if normalized is None:
            launch_env.pop("SSL_CERT_DIR", None)
            log_info("Removed invalid SSL_CERT_DIR from uv subprocess env", "uv_bridge")
        else:
            launch_env["SSL_CERT_DIR"] = normalized

    if venv_site_packages:
        existing = launch_env.get("PYTHONPATH", "")
        launch_env["PYTHONPATH"] = (
            venv_site_packages + os.pathsep + existing
            if existing
            else venv_site_packages
        )

    return launch_env


def _resolve_uv_executable() -> str:
    """Locate uv on PATH or common install locations.

    This function is kept for backward compatibility but the logic
    is now integrated into UvBridge._verify_uv() for consistency.
    """
    uv_exe = shutil.which("uv")
    if uv_exe:
        return uv_exe

    if platform.system() == "Windows":
        for candidate_dir in _UV_CANDIDATE_DIRS_WIN:
            candidate_path = candidate_dir / "uv.exe"
            if candidate_path.exists():
                log_info(f"Found uv.exe at {candidate_path}", "uv_bridge")
                return str(candidate_path)
    else:
        # Unix-like systems
        unix_candidates = [
            Path.home() / ".local" / "bin" / "uv",
            Path.home() / ".cargo" / "bin" / "uv",
        ]
        for candidate_path in unix_candidates:
            if candidate_path.exists():
                log_info(f"Found uv at {candidate_path}", "uv_bridge")
                return str(candidate_path)

    raise FileNotFoundError(
        "uv executable not found on PATH or in standard install locations. "
        "Install uv from https://github.com/astral-sh/uv or configure its path "
        "in QGarage settings."
    )


def _resolve_headless_python_executable() -> Path:
    """Return the Python executable that QGarage apps should use.

    On Windows, prefers pythonw.exe (headless) over python.exe to avoid extra
    console windows. Falls back to the current interpreter if neither is found.
    """
    interpreter_root = Path(sys.executable).parent

    if platform.system() == "Windows":
        pythonw = interpreter_root / "pythonw.exe"
        if pythonw.exists():
            return pythonw

        python_exe = interpreter_root / "python.exe"
        if python_exe.exists():
            return python_exe

        pythonw_scripts = interpreter_root / "Scripts" / "pythonw.exe"
        if pythonw_scripts.exists():
            return pythonw_scripts

        python_scripts = interpreter_root / "Scripts" / "python.exe"
        if python_scripts.exists():
            return python_scripts

    python_bin = interpreter_root / "python"
    if python_bin.exists():
        return python_bin

    log_info(
        f"Could not find pythonw.exe or python.exe in {interpreter_root}, "
        f"falling back to {sys.executable}",
        "uv_bridge",
    )
    return Path(sys.executable)


class UvBridge:
    """Manages persistent venv creation and app subprocess launching using uv."""

    def __init__(self, uv_path: str):
        self.uv_exe = self._verify_uv(uv_path)

    def _verify_uv(self, uv_path: str) -> str:
        """Verify uv is available and return the resolved path."""
        # First try shutil.which
        resolved = shutil.which(uv_path)

        # If not found and user just provided "uv", try our candidate directories
        if resolved is None and uv_path == "uv":
            log_info(
                "uv not found on PATH, checking common install locations", "uv_bridge"
            )
            if platform.system() == "Windows":
                for candidate_dir in _UV_CANDIDATE_DIRS_WIN:
                    candidate_path = candidate_dir / "uv.exe"
                    if candidate_path.exists():
                        resolved = str(candidate_path)
                        log_info(f"Found uv.exe at {resolved}", "uv_bridge")
                        break
            else:
                # Unix-like systems
                unix_candidates = [
                    Path.home() / ".local" / "bin" / "uv",
                    Path.home() / ".cargo" / "bin" / "uv",
                ]
                for candidate_path in unix_candidates:
                    if candidate_path.exists():
                        resolved = str(candidate_path)
                        log_info(f"Found uv at {resolved}", "uv_bridge")
                        break

        if resolved is None:
            raise FileNotFoundError(f"uv executable not found: {uv_path}")

        try:
            result = subprocess.run(
                [resolved, "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
                env=_build_subprocess_env(),
                creationflags=_CREATE_NO_WINDOW,
            )
            log_info(f"Found uv: {result.stdout.strip()}", "uv_bridge")
        except FileNotFoundError as exc:
            log_error(f"Failed to verify uv at {resolved}: {exc}", "uv_bridge")
            raise RuntimeError(
                f"uv executable not found (tried: {resolved}). "
                "Install from https://docs.astral.sh/uv/"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            log_error(f"Failed to verify uv at {resolved}: {exc}", "uv_bridge")
            raise RuntimeError(
                f"uv executable verification timed out after {exc.timeout} seconds: {resolved}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            log_error(f"Failed to verify uv at {resolved}: {exc}", "uv_bridge")
            raise RuntimeError(
                f"uv executable verification failed: {resolved}"
            ) from exc

        return resolved

    def ensure_env(self, app_dir: Path) -> None:
        """Create or update a persistent app venv (idempotent)."""
        self.create_venv(app_dir)
        self.install_requirements(app_dir)

    def create_venv(self, app_dir: Path) -> Path:
        """Create an isolated venv inside an app directory.

        Returns the path to site-packages.
        """
        venv_path = app_dir / VENV_DIR
        if venv_path.exists():
            log_info(f"Venv already exists at {venv_path}", "uv_bridge")
            return self._site_packages_path(venv_path)

        cmd = [self.uv_exe, "venv", str(venv_path)]
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                cwd=str(app_dir),
                env=_build_subprocess_env(),
                creationflags=_CREATE_NO_WINDOW,
            )
        except subprocess.CalledProcessError as e:
            raise _EnvSetupError(
                self._format_setup_error(
                    action="create uv venv",
                    app_dir=app_dir,
                    cmd=cmd,
                    stdout=e.stdout,
                    stderr=e.stderr,
                )
            ) from e

        self._log_setup_output("uv venv", app_dir, result.stdout, result.stderr)
        log_info(f"Created venv at {venv_path}", "uv_bridge")
        return self._site_packages_path(venv_path)

    def install_requirements(self, app_dir: Path) -> None:
        """Install requirements.txt into the app's persistent venv.

        This creates a persistent venv with all dependencies pre-installed,
        so subsequent runs are fast. Dependencies are read from requirements.txt
        and installed using `uv pip install -r requirements.txt`.
        """
        req_file = app_dir / REQUIREMENTS_FILENAME
        venv_path = app_dir / VENV_DIR
        if not req_file.exists():
            log_info(
                f"No {REQUIREMENTS_FILENAME} in {app_dir}, skipping install",
                "uv_bridge",
            )
            return

        # Check if file is empty efficiently
        if req_file.stat().st_size == 0:
            log_info(
                f"Empty {REQUIREMENTS_FILENAME} in {app_dir}, skipping install",
                "uv_bridge",
            )
            return

        cmd = [
            self.uv_exe,
            "pip",
            "install",
            "-r",
            str(req_file),
            "--python",
            str(self._python_exe(venv_path)),
        ]
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                cwd=str(app_dir),
                env=_build_subprocess_env(),
                creationflags=_CREATE_NO_WINDOW,
            )
        except subprocess.CalledProcessError as e:
            raise _EnvSetupError(
                self._format_setup_error(
                    action="install uv requirements",
                    app_dir=app_dir,
                    cmd=cmd,
                    stdout=e.stdout,
                    stderr=e.stderr,
                )
            ) from e

        self._log_setup_output("uv pip install", app_dir, result.stdout, result.stderr)
        log_info(f"Installed requirements for {app_dir.name}", "uv_bridge")

    def launch_uvx_windowed(
        self,
        package: str,
        args: Sequence[str] = (),
        cwd: Optional[Path] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> int:
        """Launch a tool with ``uvx`` in a new console window (Windows) or terminal (Unix).

        Returns the spawned process PID.
        """
        uv_cmd = [self.uv_exe, "tool", "run", package, *args]
        return self._launch_windowed(uv_cmd, cwd=cwd, env=env)

    def launch_uv_run_windowed(
        self,
        script_path: Path,
        args: Sequence[str] = (),
        with_packages: Optional[Sequence[str]] = None,
        cwd: Optional[Path] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> int:
        """Launch ``uv run --isolated`` in a new console window (Windows) or terminal (Unix).

        Returns the spawned process PID.
        """
        uv_cmd = [self.uv_exe, "run", "--isolated"]

        if with_packages:
            for pkg in with_packages:
                uv_cmd.extend(["--with", pkg])

        uv_cmd.extend([str(script_path), *args])
        return self._launch_windowed(uv_cmd, cwd=cwd, env=env)

    def launch_app_isolated(
        self,
        runner_path: Path,
        config_path: Path,
        requirements_path: Optional[Path] = None,
        venv_site_packages: Optional[str] = None,
        show_window: bool = True,
    ) -> "subprocess.Popen":
        """Run an app's execute_logic using the app's persistent venv.

        This method uses the PERSISTENT VENV MODEL, not ephemeral execution.
        The venv is created once and reused across runs. Dependencies from
        requirements.txt are installed into the venv during ensure_env().

        Args:
            runner_path:        Path to the generated runner script.
            config_path:        Path to the JSON config file consumed by the runner.
            requirements_path:  Optional path to requirements.txt (for logging only).
            venv_site_packages: Optional path to inject via PYTHONPATH (app venv).
            show_window:        When True, open a separate console window.

        Returns:
            The Popen object for the spawned process.
        """
        import json
        import subprocess as _sp

        config = json.loads(config_path.read_text(encoding="utf-8"))
        app_dir = Path(config["app_dir"])

        # Ensure the persistent venv exists and has all requirements installed
        self.ensure_env(app_dir)

        # Use the venv's python executable
        python_exe = self._python_exe(app_dir / VENV_DIR)

        cmd = [str(python_exe), str(runner_path), str(config_path)]

        launch_env = _build_subprocess_env(venv_site_packages=venv_site_packages)

        if platform.system() == "Windows":
            creationflags = _CREATE_NEW_CONSOLE if show_window else _CREATE_NO_WINDOW
            popen_cmd = _wrap_windowed_command(cmd, keep_open_on_failure=show_window)
            process = _sp.Popen(
                popen_cmd,
                env=launch_env,
                creationflags=creationflags,
            )
        else:
            popen_kwargs = {"env": launch_env}
            if show_window:
                popen_kwargs["start_new_session"] = True
            process = _sp.Popen(cmd, **popen_kwargs)

        log_info(
            "Launched persistent venv app process "
            f"(pid={process.pid}, show_window={show_window}): {' '.join(cmd)}",
            "uv_bridge",
        )
        return process

    def _launch_windowed(
        self,
        command: Sequence[str],
        cwd: Optional[Path] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> int:
        launch_env = _build_subprocess_env(env=env)

        if platform.system() == "Windows":
            process = subprocess.Popen(
                list(command),
                cwd=str(cwd) if cwd else None,
                env=launch_env,
                creationflags=_CREATE_NEW_CONSOLE,
            )
        else:
            process = subprocess.Popen(
                list(command),
                cwd=str(cwd) if cwd else None,
                env=launch_env,
                start_new_session=True,
            )

        log_info(
            f"Launched windowed process (pid={process.pid}): {' '.join(command)}",
            "uv_bridge",
        )
        return process.pid

    def get_site_packages(self, app_dir: Path) -> str | None:
        """Return the absolute path to the app venv's site-packages directory."""
        venv_path = app_dir / VENV_DIR
        if not venv_path.exists():
            return None
        return str(self._site_packages_path(venv_path))

    def _log_setup_output(
        self, operation: str, app_dir: Path, stdout: str, stderr: str
    ) -> None:
        """Log captured output from uv venv/pip commands."""
        if stdout and stdout.strip():
            lines = stdout.strip().split("\n")
            for line in lines[:5]:
                log_info(f"[{operation}] {line}", "uv_bridge")
            if len(lines) > 5:
                log_info(
                    f"[{operation}] ... ({len(lines) - 5} more lines)", "uv_bridge"
                )

        if stderr and stderr.strip():
            lines = stderr.strip().split("\n")
            for line in lines[:5]:
                log_info(f"[{operation} stderr] {line}", "uv_bridge")
            if len(lines) > 5:
                log_info(
                    f"[{operation} stderr] ... ({len(lines) - 5} more lines)",
                    "uv_bridge",
                )

    def _format_setup_error(
        self,
        action: str,
        app_dir: Path,
        cmd: list[str],
        stdout: str,
        stderr: str,
    ) -> str:
        """Build a user-facing error message for uv setup failures."""
        lines = [
            f"Failed to {action} for app at {app_dir.name}",
            f"Command: {' '.join(cmd)}",
        ]
        if stdout and stdout.strip():
            lines.append(f"Output: {stdout.strip()}")
        if stderr and stderr.strip():
            lines.append(f"Error: {stderr.strip()}")
        return "\n".join(lines)

    @staticmethod
    def _site_packages_path(venv_path: Path) -> Path:
        if platform.system() == "Windows":
            return venv_path / "Lib" / "site-packages"
        py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
        return venv_path / "lib" / py_ver / "site-packages"

    @staticmethod
    def _python_exe(venv_path: Path) -> Path:
        if platform.system() == "Windows":
            return venv_path / "Scripts" / "python.exe"
        return venv_path / "bin" / "python"


class SysPathContext:
    """Context manager for temporarily prepending directories to sys.path."""

    def __init__(self, *paths: str | Path):
        """Prepare to inject *paths* into sys.path.

        The paths will be inserted near the front of sys.path, after any project
        root, but before stdlib and site-packages.
        """
        self._paths_to_inject = [str(p) for p in paths if p and Path(p).is_dir()]
        self._original_path = None
        self._insert_index = None

    def __enter__(self):
        """Inject paths into sys.path."""
        if not self._paths_to_inject:
            return self
        self._original_path = sys.path.copy()
        self._insert_index = self._find_insert_index()
        sys.path[self._insert_index : self._insert_index] = self._paths_to_inject
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore original sys.path."""
        if self._original_path is not None:
            sys.path[:] = self._original_path

    @staticmethod
    def _find_insert_index() -> int:
        """Return the index where venv packages should be inserted.

        Tries to inject after the project directory but before stdlib/site-packages.
        """
        for i, p in enumerate(sys.path):
            lower = p.lower()
            if "site-packages" in lower or "lib" in lower:
                return i
        return 0
