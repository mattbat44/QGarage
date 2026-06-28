"""Background worker that installs uv or pixi using the system's preferred method.

Install commands used:
  uv
    Linux / macOS : curl -LsSf https://astral.sh/uv/install.sh | sh
    Windows       : powershell -Command "irm https://astral.sh/uv/install.ps1 | iex"

  pixi
    Linux / macOS : curl -fsSL https://pixi.sh/install.sh | bash
    Windows       : powershell -Command "iwr -useb https://pixi.sh/install.ps1 | iex"
"""

from __future__ import annotations

import logging
import platform
import subprocess

from qgis.PyQt.QtCore import QThread, pyqtSignal

logger = logging.getLogger("qgarage.install_tool_worker")


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

    # ------------------------------------------------------------------
    # Install command table: (tool, system) -> argv list
    # ``shell=True`` is NOT used; each entry is a real argv list so we
    # can capture stdout/stderr cleanly.
    # ------------------------------------------------------------------
    _COMMANDS: dict[tuple[str, str], list[str]] = {
        ("uv", "Linux"): [
            "sh",
            "-c",
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
        ],
        ("uv", "Darwin"): [
            "sh",
            "-c",
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
        ],
        ("uv", "Windows"): [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "irm https://astral.sh/uv/install.ps1 | iex",
        ],
        ("pixi", "Linux"): [
            "sh",
            "-c",
            "curl -fsSL https://pixi.sh/install.sh | bash",
        ],
        ("pixi", "Darwin"): [
            "sh",
            "-c",
            "curl -fsSL https://pixi.sh/install.sh | bash",
        ],
        ("pixi", "Windows"): [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "iwr -useb https://pixi.sh/install.ps1 | iex",
        ],
    }

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

        cmd = self._COMMANDS.get((tool, system))
        if cmd is None:
            msg = f"No installer available for {tool!r} on {system!r}."
            logger.error(msg)
            self.install_finished.emit(tool, False, msg)
            return

        self.log_message.emit(f"Installing {tool} for {system}…")
        logger.info("Running installer: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except FileNotFoundError as exc:
            msg = (
                f"Could not find installer program: {exc}. "
                "Please install curl (Linux/macOS) or PowerShell (Windows)."
            )
            logger.error(msg)
            self.install_finished.emit(tool, False, msg)
            return
        except subprocess.TimeoutExpired:
            msg = f"Install of {tool} timed out after 180 s."
            logger.error(msg)
            self.install_finished.emit(tool, False, msg)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error during %s install", tool)
            self.install_finished.emit(tool, False, str(exc))
            return

        if result.stdout:
            for line in result.stdout.splitlines():
                self.log_message.emit(line)

        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else "(no stderr)"
            msg = f"{tool} installer exited with code {result.returncode}.\n{stderr}"
            logger.error(msg)
            self.install_finished.emit(tool, False, msg)
            return

        self.log_message.emit(f"{tool} installed successfully.")
        logger.info("%s installed successfully.", tool)
        self.install_finished.emit(tool, True, "")
