import json
import logging
from datetime import datetime, timezone

from qgis.core import QgsSettings

SETTINGS_PREFIX = "qhub/"
MAX_HISTORY_ENTRIES = 20

logger = logging.getLogger("qhub.settings")


def get_setting(key: str, default=None):
    """Read a QHub setting from QGIS settings store."""
    return QgsSettings().value(SETTINGS_PREFIX + key, default)


def set_setting(key: str, value):
    """Write a QHub setting to QGIS settings store."""
    QgsSettings().setValue(SETTINGS_PREFIX + key, value)


def get_uv_executable() -> str:
    return get_setting("uv_executable", "uv")


class ParameterCache:
    """Persist and recall per-app parameter values via QgsSettings.

    Stores:
    - ``last`` — the most recently used parameter set (auto-restored on build)
    - ``history`` — a list of up to MAX_HISTORY_ENTRIES recent runs with timestamps
    """

    def __init__(self, app_id: str):
        self._prefix = f"{SETTINGS_PREFIX}app_cache/{app_id}/"
        self._qs = QgsSettings()

    # --- last-used params ---

    def save_last(self, params: dict) -> None:
        """Persist *params* as the last-used set for this app."""
        try:
            self._qs.setValue(self._prefix + "last", json.dumps(params, default=str))
        except Exception:
            logger.debug("Could not save last params", exc_info=True)

    def load_last(self) -> dict | None:
        """Return the last-used parameter dict, or *None*."""
        raw = self._qs.value(self._prefix + "last", None)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    # --- run history ---

    def push_history(self, params: dict) -> None:
        """Append *params* (with timestamp) to the run history ring."""
        history = self.load_history()
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "params": params,
        }
        history.append(entry)
        # Keep only the most recent entries
        history = history[-MAX_HISTORY_ENTRIES:]
        try:
            self._qs.setValue(
                self._prefix + "history", json.dumps(history, default=str)
            )
        except Exception:
            logger.debug("Could not save history", exc_info=True)

    def load_history(self) -> list[dict]:
        """Return the run history list (oldest first)."""
        raw = self._qs.value(self._prefix + "history", None)
        if raw is None:
            return []
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    def clear(self) -> None:
        """Remove all cached data for this app."""
        self._qs.remove(self._prefix)
