from qgis.core import QgsSettings

SETTINGS_PREFIX = "qhub/"


def get_setting(key: str, default=None):
    """Read a QHub setting from QGIS settings store."""
    return QgsSettings().value(SETTINGS_PREFIX + key, default)


def set_setting(key: str, value):
    """Write a QHub setting to QGIS settings store."""
    QgsSettings().setValue(SETTINGS_PREFIX + key, value)


def get_uv_executable() -> str:
    return get_setting("uv_executable", "uv")
