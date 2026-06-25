"""Landing screen shown when uv and/or pixi are unavailable."""

import logging
import os
import platform
import subprocess
from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import Qt, QThread, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger("qgarage.env_setup")


class InstallWorker(QThread):
    """Background worker for installing uv/pixi."""

    finished = pyqtSignal(bool, str)  # (success, message)

    def __init__(self, tool_name: str, script_path: str, parent=None):
        super().__init__(parent)
        self.tool_name = tool_name
        self.script_path = script_path

    def run(self):
        """Execute the install script."""
        try:
            logger.info(
                f"Starting {self.tool_name} installation from {self.script_path}"
            )

            if not os.path.exists(self.script_path):
                msg = f"Install script not found: {self.script_path}"
                logger.error(msg)
                self.finished.emit(False, msg)
                return

            if platform.system() == "Windows":
                # PowerShell script
                result = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        self.script_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                )
            else:
                # Bash script
                result = subprocess.run(
                    ["bash", self.script_path],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env={
                        **os.environ,
                        "PATH": f"{Path.home()}/.local/bin:{os.environ.get('PATH', '')}",
                    },
                )

            if result.returncode == 0:
                msg = f"{self.tool_name} installed successfully!"
                logger.info(msg)
                self.finished.emit(True, msg)
            else:
                msg = f"{self.tool_name} installation failed:\n{result.stderr or result.stdout}"
                logger.error(msg)
                self.finished.emit(False, msg)

        except subprocess.TimeoutExpired:
            msg = f"{self.tool_name} installation timed out (5 minutes)"
            logger.error(msg)
            self.finished.emit(False, msg)
        except Exception as e:
            msg = f"Error installing {self.tool_name}: {e}"
            logger.error(msg)
            self.finished.emit(False, msg)


class EnvSetupWidget(QWidget):
    """Landing screen for setting up missing environment tools (uv/pixi)."""

    tools_ready = pyqtSignal()  # Emitted when all tools are installed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("qgarageEnvSetup")
        self._uv_available = self._check_uv_available()
        self._pixi_available = self._check_pixi_available()
        self._install_worker: Optional[InstallWorker] = None
        self._build_ui()

    def _check_uv_available(self) -> bool:
        """Check if uv is available in PATH."""
        try:
            subprocess.run(
                ["uv", "--version"],
                capture_output=True,
                timeout=5,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _check_pixi_available(self) -> bool:
        """Check if pixi is available in PATH."""
        try:
            subprocess.run(
                ["pixi", "--version"],
                capture_output=True,
                timeout=5,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def is_ready(self) -> bool:
        """Return True if both tools are available."""
        return self._uv_available and self._pixi_available

    def _build_ui(self):
        """Build the landing screen UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Title
        title = QLabel("QGarage Environment Setup")
        title.setObjectName("qgarageEnvSetupTitle")
        title.setStyleSheet(
            "QLabel#qgarageEnvSetupTitle { font-size: 18px; font-weight: bold; }"
        )
        layout.addWidget(title)

        # Description
        description = QLabel(
            "QGarage requires environment managers to run apps. "
            "The following tools are needed:"
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        # Create scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        # UV section
        uv_section = self._build_tool_section(
            "uv",
            self._uv_available,
            "Pure-Python package manager",
            "uv.ps1" if platform.system() == "Windows" else "uv.sh",
        )
        content_layout.addWidget(uv_section)

        # Pixi section
        pixi_section = self._build_tool_section(
            "pixi",
            self._pixi_available,
            "Conda package manager for compiled packages",
            "pixi.ps1" if platform.system() == "Windows" else "pixi.sh",
        )
        content_layout.addWidget(pixi_section)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # Spacer before buttons
        layout.addSpacing(10)

        # Refresh button to check if tools are now available
        refresh_btn = QPushButton("Refresh / Retry")
        refresh_btn.setObjectName("qgarageRefreshButton")
        refresh_btn.clicked.connect(self._on_refresh_clicked)
        layout.addWidget(refresh_btn)

    def _build_tool_section(
        self, tool_name: str, is_available: bool, description: str, script_name: str
    ) -> QWidget:
        """Build a section for a single tool."""
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        section.setStyleSheet(
            """
            QWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: #f9f9f9;
            }
            QWidget[unavailable="true"] {
                background-color: #ffe6e6;
            }
            """
        )
        if not is_available:
            section.setProperty("unavailable", True)

        # Tool name and status
        name_label = QLabel(f"{tool_name.upper()}")
        name_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(name_label)

        # Description
        desc_label = QLabel(description)
        desc_label.setStyleSheet("color: #666; font-size: 10px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Status
        if is_available:
            status_label = QLabel("✓ Available")
            status_label.setStyleSheet(
                "color: #008000; font-weight: bold; font-size: 11px;"
            )
        else:
            status_label = QLabel("✗ Not installed")
            status_label.setStyleSheet(
                "color: #d32f2f; font-weight: bold; font-size: 11px;"
            )

        layout.addWidget(status_label)

        # Install button (only if not available)
        if not is_available:
            install_btn = QPushButton(f"Install {tool_name}")
            install_btn.setObjectName(f"install{tool_name.capitalize()}Button")
            install_btn.clicked.connect(
                lambda: self._on_install_clicked(tool_name, script_name)
            )
            layout.addWidget(install_btn)

        return section

    def _on_install_clicked(self, tool_name: str, script_name: str):
        """Handle install button click."""
        # Find the script - try plugin-relative path first, then repo root
        plugin_dir = Path(__file__).parent.parent

        # Try: qgarage/../scripts/ (if scripts are in repo root)
        script_path = plugin_dir.parent / "scripts" / f"install_{script_name}"

        # If not found, try looking inside plugin: qgarage/scripts/
        if not script_path.exists():
            script_path = plugin_dir / "scripts" / f"install_{script_name}"

        if not script_path.exists():
            msg = f"Install script not found. Checked: {plugin_dir.parent / 'scripts'} and {plugin_dir / 'scripts'}"
            logger.error(msg)
            return

        logger.info(f"Starting installation of {tool_name} from {script_path}")

        # Disable all buttons during installation
        self.setEnabled(False)

        # Create and start worker
        self._install_worker = InstallWorker(tool_name, str(script_path), parent=self)
        self._install_worker.finished.connect(self._on_install_finished)
        self._install_worker.start()

    def _on_install_finished(self, success: bool, message: str):
        """Handle installation completion."""
        logger.info(f"Installation finished: {success} - {message}")

        if success:
            # Re-check tool availability after short delay to allow PATH updates
            # This gives the system time to register the new executable
            QTimer.singleShot(1000, self._check_and_refresh)
        else:
            # Re-enable the widget but keep the UI as-is to show error
            self.setEnabled(True)

    def _check_and_refresh(self):
        """Check tool availability and refresh UI."""
        self._uv_available = self._check_uv_available()
        self._pixi_available = self._check_pixi_available()

        # Rebuild UI to reflect changes
        self._rebuild_ui()

        # If both are now available, emit ready signal
        if self.is_ready():
            self.tools_ready.emit()
        else:
            self.setEnabled(True)

        self._install_worker = None

    def _on_refresh_clicked(self):
        """Handle refresh button click."""
        logger.info("Checking for available tools...")
        self._uv_available = self._check_uv_available()
        self._pixi_available = self._check_pixi_available()

        if self.is_ready():
            self.tools_ready.emit()
        else:
            self._rebuild_ui()

    def _rebuild_ui(self):
        """Rebuild the UI to reflect current tool availability."""
        # Clear and rebuild
        for i in reversed(range(self.layout().count())):
            widget = self.layout().itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()

        self._build_ui()
