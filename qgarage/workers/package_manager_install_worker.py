from __future__ import annotations

import subprocess
from collections.abc import Iterable

from qgis.PyQt.QtCore import QThread, pyqtSignal

from ..core.logger import log_error, log_info
from ..core.package_manager_install import build_install_command


class PackageManagerInstallWorker(QThread):
    """Install one or more package managers without blocking the UI thread."""

    install_finished = pyqtSignal(bool, str)

    def __init__(self, package_managers: Iterable[str], parent=None):
        super().__init__(parent)
        self.package_managers = tuple(package_managers)

    def run(self) -> None:
        try:
            command = build_install_command(self.package_managers)
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            output = (exc.stderr or exc.stdout or "").strip()
            log_error(
                f"Package manager install failed for {', '.join(self.package_managers)}: {output}",
                "package_manager_install_worker",
            )
            self.install_finished.emit(False, output or "Installer exited with an error")
            return
        except Exception as exc:
            log_error(
                f"Package manager install failed for {', '.join(self.package_managers)}: {exc}",
                "package_manager_install_worker",
            )
            self.install_finished.emit(False, str(exc))
            return

        output = (result.stdout or result.stderr or "").strip()
        log_info(
            f"Installed package managers: {', '.join(self.package_managers)}",
            "package_manager_install_worker",
        )
        self.install_finished.emit(True, output)