from pathlib import Path
from typing import Optional

from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtGui import QPalette

from ..core.constants import (
    DARK_THEME_FILE,
    DARK_THEME_LUMINANCE_THRESHOLD,
    DEFAULT_ENCODING,
    LIGHT_THEME_FILE,
)
from ..core.logger import log_warning

THEMES_DIR = Path(__file__).parent

# Cache for loaded stylesheets
_stylesheet_cache: dict[str, str] = {}


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
        return luminance < DARK_THEME_LUMINANCE_THRESHOLD

    @classmethod
    def get_stylesheet(cls) -> str:
        """Return the appropriate QSS stylesheet content (cached)."""
        theme_file = DARK_THEME_FILE if cls.is_dark_theme() else LIGHT_THEME_FILE

        # Check cache first
        if theme_file in _stylesheet_cache:
            return _stylesheet_cache[theme_file]

        # Load and cache
        qss_path = THEMES_DIR / theme_file
        if not qss_path.exists():
            log_warning(f"Theme file not found: {qss_path}", "theme")
            return ""

        content = qss_path.read_text(encoding=DEFAULT_ENCODING)
        _stylesheet_cache[theme_file] = content
        return content

    @classmethod
    def apply_to_widget(cls, widget) -> None:
        """Apply the current theme's stylesheet to a specific widget.

        Applied at the widget level only — never globally — to avoid
        interfering with QGIS's own styling or other plugins.
        """
        stylesheet = cls.get_stylesheet()
        widget.setStyleSheet(stylesheet)
