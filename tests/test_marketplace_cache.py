from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from qgarage.core.marketplace import MarketplaceItem
from qgarage.core.marketplace_cache import CACHE_FILENAME, MarketplaceCache


def test_marketplace_cache_persists_directories_items_and_scan_times(tmp_path):
    cache = MarketplaceCache(tmp_path / ".garage")
    directory = Path("C:/marketplace")
    scanned_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    item = MarketplaceItem(
        source_dir=directory / "app",
        metadata={"id": "app", "name": "App", "version": "1.0.0"},
        is_toolbox=False,
    )

    cache.save([directory], [item], {directory: scanned_at})
    snapshot = cache.load()

    assert (tmp_path / ".garage" / CACHE_FILENAME).exists()
    assert snapshot.directories == [directory]
    assert snapshot.items == [item]
    assert snapshot.scanned_at == {directory: scanned_at}


def test_marketplace_cache_marks_old_scans_as_stale(tmp_path):
    cache = MarketplaceCache(tmp_path / ".garage")
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)

    assert not cache.is_stale(now - timedelta(days=7), now=now)
    assert cache.is_stale(now - timedelta(days=7, seconds=1), now=now)