import json
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPHandler, HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from qgis.PyQt.QtCore import QThread, pyqtSignal

logger = logging.getLogger("qgarage.download_worker")

ALLOWED_DOWNLOAD_SCHEMES = {"http", "https"}


class _SafeHttpRedirectHandler(HTTPRedirectHandler):
    """Restrict redirects to http/https targets only."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirect_url = urljoin(req.full_url, newurl)
        parsed_redirect = urlparse(redirect_url)
        if parsed_redirect.scheme not in ALLOWED_DOWNLOAD_SCHEMES:
            raise URLError(
                f"Redirected to unsupported URL scheme '{parsed_redirect.scheme}'"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_remote_zip(url: str, timeout: int):
    """Open a remote ZIP download using handlers limited to http/https."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_DOWNLOAD_SCHEMES:
        raise URLError(
            f"Invalid URL scheme '{parsed.scheme}': only http and https are allowed"
        )

    opener = build_opener(HTTPHandler, HTTPSHandler, _SafeHttpRedirectHandler)
    req = Request(url, headers={"User-Agent": "QGarage/0.1"})
    return opener.open(req, timeout=timeout)


def _normalize_icon_path(
    app_meta: dict, source_app_dir: Path, dest_app_dir: Path
) -> None:
    """Copy app icon into installed app directory and normalize icon_path.

    If app_meta contains `icon_path`, this function resolves the source icon
    path (relative to source_app_dir or absolute), copies it into dest_app_dir,
    and rewrites app_meta['icon_path'] as a relative file name.
    """
    icon_value = (app_meta.get("icon_path") or "").strip()
    if not icon_value:
        return

    source_icon = Path(icon_value)
    if not source_icon.is_absolute():
        source_icon = source_app_dir / source_icon

    if not source_icon.exists() or not source_icon.is_file():
        logger.warning(
            "icon_path not found for app '%s': %s", app_meta.get("id", "?"), source_icon
        )
        return

    icon_dest_name = source_icon.name
    dest_icon_path = dest_app_dir / icon_dest_name
    if source_icon.resolve() != dest_icon_path.resolve():
        shutil.copy2(source_icon, dest_icon_path)

    app_meta["icon_path"] = icon_dest_name
    with open(dest_app_dir / "app_meta.json", "w", encoding="utf-8") as f:
        json.dump(app_meta, f, ensure_ascii=False, indent=2)


class DownloadAndInstallWorker(QThread):
    """Worker thread: download ZIP -> extract -> copy to apps dir.

    Signals:
        progress(int, str): (percentage, status_message)
        finished(bool, str, bool): (success, app_id_or_toolbox_id_or_error_message, is_toolbox)
    """

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str, bool)

    def __init__(self, url: str, apps_dir: Path, parent=None):
        super().__init__(parent)
        self.url = url
        self.apps_dir = apps_dir
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        temp_dir = None
        try:
            # Phase 1: Download (0-40%)
            self.progress.emit(5, f"Downloading from {self.url}...")
            temp_dir = Path(tempfile.mkdtemp(prefix="qgarage_install_"))
            zip_path = temp_dir / "app.zip"

            parsed = urlparse(self.url)
            if parsed.scheme not in ALLOWED_DOWNLOAD_SCHEMES:
                self.finished.emit(
                    False,
                    f"Invalid URL scheme '{parsed.scheme}': only http and https are allowed",
                    False,
                )
                return

            with _open_remote_zip(self.url, timeout=60) as response:
                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0

                with open(zip_path, "wb") as f:
                    while True:
                        if self._cancelled:
                            self.finished.emit(False, "Installation cancelled", False)
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
                self.finished.emit(False, "Downloaded file is not a valid ZIP archive", False)
                return

            extract_dir = temp_dir / "extracted"
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            self.progress.emit(55, "Locating metadata...")

            # Phase 3: Check for toolbox_meta.json first, then app_meta.json (55-60%)
            toolbox_meta_files = list(extract_dir.rglob("toolbox_meta.json"))
            if toolbox_meta_files:
                # This is a toolbox
                self._install_toolbox(toolbox_meta_files[0], extract_dir)
                return

            # Not a toolbox, check for app
            app_meta_files = list(extract_dir.rglob("app_meta.json"))
            if not app_meta_files:
                self.finished.emit(False, "No app_meta.json or toolbox_meta.json found in archive", False)
                return

            self._install_app(app_meta_files[0], extract_dir)

        except URLError as e:
            self.finished.emit(False, f"Download failed: {e}", False)
        except Exception as e:
            self.finished.emit(False, f"Installation error: {type(e).__name__}: {e}", False)
        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _install_app(self, app_meta_path: Path, extract_dir: Path):
        """Install a single app from extracted directory."""
        app_source_dir = app_meta_path.parent

        with open(app_meta_path, encoding="utf-8") as f:
            app_meta = json.load(f)

        app_id = app_meta.get("id")
        if not app_id:
            self.finished.emit(False, "app_meta.json missing 'id' field", False)
            return

        self.progress.emit(60, f"Installing app '{app_id}'...")

        # Phase 4: Copy to apps directory (60-70%)
        dest_dir = self.apps_dir / app_id
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(app_source_dir, dest_dir)
        _normalize_icon_path(app_meta, app_source_dir, dest_dir)

        self.progress.emit(100, "Installation complete!")
        self.finished.emit(True, app_id, False)

    def _install_toolbox(self, toolbox_meta_path: Path, extract_dir: Path):
        """Install a toolbox with multiple apps from extracted directory."""
        toolbox_source_dir = toolbox_meta_path.parent

        with open(toolbox_meta_path, encoding="utf-8") as f:
            toolbox_meta = json.load(f)

        toolbox_id = toolbox_meta.get("id")
        if not toolbox_id:
            self.finished.emit(False, "toolbox_meta.json missing 'id' field", False)
            return

        self.progress.emit(60, f"Installing toolbox '{toolbox_id}'...")

        # Copy entire toolbox directory to apps directory
        dest_dir = self.apps_dir / toolbox_id
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(toolbox_source_dir, dest_dir)

        # Normalize icon path for toolbox
        if toolbox_meta.get("icon_path"):
            icon_value = toolbox_meta["icon_path"].strip()
            source_icon = Path(icon_value)
            if not source_icon.is_absolute():
                source_icon = toolbox_source_dir / source_icon

            if source_icon.exists() and source_icon.is_file():
                icon_dest_name = source_icon.name
                dest_icon_path = dest_dir / icon_dest_name
                if source_icon.resolve() != dest_icon_path.resolve():
                    shutil.copy2(source_icon, dest_icon_path)

                toolbox_meta["icon_path"] = icon_dest_name
                with open(dest_dir / "toolbox_meta.json", "w", encoding="utf-8") as f:
                    json.dump(toolbox_meta, f, ensure_ascii=False, indent=2)

        # Normalize icon paths for all apps in the toolbox
        for child in dest_dir.iterdir():
            if child.is_dir():
                app_meta_file = child / "app_meta.json"
                if app_meta_file.exists():
                    with open(app_meta_file, encoding="utf-8") as f:
                        app_meta = json.load(f)
                    _normalize_icon_path(app_meta, toolbox_source_dir / child.name, child)

        self.progress.emit(100, "Toolbox installation complete!")
        self.finished.emit(True, toolbox_id, True)


class LocalInstallWorker(QThread):
    """Worker thread: copy local folder to apps dir.

    Signals:
        progress(int, str): (percentage, status_message)
        finished(bool, str, bool): (success, app_id_or_toolbox_id_or_error_message, is_toolbox)
    """

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str, bool)

    def __init__(self, source_dir: Path, apps_dir: Path, parent=None):
        super().__init__(parent)
        self.source_dir = source_dir
        self.apps_dir = apps_dir

    def run(self):
        try:
            # Check for toolbox first
            toolbox_meta_file = self.source_dir / "toolbox_meta.json"
            if toolbox_meta_file.exists():
                self._install_toolbox(toolbox_meta_file)
                return

            # Check for app
            meta_file = self.source_dir / "app_meta.json"
            if not meta_file.exists():
                self.finished.emit(False, "No app_meta.json or toolbox_meta.json found in selected folder", False)
                return

            self._install_app(meta_file)

        except Exception as e:
            self.finished.emit(False, f"Installation error: {type(e).__name__}: {e}", False)

    def _install_app(self, meta_file: Path):
        """Install a single app from local directory."""
        self.progress.emit(10, "Reading app metadata...")

        with open(meta_file, encoding="utf-8") as f:
            app_meta = json.load(f)

        app_id = app_meta.get("id")
        if not app_id:
            self.finished.emit(False, "app_meta.json missing 'id' field", False)
            return

        self.progress.emit(30, f"Copying app '{app_id}'...")

        # Copy to apps directory
        dest_dir = self.apps_dir / app_id
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(self.source_dir, dest_dir)
        _normalize_icon_path(app_meta, self.source_dir, dest_dir)

        self.progress.emit(100, "Installation complete!")
        self.finished.emit(True, app_id, False)

    def _install_toolbox(self, toolbox_meta_file: Path):
        """Install a toolbox from local directory."""
        self.progress.emit(10, "Reading toolbox metadata...")

        with open(toolbox_meta_file, encoding="utf-8") as f:
            toolbox_meta = json.load(f)

        toolbox_id = toolbox_meta.get("id")
        if not toolbox_id:
            self.finished.emit(False, "toolbox_meta.json missing 'id' field", False)
            return

        self.progress.emit(30, f"Copying toolbox '{toolbox_id}'...")

        # Copy to apps directory
        dest_dir = self.apps_dir / toolbox_id
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(self.source_dir, dest_dir)

        # Normalize icon path for toolbox
        if toolbox_meta.get("icon_path"):
            icon_value = toolbox_meta["icon_path"].strip()
            source_icon = Path(icon_value)
            if not source_icon.is_absolute():
                source_icon = self.source_dir / source_icon

            if source_icon.exists() and source_icon.is_file():
                icon_dest_name = source_icon.name
                dest_icon_path = dest_dir / icon_dest_name
                if source_icon.resolve() != dest_icon_path.resolve():
                    shutil.copy2(source_icon, dest_icon_path)

                toolbox_meta["icon_path"] = icon_dest_name
                with open(dest_dir / "toolbox_meta.json", "w", encoding="utf-8") as f:
                    json.dump(toolbox_meta, f, ensure_ascii=False, indent=2)

        # Normalize icon paths for all apps in the toolbox
        for child in dest_dir.iterdir():
            if child.is_dir():
                app_meta_file = child / "app_meta.json"
                if app_meta_file.exists():
                    with open(app_meta_file, encoding="utf-8") as f:
                        app_meta = json.load(f)
                    _normalize_icon_path(app_meta, self.source_dir / child.name, child)

        self.progress.emit(100, "Toolbox installation complete!")
        self.finished.emit(True, toolbox_id, True)
