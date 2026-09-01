from __future__ import annotations

"""Pixi environment bridge for QGarage apps.

Manages per-app pixi environments that give access to the full conda-forge
ecosystem (compiled C/C++ packages like GDAL, scipy, etc.).
"""

import os
import platform
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Optional

from .constants import PIXI_ENV_DIR, PIXI_TOML_FILENAME
from .logger import log_error, log_info

_CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0
_CREATE_NEW_CONSOLE = 0x00000010 if platform.system() == "Windows" else 0

# Common pixi install dirs that may not appear in QGIS's stripped PATH
_PIXI_CANDIDATE_DIRS_WIN = [
    Path.home() / ".pixi" / "bin",
    Path(os.environ.get("LOCALAPPDATA", "")) / "pixi" / "bin",
    Path.home() / ".local" / "bin",
]

_PIXI_CANDIDATE_DIRS_UNIX = [
    Path.home() / ".pixi" / "bin",
    Path.home() / ".local" / "bin",
    Path("/usr/local/bin"),
]

_WINDOWS_PATH_KEEP_PREFIXES = (
    r"c:\windows",
    r"c:\program files\windowspowershell",
    r"c:\program files\dotnet",
)

_WINDOWS_PATH_DROP_MARKERS = (
    "\\qgis",
    "\\osgeo4w",
    "\\grass",
    "\\qt5",
    "\\qt6",
    "\\python312",
    "\\python311",
    "\\python310",
    "\\python39",
    "\\python38",
)


def _wrap_windowed_command(command: list[str], keep_open_on_failure: bool) -> list[str]:
    """Wrap a Windows console command so startup failures remain visible."""
    if platform.system() != "Windows" or not keep_open_on_failure:
        return command

    quoted = subprocess.list2cmdline(command)
    return ["cmd.exe", "/c", f"{quoted} || pause"]


def _build_pixi_env(*, env: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """Build a subprocess environment for pixi commands launched from QGIS.

    QGIS/OSGeo shells often inject Python-specific environment variables that
    interfere with pixi's own interpreter and solver subprocesses. Strip the
    problematic variables while preserving the rest of the user environment.
    """
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
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
        "CONDA_PROMPT_MODIFIER",
        "CONDA_EXE",
        "CONDA_PYTHON_EXE",
        "CONDA_SHLVL",
    ):
        launch_env.pop(var, None)

    for key in list(launch_env):
        if key.startswith(("GDAL_", "PROJ_", "CPL_", "GEOTIFF_", "QGIS_", "OGR_")):
            launch_env.pop(key, None)

    for var in (
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "VSI_CACHE",
        "VSI_CACHE_SIZE",
    ):
        launch_env.pop(var, None)

    if platform.system() == "Windows":
        launch_env["PATH"] = _sanitize_windows_path_for_pixi(launch_env)

    return launch_env


def _sanitize_windows_path_for_pixi(env: Mapping[str, str]) -> str:
    """Trim PATH entries that are likely to contaminate pixi-native DLL loading."""
    path_value = env.get("PATH", "")
    if not path_value:
        return path_value

    pixi_exe = _resolve_pixi_executable("pixi")
    preferred_entries = []
    pixi_bin = str(Path(pixi_exe).parent)
    if pixi_bin:
        preferred_entries.append(pixi_bin)

    keep_entries = []
    seen = set()

    def _add(entry: str) -> None:
        normalized = entry.strip().strip('"')
        if not normalized:
            return
        key = normalized.lower()
        if key in seen:
            return
        seen.add(key)
        keep_entries.append(normalized)

    for entry in preferred_entries:
        _add(entry)

    for raw_entry in path_value.split(os.pathsep):
        entry = raw_entry.strip().strip('"')
        if not entry:
            continue

        lower_entry = entry.lower()
        if any(marker in lower_entry for marker in _WINDOWS_PATH_DROP_MARKERS):
            continue

        if lower_entry.startswith(_WINDOWS_PATH_KEEP_PREFIXES) or lower_entry == ".":
            _add(entry)

    return os.pathsep.join(keep_entries)


def _resolve_pixi_executable(requested: str) -> str:
    """Return a resolved path to the pixi executable.

    QGIS launches subprocesses with a stripped PATH, so ``pixi`` may not
    resolve even when it is installed.
    """
    resolved_on_path = shutil.which(requested)
    if resolved_on_path:
        return resolved_on_path

    is_windows = platform.system() == "Windows"
    candidate_dirs = (
        _PIXI_CANDIDATE_DIRS_WIN if is_windows else _PIXI_CANDIDATE_DIRS_UNIX
    )

    extra_dirs = [str(d) for d in candidate_dirs if d.exists()]
    augmented_path = os.pathsep.join([*extra_dirs, os.environ.get("PATH", "")])
    found = shutil.which(requested, path=augmented_path)
    if found:
        log_info(f"Resolved pixi via augmented PATH: {found}", "pixi_bridge")
        return found

    exe_name = "pixi.exe" if is_windows else "pixi"
    for candidate_dir in candidate_dirs:
        candidate = candidate_dir / exe_name
        if candidate.is_file():
            log_info(f"Found pixi at known location: {candidate}", "pixi_bridge")
            return str(candidate)

    return requested  # fall through; _verify_pixi will raise a clear error


class PixiBridge:
    """Manages pixi environments for QGarage apps."""

    def __init__(self, pixi_executable: str = "pixi"):
        self.pixi_exe = _resolve_pixi_executable(pixi_executable)
        self._verify_pixi()

    def _verify_pixi(self) -> None:
        try:
            result = subprocess.run(
                [self.pixi_exe, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
                env=_build_pixi_env(),
                creationflags=_CREATE_NO_WINDOW,
            )
            log_info(f"pixi version: {result.stdout.strip()}", "pixi_bridge")
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"pixi executable not found (tried: {self.pixi_exe}). "
                "Install from https://pixi.sh"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"pixi verification timed out after {exc.timeout} seconds: {self.pixi_exe}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            output = "\n".join(
                part.strip() for part in (exc.stdout, exc.stderr) if part and part.strip()
            )
            raise RuntimeError(
                f"pixi verification failed for {self.pixi_exe}.\n"
                f"Output:\n{output or '<no output>'}"
            ) from exc

    def ensure_env(self, app_dir: Path) -> None:
        """Create or update the pixi environment for an app.

        Runs ``pixi install`` which is idempotent — fast when already
        up-to-date.
        """
        manifest = app_dir / PIXI_TOML_FILENAME
        if not manifest.exists():
            log_info(
                f"No {PIXI_TOML_FILENAME} in {app_dir}, skipping pixi install",
                "pixi_bridge",
            )
            return

        cmd = [
            self.pixi_exe,
            "install",
            "--manifest-path",
            str(manifest),
        ]
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                cwd=str(app_dir),
                env=_build_pixi_env(),
                creationflags=_CREATE_NO_WINDOW,
            )
        except subprocess.CalledProcessError as e:
            stdout_text = (e.stdout or "").strip()
            stderr_text = (e.stderr or "").strip()
            combined = "\n".join(part for part in (stdout_text, stderr_text) if part)
            log_error(
                "Pixi install failed for "
                f"{app_dir.name}. Command: {' '.join(cmd)}\n"
                f"Working directory: {app_dir}\n"
                f"Output:\n{combined or '<no output>'}",
                "pixi_bridge",
            )
            raise RuntimeError(
                "Failed to install pixi environment "
                f"for {app_dir.name}. See QGIS logs for full command/output.\n"
                f"{combined or '<no output>'}"
            ) from e

        if result.stdout.strip():
            log_info(
                f"pixi install output for {app_dir.name}:\n{result.stdout.strip()}",
                "pixi_bridge",
            )
        if result.stderr.strip():
            log_info(
                f"pixi install stderr for {app_dir.name}:\n{result.stderr.strip()}",
                "pixi_bridge",
            )
        log_info(f"Pixi environment ready for {app_dir.name}", "pixi_bridge")

    def get_site_packages(self, app_dir: Path) -> Optional[str]:
        """Return the site-packages path for an app's pixi env, or None."""
        env_dir = app_dir / PIXI_ENV_DIR / "envs" / "default"
        sp = self._site_packages_path(env_dir)
        if sp and sp.exists():
            return str(sp)
        return None

    def launch_app_isolated(
        self,
        runner_path: Path,
        config_path: Path,
        requirements_path: Optional[Path] = None,
        venv_site_packages: Optional[str] = None,
        show_window: bool = True,
        *,
        manifest_path: Optional[Path] = None,
    ) -> subprocess.Popen:
        """Run an app's execute_logic in a pixi-managed subprocess.

        The pixi environment provides its own Python and all declared
        dependencies (both conda and PyPI).

        Args:
            runner_path:        Path to the generated runner script.
            config_path:        Path to the JSON config file consumed by the runner.
            requirements_path:  Ignored for pixi apps (deps are in pixi.toml).
            venv_site_packages: Optional path to inject via PYTHONPATH.
            show_window:        When True, open a separate console window.
            manifest_path:      Path to pixi.toml. Inferred from config if None.

        Returns:
            The Popen object for the spawned process.
        """
        import subprocess as _sp

        if manifest_path is None:
            # Infer from config_path's sibling or fall back
            import json

            config = json.loads(config_path.read_text(encoding="utf-8"))
            manifest_path = Path(config["app_dir"]) / PIXI_TOML_FILENAME

        app_dir = manifest_path.parent

        cmd = [
            self.pixi_exe,
            "run",
            "--manifest-path",
            str(manifest_path),
            "python",
            str(runner_path),
            str(config_path),
        ]

        launch_env = _build_pixi_env()
        launch_env["QGARAGE_ENV_BACKEND"] = "pixi"

        if platform.system() == "Windows":
            creationflags = _CREATE_NEW_CONSOLE if show_window else _CREATE_NO_WINDOW
            popen_cmd = _wrap_windowed_command(cmd, keep_open_on_failure=show_window)
            process = _sp.Popen(
                popen_cmd,
                env=launch_env,
                cwd=str(app_dir),
                creationflags=creationflags,
            )
        else:
            popen_kwargs: dict = {"env": launch_env, "cwd": str(app_dir)}
            if show_window:
                popen_kwargs["start_new_session"] = True
            process = _sp.Popen(cmd, **popen_kwargs)

        log_info(
            f"Launched pixi app process (pid={process.pid}, show_window={show_window}): "
            f"{' '.join(cmd)}",
            "pixi_bridge",
        )
        return process

    @staticmethod
    def _site_packages_path(env_dir: Path) -> Optional[Path]:
        """Get site-packages path for a pixi environment."""
        if platform.system() == "Windows":
            sp = env_dir / "Lib" / "site-packages"
            return sp if sp.exists() else None
        return next((env_dir / "lib").glob("python*/site-packages"), None)
