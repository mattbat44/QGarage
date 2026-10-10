"""Detect and (re)attach apps that belong inside a sibling toolbox folder."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from .app_update import get_install_source
from .constants import APP_META_FILENAME, DEFAULT_ENCODING, TOOLBOX_META_FILENAME
from .fs_utils import remove_tree

logger = logging.getLogger("qgarage.toolbox_membership")


def _read_json(path: Path) -> Optional[dict]:
    try:
        with open(path, encoding=DEFAULT_ENCODING) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def find_parent_toolbox_meta(app_source_dir: Path) -> Optional[Path]:
    """Return the toolbox_meta.json path if app_source_dir sits directly inside a toolbox."""
    candidate = app_source_dir.parent / TOOLBOX_META_FILENAME
    return candidate if candidate.is_file() else None


def ensure_toolbox_shell(apps_dir: Path, toolbox_meta_file: Path) -> Optional[str]:
    """Ensure ``apps_dir/<toolbox_id>`` exists with a ``toolbox_meta.json``.

    Copies the toolbox metadata (and icon, if any) in only when the toolbox
    doesn't already exist in ``apps_dir``. Returns the toolbox id, or ``None``
    if the source toolbox metadata is invalid.
    """
    toolbox_meta = _read_json(toolbox_meta_file)
    if not toolbox_meta or not toolbox_meta.get("id"):
        return None

    toolbox_id = toolbox_meta["id"]
    dest_toolbox_dir = apps_dir / toolbox_id
    dest_meta_file = dest_toolbox_dir / TOOLBOX_META_FILENAME
    dest_toolbox_dir.mkdir(parents=True, exist_ok=True)
    if not dest_meta_file.exists():
        shutil.copy2(toolbox_meta_file, dest_meta_file)
        icon_value = (toolbox_meta.get("icon_path") or "").strip()
        if icon_value:
            source_icon = Path(icon_value)
            if not source_icon.is_absolute():
                source_icon = toolbox_meta_file.parent / source_icon
            if source_icon.is_file():
                shutil.copy2(source_icon, dest_toolbox_dir / source_icon.name)
    return toolbox_id


def reconcile_installed_apps(apps_dir: Path) -> list[tuple[str, str]]:
    """Move standalone installed apps back into their toolbox, if detectable.

    For each standalone app (a top-level ``apps_dir`` entry with its own
    ``app_meta.json``), checks its recorded ``local`` install source to see
    whether the original source folder sat directly inside a toolbox folder
    on disk. Apps installed from a URL, or whose original local source no
    longer exists, are left untouched.

    Returns a list of ``(app_id, toolbox_id)`` pairs that were migrated.
    """
    migrated: list[tuple[str, str]] = []
    if not apps_dir.is_dir():
        return migrated

    for child in list(apps_dir.iterdir()):
        if not child.is_dir():
            continue
        # Only standalone app folders are candidates; skip existing toolboxes.
        if (child / TOOLBOX_META_FILENAME).is_file():
            continue

        app_meta_file = child / APP_META_FILENAME
        app_meta = _read_json(app_meta_file)
        if not app_meta or not app_meta.get("id"):
            continue

        source = get_install_source(app_meta)
        if source is None or source.source_type != "local":
            continue

        toolbox_meta_file = find_parent_toolbox_meta(Path(source.locator))
        if toolbox_meta_file is None:
            continue

        toolbox_id = ensure_toolbox_shell(apps_dir, toolbox_meta_file)
        if toolbox_id is None:
            continue

        app_id = app_meta["id"]
        dest_app_dir = apps_dir / toolbox_id / app_id
        if dest_app_dir.exists():
            logger.warning(
                "Skipping toolbox reconciliation for '%s': '%s' already exists",
                app_id,
                dest_app_dir,
            )
            continue

        shutil.move(str(child), str(dest_app_dir))
        migrated.append((app_id, toolbox_id))
        logger.info(
            "Moved app '%s' into toolbox '%s' during reconciliation", app_id, toolbox_id
        )

    return migrated


def relocate_standalone_conflict(apps_dir: Path, app_id: str, keep_dir: Path) -> None:
    """Remove a stale standalone install of ``app_id`` that now lives elsewhere."""
    stale_dir = apps_dir / app_id
    if stale_dir.exists() and stale_dir.resolve() != keep_dir.resolve():
        remove_tree(stale_dir)
