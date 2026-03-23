import logging
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("qhub.uv_bridge")

_CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0


class UvBridge:
    """Manages uv virtual environments for QHub apps."""

    def __init__(self, uv_executable: str = "uv"):
        self.uv_exe = uv_executable
        self._verify_uv()

    def _verify_uv(self) -> None:
        try:
            result = subprocess.run(
                [self.uv_exe, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=_CREATE_NO_WINDOW,
            )
            logger.info(f"uv version: {result.stdout.strip()}")
        except FileNotFoundError:
            raise RuntimeError(
                "uv executable not found. Install from https://docs.astral.sh/uv/"
            )

    def create_venv(self, app_dir: Path) -> Path:
        """Create an isolated venv inside an app directory.

        Returns the path to site-packages.
        """
        venv_path = app_dir / ".venv"
        if venv_path.exists():
            logger.info(f"Venv already exists at {venv_path}")
            return self._site_packages_path(venv_path)

        subprocess.run(
            [self.uv_exe, "venv", str(venv_path)],
            check=True,
            capture_output=True,
            text=True,
            creationflags=_CREATE_NO_WINDOW,
        )
        logger.info(f"Created venv at {venv_path}")
        return self._site_packages_path(venv_path)

    def install_requirements(self, app_dir: Path) -> None:
        """Install requirements.txt into the app's venv."""
        req_file = app_dir / "requirements.txt"
        venv_path = app_dir / ".venv"
        if not req_file.exists():
            logger.info(f"No requirements.txt in {app_dir}, skipping install")
            return
        if req_file.read_text().strip() == "":
            logger.info(f"Empty requirements.txt in {app_dir}, skipping install")
            return

        subprocess.run(
            [
                self.uv_exe,
                "pip",
                "install",
                "-r",
                str(req_file),
                "--python",
                str(self._python_exe(venv_path)),
            ],
            check=True,
            capture_output=True,
            text=True,
            creationflags=_CREATE_NO_WINDOW,
        )
        logger.info(f"Installed requirements for {app_dir.name}")

    def get_site_packages(self, app_dir: Path) -> Optional[str]:
        """Return the site-packages path for an app's venv, or None."""
        venv_path = app_dir / ".venv"
        sp = self._site_packages_path(venv_path)
        return str(sp) if sp.exists() else None

    @staticmethod
    def _site_packages_path(venv_path: Path) -> Path:
        if platform.system() == "Windows":
            return venv_path / "Lib" / "site-packages"
        return next((venv_path / "lib").glob("python*/site-packages"))

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
            logger.debug(f"Injected {self.sp_path} at sys.path[{insert_idx}]")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.sp_path and self.sp_path in sys.path:
            sys.path.remove(self.sp_path)
            logger.debug(f"Removed {self.sp_path} from sys.path")
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
