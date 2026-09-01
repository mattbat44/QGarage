from __future__ import annotations

"""Background worker that installs uv or pixi using the system's preferred method.

Install commands used:
  uv
    Linux / macOS : curl -LsSf https://astral.sh/uv/install.sh | sh
    Windows       : powershell -Command "irm https://astral.sh/uv/install.ps1 | iex"

  pixi
    Linux / macOS : curl -fsSL https://pixi.sh/install.sh | bash
    Windows       : powershell -Command "iwr -useb https://pixi.sh/install.ps1 | iex"
"""



import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path

from qgis.PyQt.QtCore import QThread, pyqtSignal

from ..core.package_manager_install import build_install_command

logger = logging.getLogger("qgarage.install_tool_worker")


def _resolve_windows_powershell() -> tuple[str, list[str]]:
    """Find PowerShell even when QGIS has launched with a reduced PATH."""
    candidates = []
    for root in (os.environ.get("SystemRoot"), os.environ.get("WINDIR"), r"C:\Windows"):
        if root:
            candidate = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
            candidate_text = str(candidate)
            if candidate_text not in candidates:
                candidates.append(candidate_text)

    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate, candidates

    path_executable = shutil.which("powershell.exe") or shutil.which("powershell")
    if path_executable:
        return path_executable, candidates
    return "powershell.exe", candidates


class InstallToolWorker(QThread):
    """QThread that runs a tool installer in the background.

    Signals
    -------
    log_message(str)
        Incremental progress text.
    install_finished(str, bool, str)
        ``(tool_name, success, error_text)`` — emitted when done.
    """

    log_message: pyqtSignal = pyqtSignal(str)
    install_finished: pyqtSignal = pyqtSignal(str, bool, str)

    def __init__(self, tool: str, parent=None) -> None:
        super().__init__(parent)
        if tool not in ("uv", "pixi"):
            raise ValueError(f"Unsupported tool: {tool!r}. Must be 'uv' or 'pixi'.")
        self._tool = tool

    # ------------------------------------------------------------------
    # QThread.run()
    # ------------------------------------------------------------------

    def run(self) -> None:
        tool = self._tool
        system = platform.system()

        try:
            cmd = build_install_command([tool], system_name=system)
        except ValueError as exc:
            msg = str(exc)
            logger.error(msg)
            self.install_finished.emit(tool, False, msg)
            return

        attempted_powershell_paths = []
        if system == "Windows":
            powershell_exe, attempted_powershell_paths = _resolve_windows_powershell()
            cmd[0] = powershell_exe
            self.log_message.emit(f"Using PowerShell: {powershell_exe}")

        self.log_message.emit(f"Installing {tool} for {system}…")
        command_text = subprocess.list2cmdline(cmd)
        self.log_message.emit(f"Running: {command_text}")
        logger.info("Running installer: %s", command_text)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except FileNotFoundError as exc:
            attempted = "\n".join(attempted_powershell_paths) or "(none)"
            msg = (
                f"Could not launch installer executable '{cmd[0]}': {exc}\n"
                f"Platform: {system}\n"
                f"Command: {command_text}\n"
                f"PowerShell paths checked:\n{attempted}\n"
                "Ensure C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe exists "
                "and that QGIS is not running under an application-control policy."
            )
            logger.error(msg)
            self.install_finished.emit(tool, False, msg)
            return
        except subprocess.TimeoutExpired:
            msg = f"Install of {tool} timed out after 180 s."
            logger.error(msg)
            self.install_finished.emit(tool, False, msg)
            return
        except Exception as exc:
            logger.exception("Unexpected error during %s install", tool)
            self.install_finished.emit(tool, False, str(exc))
            return

        if result.stdout:
            for line in result.stdout.splitlines():
                self.log_message.emit(line)

        if result.stderr:
            for line in result.stderr.splitlines():
                self.log_message.emit(f"stderr: {line}")

        if result.returncode != 0:
            stdout = result.stdout.strip() if result.stdout else "(no stdout)"
            stderr = result.stderr.strip() if result.stderr else "(no stderr)"
            msg = (
                f"{tool} installer exited with code {result.returncode}.\n"
                f"Command: {command_text}\n"
                f"Standard output:\n{stdout}\n"
                f"Standard error:\n{stderr}"
            )
            logger.error(msg)
            self.install_finished.emit(tool, False, msg)
            return

        self.log_message.emit(f"{tool} installed successfully.")
        logger.info("%s installed successfully.", tool)
        self.install_finished.emit(tool, True, "")
