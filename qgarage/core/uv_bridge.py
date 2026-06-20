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
    """Wrap a Windows console command so startup failures remain visible."""
    if platform.system() != "Windows" or not keep_open_on_failure:
        return list(command)

    quoted = subprocess.list2cmdline(list(command))
    return ["cmd.exe", "/d", "/s", "/c", f'"{quoted} || pause"']


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


def _resolve_uv_executable(requested: str) -> str:
    """Return a resolved path to the uv executable.

    QGIS launches subprocesses with a stripped PATH, so 'uv' may not resolve
    even when it is installed.  We try in order:
      1. requested value as-is (works for absolute paths or a full PATH).
      2. shutil.which with an augmented PATH including common install dirs.
      3. Direct existence checks of known candidate paths.
    """
    if shutil.which(requested):
        return requested

    if platform.system() == "Windows":
        extra_dirs = [str(d) for d in _UV_CANDIDATE_DIRS_WIN if d.exists()]
        augmented_path = os.pathsep.join([*extra_dirs, os.environ.get("PATH", "")])
        found = shutil.which(requested, path=augmented_path)
        if found:
            log_info(f"Resolved uv via augmented PATH: {found}", "uv_bridge")
            return found

        exe_name = Path(requested).name if os.sep in requested else "uv.exe"
        for candidate_dir in _UV_CANDIDATE_DIRS_WIN:
            candidate = candidate_dir / exe_name
            if candidate.is_file():
                log_info(f"Found uv at known location: {candidate}", "uv_bridge")
                return str(candidate)

    return requested  # fall through; _verify_uv will raise a clear error


def _resolve_headless_python_executable() -> str:
    """Return a non-GUI Python executable suitable for subprocess runners.

    In QGIS environments, ``sys.executable`` may be ``qgis-bin.exe`` or
    another GUI launcher, which opens a second QGIS window when used with
    ``uv run --python``. Prefer ``python.exe`` candidates nearby.
    """

    current = Path(sys.executable)
    current_name = current.name.lower()

    # Fast path: already a standard Python executable
    if "python" in current_name and "qgis" not in current_name:
        return str(current)

    candidates: list[Path] = []

    # Common OSGeo4W/QGIS layouts (Windows)
    if platform.system() == "Windows":
        # <QGIS>/bin/qgis-bin.exe -> <QGIS>/apps/Python*/python.exe
        root = (
            current.parent.parent
            if current.parent.name.lower() == "bin"
            else current.parent
        )
        apps_dir = root / "apps"
        if apps_dir.exists():
            for py_dir in sorted(apps_dir.glob("Python*"), reverse=True):
                candidates.append(py_dir / "python.exe")

        # Sibling python.exe near executable
        candidates.append(current.parent / "python.exe")

    # PATH fallback
    path_python = shutil.which("python")
    if path_python:
        candidates.append(Path(path_python))

    for candidate in candidates:
        if candidate.is_file():
            log_info(f"Resolved headless python: {candidate}", "uv_bridge")
            return str(candidate)

    # Final fallback: current executable
    log_info(
        f"Falling back to current executable for uv run: {sys.executable}",
        "uv_bridge",
    )
    return sys.executable


class UvBridge:
    """Manages uv virtual environments for QGarage apps."""

    def __init__(self, uv_executable: str = "uv"):
        self.uv_exe = _resolve_uv_executable(uv_executable)
        self._verify_uv()

    def _verify_uv(self) -> None:
        try:
            result = subprocess.run(
                [self.uv_exe, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                env=_build_subprocess_env(),
                creationflags=_CREATE_NO_WINDOW,
            )
            log_info(f"uv version: {result.stdout.strip()}", "uv_bridge")
        except FileNotFoundError:
            raise RuntimeError(
                f"uv executable not found (tried: {self.uv_exe}). "
                "Install from https://docs.astral.sh/uv/"
            )

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
        """Install requirements.txt into the app's venv."""
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
        tool: str,
        args: Optional[Sequence[str]] = None,
        cwd: Optional[Path] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> int:
        """Launch ``uvx <tool> ...`` in a separate console window.

        This uses uv's ephemeral execution model, so no long-lived virtual
        environment is activated in QGIS. The process runs independently and
        returns immediately with the child PID.
        """
        if not tool:
            raise ValueError("tool must be a non-empty string")

        command = [self.uv_exe, "x", tool]
        if args:
            command.extend(str(a) for a in args)

        return self._launch_windowed(command, cwd=cwd, env=env)

    def launch_uv_run_windowed(
        self,
        command: Sequence[str],
        with_packages: Optional[Sequence[str]] = None,
        cwd: Optional[Path] = None,
        env: Optional[Mapping[str, str]] = None,
        isolated: bool = True,
    ) -> int:
        """Launch ``uv run`` in a separate console window.

        By default ``isolated=True`` to avoid activating the project venv and
        keep execution scoped to this single run.
        """
        if not command:
            raise ValueError("command must not be empty")

        uv_cmd: list[str] = [self.uv_exe, "run"]
        if isolated:
            uv_cmd.append("--isolated")
        if with_packages:
            for package in with_packages:
                uv_cmd.extend(["--with", str(package)])
        uv_cmd.extend(str(part) for part in command)

        return self._launch_windowed(uv_cmd, cwd=cwd, env=env)

    def launch_app_isolated(
        self,
        runner_path: Path,
        config_path: Path,
        requirements_path: Optional[Path] = None,
        venv_site_packages: Optional[str] = None,
        show_window: bool = True,
    ) -> "subprocess.Popen":
        """Run an app's execute_logic using the app's persistent uv environment.

        Args:
            runner_path:        Path to the generated runner script.
            config_path:        Path to the JSON config file consumed by the runner.
            requirements_path:  Optional path to a requirements.txt for extra packages.
            venv_site_packages: Optional path to inject via PYTHONPATH (app venv).
            show_window:        When True, open a separate console window.

        Returns:
            The Popen object for the spawned process.
        """
        import json
        import subprocess as _sp

        config = json.loads(config_path.read_text(encoding="utf-8"))
        app_dir = Path(config["app_dir"])
        self.ensure_env(app_dir)
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
            "Launched persistent uv app process "
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

    def get_site_packages(self, app_dir: Path) -> Optional[str]:
        """Return the site-packages path for an app's venv, or None."""
        venv_path = app_dir / VENV_DIR
        try:
            sp = self._site_packages_path(venv_path)
            return str(sp) if sp and sp.exists() else None
        except StopIteration:
            log_error(f"Could not find site-packages in {venv_path}", "uv_bridge")
            return None

    def _log_setup_output(
        self,
        action: str,
        app_dir: Path,
        stdout_text: Optional[str],
        stderr_text: Optional[str],
    ) -> None:
        stdout_clean = (stdout_text or "").strip()
        stderr_clean = (stderr_text or "").strip()
        if stdout_clean:
            log_info(
                f"{action} output for {app_dir.name}:\n{stdout_clean}",
                "uv_bridge",
            )
        if stderr_clean:
            log_info(
                f"{action} stderr for {app_dir.name}:\n{stderr_clean}",
                "uv_bridge",
            )

    def _format_setup_error(
        self,
        *,
        action: str,
        app_dir: Path,
        cmd: Sequence[str],
        stdout: Optional[str],
        stderr: Optional[str],
    ) -> str:
        stdout_clean = (stdout or "").strip()
        stderr_clean = (stderr or "").strip()
        combined = "\n".join(part for part in (stdout_clean, stderr_clean) if part)
        log_error(
            f"Failed to {action} for {app_dir.name}. Command: {' '.join(cmd)}\n"
            f"Working directory: {app_dir}\n"
            f"Output:\n{combined or '<no output>'}",
            "uv_bridge",
        )
        return (
            f"Failed to {action} for {app_dir.name}. "
            "See QGIS logs for full command/output.\n"
            f"{combined or '<no output>'}"
        )

    @staticmethod
    def _site_packages_path(venv_path: Path) -> Optional[Path]:
        """Get site-packages path, handling platform differences."""
        if platform.system() == "Windows":
            return venv_path / "Lib" / "site-packages"
        # Use next() with default to handle missing python directory
        return next((venv_path / "lib").glob("python*/site-packages"), None)

    @staticmethod
    def _python_exe(venv_path: Path) -> Path:
        if platform.system() == "Windows":
            return venv_path / "Scripts" / "python.exe"
        return venv_path / "bin" / "python"


class SysPathContext:
    """Context manager for temporarily injecting an app's site-packages into sys.path.

    Inserts after QGIS's own paths so QGIS-provided packages (PyQt, GDAL, etc.)
    always take precedence.
    """

    def __init__(self, site_packages_path: Optional[str]):
        self.sp_path = site_packages_path
        self._inserted_at: Optional[int] = None

    def __enter__(self):
        if self.sp_path and self.sp_path not in sys.path:
            insert_idx = self._find_insert_index()
            sys.path.insert(insert_idx, self.sp_path)
            self._inserted_at = insert_idx
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.sp_path and self.sp_path in sys.path:
            sys.path.remove(self.sp_path)
        return False

    @staticmethod
    def _find_insert_index() -> int:
        """Find index after QGIS/PyQt paths where app packages should go."""
        qgis_markers = ("qgis", "osgeo4w", "pyqt", "sip", "gdal")
        last_qgis_idx = 0
        for i, p in enumerate(sys.path):
            p_lower = p.lower()
            if any(marker in p_lower for marker in qgis_markers):
                last_qgis_idx = i + 1
        return last_qgis_idx
