import json
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from qgis.PyQt.QtCore import QThread, pyqtSignal

from ..core.uv_bridge import UvBridge

logger = logging.getLogger("qhub.download_worker")


class DownloadAndInstallWorker(QThread):
    """Worker thread: download ZIP -> extract -> uv venv -> uv pip install.

    Signals:
        progress(int, str): (percentage, status_message)
        finished(bool, str): (success, app_id_or_error_message)
    """

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, url: str, apps_dir: Path, uv_bridge: UvBridge, parent=None):
        super().__init__(parent)
        self.url = url
        self.apps_dir = apps_dir
        self.uv_bridge = uv_bridge
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        temp_dir = None
        try:
            # Phase 1: Download (0-40%)
            self.progress.emit(5, f"Downloading from {self.url}...")
            temp_dir = Path(tempfile.mkdtemp(prefix="qhub_install_"))
            zip_path = temp_dir / "app.zip"

            req = Request(self.url, headers={"User-Agent": "QHub/0.1"})
            response = urlopen(req, timeout=60)
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0

            with open(zip_path, "wb") as f:
                while True:
                    if self._cancelled:
                        self.finished.emit(False, "Installation cancelled")
                        return
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = int((downloaded / total) * 35) + 5
                        self.progress.emit(
                            pct, f"Downloaded {downloaded}/{total} bytes"
                        )

            self.progress.emit(40, "Download complete. Extracting...")

            # Phase 2: Extract (40-55%)
            if not zipfile.is_zipfile(zip_path):
                self.finished.emit(False, "Downloaded file is not a valid ZIP archive")
                return

            extract_dir = temp_dir / "extracted"
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            self.progress.emit(55, "Locating app_meta.json...")

            # Phase 3: Find and validate app_meta.json (55-60%)
            app_meta_files = list(extract_dir.rglob("app_meta.json"))
            if not app_meta_files:
                self.finished.emit(False, "No app_meta.json found in archive")
                return

            app_meta_path = app_meta_files[0]
            app_source_dir = app_meta_path.parent

            with open(app_meta_path, encoding="utf-8") as f:
                app_meta = json.load(f)

            app_id = app_meta.get("id")
            if not app_id:
                self.finished.emit(False, "app_meta.json missing 'id' field")
                return

            self.progress.emit(60, f"Installing app '{app_id}'...")

            # Phase 4: Copy to apps directory (60-70%)
            dest_dir = self.apps_dir / app_id
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            shutil.copytree(app_source_dir, dest_dir)

            self.progress.emit(70, "Creating virtual environment...")

            # Phase 5: uv venv (70-85%)
            self.uv_bridge.create_venv(dest_dir)

            self.progress.emit(85, "Installing dependencies...")

            # Phase 6: pip install (85-98%)
            self.uv_bridge.install_requirements(dest_dir)

            self.progress.emit(100, "Installation complete!")
            self.finished.emit(True, app_id)

        except URLError as e:
            self.finished.emit(False, f"Download failed: {e}")
        except Exception as e:
            self.finished.emit(False, f"Installation error: {type(e).__name__}: {e}")
        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)


class LocalInstallWorker(QThread):
    """Worker thread: copy local folder -> uv venv -> uv pip install.

    Signals:
        progress(int, str): (percentage, status_message)
        finished(bool, str): (success, app_id_or_error_message)
    """

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(
        self, source_dir: Path, apps_dir: Path, uv_bridge: UvBridge, parent=None
    ):
        super().__init__(parent)
        self.source_dir = source_dir
        self.apps_dir = apps_dir
        self.uv_bridge = uv_bridge

    def run(self):
        try:
            # Validate
            meta_file = self.source_dir / "app_meta.json"
            if not meta_file.exists():
                self.finished.emit(False, "No app_meta.json found in selected folder")
                return

            self.progress.emit(10, "Reading app metadata...")

            with open(meta_file, encoding="utf-8") as f:
                app_meta = json.load(f)

            app_id = app_meta.get("id")
            if not app_id:
                self.finished.emit(False, "app_meta.json missing 'id' field")
                return

            self.progress.emit(30, f"Copying app '{app_id}'...")

            # Copy to apps directory
            dest_dir = self.apps_dir / app_id
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            shutil.copytree(self.source_dir, dest_dir)

            self.progress.emit(50, "Creating virtual environment...")
            self.uv_bridge.create_venv(dest_dir)

            self.progress.emit(75, "Installing dependencies...")
            self.uv_bridge.install_requirements(dest_dir)

            self.progress.emit(100, "Installation complete!")
            self.finished.emit(True, app_id)

        except Exception as e:
            self.finished.emit(False, f"Installation error: {type(e).__name__}: {e}")
