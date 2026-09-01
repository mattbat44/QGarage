"""Persistence for metadata-only local marketplace scans."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .marketplace import MarketplaceItem

CACHE_FILENAME = "marketplace_cache.json"
CACHE_MAX_AGE = timedelta(days=7)


@dataclass
class MarketplaceCacheSnapshot:
    """Cached marketplace directories, metadata, and scan timestamps."""

    directories: list[Path]
    items: list[MarketplaceItem]
    scanned_at: dict[Path, datetime]


class MarketplaceCache:
    """Read and write marketplace listings beneath the managed apps directory."""

    def __init__(self, apps_dir: Path):
        self._cache_file = apps_dir / CACHE_FILENAME

    def load(self) -> MarketplaceCacheSnapshot:
        """Load valid cached data, returning an empty snapshot on any failure."""
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return MarketplaceCacheSnapshot([], [], {})
        if not isinstance(data, dict):
            return MarketplaceCacheSnapshot([], [], {})

        directories = []
        scanned_at = {}
        for entry in data.get("directories", []):
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                continue
            directory = Path(entry["path"])
            directories.append(directory)
            timestamp = _parse_timestamp(entry.get("scanned_at"))
            if timestamp is not None:
                scanned_at[directory] = timestamp

        items = [_item_from_data(item) for item in data.get("items", [])]
        return MarketplaceCacheSnapshot(
            directories=directories,
            items=[item for item in items if item is not None],
            scanned_at=scanned_at,
        )

    def save(
        self,
        directories: list[Path],
        items: list[MarketplaceItem],
        scanned_at: dict[Path, datetime],
    ) -> None:
        """Persist selected directories and their metadata listings atomically."""
        data = {
            "version": 1,
            "directories": [
                {
                    "path": str(directory),
                    "scanned_at": _format_timestamp(scanned_at.get(directory)),
                }
                for directory in directories
            ],
            "items": [_item_to_data(item) for item in items],
        }
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            temporary_file = self._cache_file.with_suffix(".tmp")
            temporary_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary_file.replace(self._cache_file)
        except OSError:
            return

    @staticmethod
    def is_stale(scanned_at: datetime, *, now: datetime | None = None) -> bool:
        """Return whether a scan is older than the marketplace refresh threshold."""
        now = now or datetime.now(timezone.utc)
        return now - scanned_at > CACHE_MAX_AGE


def _item_to_data(item: MarketplaceItem) -> dict:
    return {
        "source_dir": str(item.source_dir),
        "metadata": item.metadata,
        "is_toolbox": item.is_toolbox,
        "app_count": item.app_count,
        "parent_toolbox_id": item.parent_toolbox_id,
        "parent_toolbox_name": item.parent_toolbox_name,
    }


def _item_from_data(data: object) -> MarketplaceItem | None:
    if not isinstance(data, dict) or not isinstance(data.get("metadata"), dict):
        return None
    source_dir = data.get("source_dir")
    if not isinstance(source_dir, str) or not data["metadata"].get("id"):
        return None
    return MarketplaceItem(
        source_dir=Path(source_dir),
        metadata=data["metadata"],
        is_toolbox=bool(data.get("is_toolbox")),
        app_count=int(data.get("app_count", 0)),
        parent_toolbox_id=data.get("parent_toolbox_id"),
        parent_toolbox_name=data.get("parent_toolbox_name"),
    )


def _format_timestamp(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value is not None else None


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    return (
        timestamp.replace(tzinfo=timezone.utc)
        if timestamp.tzinfo is None
        else timestamp.astimezone(timezone.utc)
    )