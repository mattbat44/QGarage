"""Logging utility for QHub using QGIS message log."""
from qgis.core import Qgis, QgsMessageLog

PLUGIN_NAME = "QHub"


def log_info(message: str, tag: str = ""):
    """Log an info message."""
    full_tag = f"{PLUGIN_NAME}.{tag}" if tag else PLUGIN_NAME
    QgsMessageLog.logMessage(message, full_tag, Qgis.MessageLevel.Info)


def log_warning(message: str, tag: str = ""):
    """Log a warning message."""
    full_tag = f"{PLUGIN_NAME}.{tag}" if tag else PLUGIN_NAME
    QgsMessageLog.logMessage(message, full_tag, Qgis.MessageLevel.Warning)


def log_error(message: str, tag: str = ""):
    """Log an error message."""
    full_tag = f"{PLUGIN_NAME}.{tag}" if tag else PLUGIN_NAME
    QgsMessageLog.logMessage(message, full_tag, Qgis.MessageLevel.Critical)


def log_debug(message: str, tag: str = ""):
    """Log a debug message."""
    full_tag = f"{PLUGIN_NAME}.{tag}" if tag else PLUGIN_NAME
    QgsMessageLog.logMessage(message, full_tag, Qgis.MessageLevel.Info)
