"""Read-only discovery of apps and toolboxes offered by local directories."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .constants import APP_META_FILENAME, DEFAULT_ENCODING, TOOLBOX_META_FILENAME


@dataclass(frozen=True)
class MarketplaceItem:
    """A locally available app or toolbox that has not been installed."""

    source_dir: Path
    metadata: dict
    is_toolbox: bool
    app_count: int = 0
    parent_toolbox_id: str | None = None
    parent_toolbox_name: str | None = None

    @property
    def item_id(self) -> str:
        return self.metadata["id"]

    @property
    def name(self) -> str:
        return self.metadata.get("name", self.item_id)


def scan_marketplace(
    directories: list[Path], *, is_cancelled=None
) -> list[MarketplaceItem]:
    """Return installable items beneath directories without modifying the filesystem."""
    items: list[MarketplaceItem] = []
    seen_dirs: set[Path] = set()

    for directory in directories:
        if is_cancelled is not None and is_cancelled():
            return []
        source_root = Path(directory)
        if not source_root.is_dir():
            continue

        for current_root, child_dirs, file_names in _walk_directories(source_root):
            if is_cancelled is not None and is_cancelled():
                return []
            current_dir = Path(current_root)
            metadata_name = (
                TOOLBOX_META_FILENAME
                if TOOLBOX_META_FILENAME in file_names
                else APP_META_FILENAME
                if APP_META_FILENAME in file_names
                else None
            )
            if metadata_name is None:
                continue

            resolved_dir = current_dir.resolve()
            if resolved_dir in seen_dirs:
                child_dirs[:] = []
                continue

            metadata = _read_metadata(current_dir / metadata_name)
            if metadata is None:
                continue

            is_toolbox = metadata_name == TOOLBOX_META_FILENAME
            app_count = _count_toolbox_apps(current_dir) if is_toolbox else 0
            items.append(
                MarketplaceItem(
                    source_dir=current_dir,
                    metadata=metadata,
                    is_toolbox=is_toolbox,
                    app_count=app_count,
                )
            )
            seen_dirs.add(resolved_dir)
            if is_toolbox:
                items.extend(_toolbox_app_items(current_dir, metadata, seen_dirs))
            child_dirs[:] = []

    return _latest_items(items)


def _walk_directories(directory: Path):
    """Yield directory contents while avoiding symlink recursion."""
    import os

    for root, child_dirs, file_names in os.walk(directory, followlinks=False):
        child_dirs[:] = [
            child for child in child_dirs if not (Path(root) / child).is_symlink()
        ]
        yield root, child_dirs, file_names


def _read_metadata(metadata_file: Path) -> dict | None:
    try:
        with open(metadata_file, encoding=DEFAULT_ENCODING) as file_handle:
            metadata = json.load(file_handle)
    except (json.JSONDecodeError, OSError):
        return None

    return metadata if isinstance(metadata, dict) and metadata.get("id") else None


def _count_toolbox_apps(toolbox_dir: Path) -> int:
    return sum(
        1
        for child in toolbox_dir.iterdir()
        if child.is_dir() and _read_metadata(child / APP_META_FILENAME) is not None
    )


def _toolbox_app_items(
    toolbox_dir: Path, toolbox_metadata: dict, seen_dirs: set[Path]
) -> list[MarketplaceItem]:
    """Return direct toolbox members so users can install tools individually."""
    items = []
    toolbox_name = toolbox_metadata.get("name", toolbox_metadata["id"])
    for child in toolbox_dir.iterdir():
        if not child.is_dir():
            continue
        metadata = _read_metadata(child / APP_META_FILENAME)
        if metadata is None or child.resolve() in seen_dirs:
            continue
        seen_dirs.add(child.resolve())
        items.append(
            MarketplaceItem(
                source_dir=child,
                metadata=metadata,
                is_toolbox=False,
                parent_toolbox_id=toolbox_metadata["id"],
                parent_toolbox_name=toolbox_name,
            )
        )
    return items


def _latest_items(items: list[MarketplaceItem]) -> list[MarketplaceItem]:
    """Keep newest toolbox versions and the tools they contain."""
    newest_toolboxes = _newest_by_id(item for item in items if item.is_toolbox)
    newest_toolbox_paths = {
        item.source_dir.resolve() for item in newest_toolboxes.values()
    }
    tool_items = (
        item
        for item in items
        if not item.is_toolbox
        and (
            item.parent_toolbox_id is None
            or item.source_dir.parent.resolve() in newest_toolbox_paths
        )
    )
    newest_tools = _newest_by_id(tool_items)
    return sorted(
        [*newest_toolboxes.values(), *newest_tools.values()],
        key=lambda item: (item.name.casefold(), item.item_id),
    )


def _newest_by_id(items) -> dict[str, MarketplaceItem]:
    newest: dict[str, MarketplaceItem] = {}
    for item in items:
        current = newest.get(item.item_id)
        if current is None or _version_key(item) > _version_key(current):
            newest[item.item_id] = item
    return newest


def _version_key(item: MarketplaceItem) -> tuple[tuple[int, int | str], ...]:
    value = str(item.metadata.get("version") or "")
    parts: list[tuple[int, int | str]] = []
    for token in re.findall(r"\d+|[A-Za-z]+", value):
        parts.append((0, int(token)) if token.isdigit() else (1, token.lower()))
    return tuple(parts)