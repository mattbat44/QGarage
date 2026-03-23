import logging
from pathlib import Path

from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtGui import QPalette

logger = logging.getLogger("qhub.theme_manager")

THEMES_DIR = Path(__file__).parent


class ThemeManager:
    """Detects QGIS theme (dark/light) and applies matching QSS to QHub widgets."""

    @staticmethod
    def is_dark_theme() -> bool:
        """Detect whether QGIS is using a dark theme.

        Compares the window background luminance against a threshold.
        """
        app = QApplication.instance()
        if app is None:
            return False
        palette = app.palette()
        bg = palette.color(QPalette.ColorRole.Window)
        luminance = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
        return luminance < 128

    @classmethod
    def get_stylesheet(cls) -> str:
        """Return the appropriate QSS stylesheet content."""
        theme_file = "dark.qss" if cls.is_dark_theme() else "light.qss"
        qss_path = THEMES_DIR / theme_file
        if not qss_path.exists():
            logger.warning(f"Theme file not found: {qss_path}")
            return ""
        return qss_path.read_text(encoding="utf-8")

    @classmethod
    def apply_to_widget(cls, widget) -> None:
        """Apply the current theme's stylesheet to a specific widget.

        Applied at the widget level only — never globally — to avoid
        interfering with QGIS's own styling or other plugins.
        """
        stylesheet = cls.get_stylesheet()
        widget.setStyleSheet(stylesheet)
