from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import (
    HTTPHandler,
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
)

from .constants import (
    APP_META_FILENAME,
    DEFAULT_ENCODING,
    PIXI_ENV_DIR,
    PIXI_TOML_FILENAME,
    REQUIREMENTS_FILENAME,
    VENV_DIR,
)
from .settings import get_setting, set_setting

INSTALL_SOURCE_KEY = "qgarage_install_source"
INSTALL_SOURCE_TYPE_KEY = "qgarage_install_source_type"
INSTALL_SOURCE_APP_RELPATH_KEY = "qgarage_install_source_app_relpath"

ALLOWED_DOWNLOAD_SCHEMES = {"http", "https"}
UPDATE_CHECK_INTERVAL = timedelta(hours=6)
_SKIP_COPY_NAMES = {VENV_DIR, PIXI_ENV_DIR, "__pycache__"}


@dataclass(frozen=True)
class InstallSource:
    source_type: str
    locator: str
    app_relpath: Optional[str] = None


@dataclass
class SourceSnapshot:
    app_dir: Path
    app_meta: dict
    temp_dir: Optional[Path] = None

    def cleanup(self) -> None:
        if self.temp_dir is not None and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)


@dataclass(frozen=True)
class UpdateCheckResult:
    available: bool
    available_version: Optional[str] = None


@dataclass(frozen=True)
class UpdateApplyResult:
    app_meta: dict
    requirements_changed: bool
    pixi_changed: bool


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


def stamp_install_source(
    app_meta: dict,
    *,
    source_type: str,
    source_locator: str,
    app_relpath: Optional[str] = None,
) -> dict:
    """Store install-source metadata inside an installed app's app_meta."""
    app_meta[INSTALL_SOURCE_TYPE_KEY] = source_type
    app_meta[INSTALL_SOURCE_KEY] = source_locator
    if app_relpath and app_relpath != ".":
        app_meta[INSTALL_SOURCE_APP_RELPATH_KEY] = app_relpath
    else:
        app_meta.pop(INSTALL_SOURCE_APP_RELPATH_KEY, None)
    return app_meta


def get_install_source(app_meta: dict) -> Optional[InstallSource]:
    """Return the recorded install source for an installed app, if any."""
    source_type = (app_meta.get(INSTALL_SOURCE_TYPE_KEY) or "").strip()
    locator = (app_meta.get(INSTALL_SOURCE_KEY) or "").strip()
    if not source_type or not locator:
        return None
    app_relpath = (app_meta.get(INSTALL_SOURCE_APP_RELPATH_KEY) or "").strip() or None
    return InstallSource(source_type=source_type, locator=locator, app_relpath=app_relpath)


def should_check_for_updates(app_id: str, *, force: bool = False) -> bool:
    """Return True when an app is due for an update check."""
    if force:
        return True

    raw_value = get_setting(_update_check_setting_key(app_id), None)
    if not isinstance(raw_value, str) or not raw_value:
        return True

    try:
        last_checked = datetime.fromisoformat(raw_value)
    except ValueError:
        return True

    if last_checked.tzinfo is None:
        last_checked = last_checked.replace(tzinfo=timezone.utc)

    return datetime.now(timezone.utc) - last_checked >= UPDATE_CHECK_INTERVAL


def record_update_check(app_id: str) -> None:
    """Persist the timestamp of a completed update check."""
    set_setting(_update_check_setting_key(app_id), datetime.now(timezone.utc).isoformat())


def check_for_app_update(app_meta: dict) -> UpdateCheckResult:
    """Check the recorded install source for a newer app version."""
    source = get_install_source(app_meta)
    app_id = str(app_meta.get("id") or "")
    installed_version = str(app_meta.get("version") or "")
    if source is None or not app_id or not installed_version:
        return UpdateCheckResult(available=False)

    snapshot = _resolve_source_snapshot(source, app_id)
    if snapshot is None:
        return UpdateCheckResult(available=False)

    try:
        available_version = str(snapshot.app_meta.get("version") or "")
        if available_version and _is_version_newer(available_version, installed_version):
            return UpdateCheckResult(
                available=True,
                available_version=available_version,
            )
        return UpdateCheckResult(available=False)
    finally:
        snapshot.cleanup()


def apply_update_from_source(installed_app_dir: Path, installed_app_meta: dict) -> UpdateApplyResult:
    """Replace installed app files from the recorded source while preserving envs."""
    source = get_install_source(installed_app_meta)
    app_id = str(installed_app_meta.get("id") or "")
    if source is None or not app_id:
        raise RuntimeError("This app does not have a recorded install source.")

    snapshot = _resolve_source_snapshot(source, app_id)
    if snapshot is None:
        raise RuntimeError("The recorded install source is no longer available.")

    try:
        old_requirements = _read_optional_text(installed_app_dir / REQUIREMENTS_FILENAME)
        old_pixi = _read_optional_text(installed_app_dir / PIXI_TOML_FILENAME)

        _clear_installed_app_dir(installed_app_dir)
        _copy_app_contents(snapshot.app_dir, installed_app_dir)

        updated_meta = _load_json(installed_app_dir / APP_META_FILENAME)
        updated_meta = stamp_install_source(
            updated_meta,
            source_type=source.source_type,
            source_locator=source.locator,
            app_relpath=source.app_relpath,
        )
        _normalize_icon_path(updated_meta, snapshot.app_dir, installed_app_dir)
        _write_json(installed_app_dir / APP_META_FILENAME, updated_meta)

        new_requirements = _read_optional_text(installed_app_dir / REQUIREMENTS_FILENAME)
        new_pixi = _read_optional_text(installed_app_dir / PIXI_TOML_FILENAME)

        return UpdateApplyResult(
            app_meta=updated_meta,
            requirements_changed=old_requirements != new_requirements,
            pixi_changed=old_pixi != new_pixi,
        )
    finally:
        snapshot.cleanup()


def _update_check_setting_key(app_id: str) -> str:
    return f"app_update/{app_id}/last_checked"


def _open_remote_zip(url: str, timeout: int):
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_DOWNLOAD_SCHEMES:
        raise URLError(
            f"Invalid URL scheme '{parsed.scheme}': only http and https are allowed"
        )

    opener = build_opener(HTTPHandler, HTTPSHandler, _SafeHttpRedirectHandler)
    req = Request(url, headers={"User-Agent": "QGarage/0.1"})
    return opener.open(req, timeout=timeout)


def _resolve_source_snapshot(source: InstallSource, app_id: str) -> Optional[SourceSnapshot]:
    if source.source_type == "local":
        return _resolve_local_snapshot(source, app_id)
    if source.source_type == "url":
        return _resolve_remote_snapshot(source, app_id)
    return None


def _resolve_local_snapshot(source: InstallSource, app_id: str) -> Optional[SourceSnapshot]:
    source_root = Path(source.locator).expanduser()
    if not source_root.exists():
        return None

    app_dir = _resolve_local_app_dir(source_root, app_id, source.app_relpath)
    if app_dir is None:
        return None

    app_meta = _load_json(app_dir / APP_META_FILENAME)
    return SourceSnapshot(app_dir=app_dir, app_meta=app_meta)


def _resolve_remote_snapshot(source: InstallSource, app_id: str) -> Optional[SourceSnapshot]:
    temp_dir = Path(tempfile.mkdtemp(prefix="qgarage_update_"))
    zip_path = temp_dir / "app.zip"
    extract_dir = temp_dir / "extracted"

    try:
        with _open_remote_zip(source.locator, timeout=20) as response:
            with open(zip_path, "wb") as f:
                shutil.copyfileobj(response, f)

        if not zipfile.is_zipfile(zip_path):
            return None

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        app_dir = _resolve_local_app_dir(extract_dir, app_id, source.app_relpath)
        if app_dir is None:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        app_meta = _load_json(app_dir / APP_META_FILENAME)
        return SourceSnapshot(app_dir=app_dir, app_meta=app_meta, temp_dir=temp_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None


def _resolve_local_app_dir(
    source_root: Path, app_id: str, app_relpath: Optional[str]
) -> Optional[Path]:
    if app_relpath:
        candidate = source_root / app_relpath
        if _is_matching_app_dir(candidate, app_id):
            return candidate

    if _is_matching_app_dir(source_root, app_id):
        return source_root

    for meta_file in source_root.rglob(APP_META_FILENAME):
        candidate = meta_file.parent
        if _is_matching_app_dir(candidate, app_id):
            return candidate
    return None


def _is_matching_app_dir(candidate: Path, app_id: str) -> bool:
    meta_file = candidate / APP_META_FILENAME
    if not meta_file.exists():
        return False
    try:
        return str(_load_json(meta_file).get("id") or "") == app_id
    except Exception:
        return False


def _clear_installed_app_dir(app_dir: Path) -> None:
    for child in app_dir.iterdir():
        if child.name in {VENV_DIR, PIXI_ENV_DIR}:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _copy_app_contents(source_app_dir: Path, dest_app_dir: Path) -> None:
    for child in source_app_dir.iterdir():
        if child.name in _SKIP_COPY_NAMES:
            continue
        dest_path = dest_app_dir / child.name
        if child.is_dir():
            shutil.copytree(
                child,
                dest_path,
                ignore=shutil.ignore_patterns(*_SKIP_COPY_NAMES),
            )
        else:
            shutil.copy2(child, dest_path)


def _normalize_icon_path(app_meta: dict, source_app_dir: Path, dest_app_dir: Path) -> None:
    icon_value = (app_meta.get("icon_path") or "").strip()
    if not icon_value:
        return

    source_icon = Path(icon_value)
    if not source_icon.is_absolute():
        source_icon = source_app_dir / source_icon

    if not source_icon.exists() or not source_icon.is_file():
        return

    dest_icon_path = dest_app_dir / source_icon.name
    if source_icon.resolve() != dest_icon_path.resolve():
        shutil.copy2(source_icon, dest_icon_path)

    app_meta["icon_path"] = source_icon.name


def _read_optional_text(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return path.read_text(encoding=DEFAULT_ENCODING)


def _load_json(path: Path) -> dict:
    with open(path, encoding=DEFAULT_ENCODING) as f:
        return json.load(f)


def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding=DEFAULT_ENCODING) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _version_key(value: str) -> tuple:
    parts: list[tuple[int, object]] = []
    token = ""
    is_digit_token = None
    for char in value.strip():
        char_is_digit = char.isdigit()
        if is_digit_token is None or char_is_digit == is_digit_token:
            token += char
            is_digit_token = char_is_digit
            continue
        parts.append((0, int(token)) if is_digit_token else (1, token.lower()))
        token = char
        is_digit_token = char_is_digit
    if token:
        parts.append((0, int(token)) if is_digit_token else (1, token.lower()))
    return tuple(parts)


def _is_version_newer(candidate: str, installed: str) -> bool:
    if not candidate or not installed or candidate == installed:
        return False
    return _version_key(candidate) > _version_key(installed)
