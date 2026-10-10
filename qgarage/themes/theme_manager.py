from __future__ import annotations

from pathlib import Path

from ..core.constants import DEFAULT_ENCODING, THEME_FILE
from ..core.logger import log_warning
from .assets import register_fonts

THEMES_DIR = Path(__file__).parent

# Cache for loaded stylesheets
_stylesheet_cache: dict[str, str] = {}


class ThemeManager:
    """Applies the single QGarage QSS theme to QGarage widgets."""

    @classmethod
    def get_stylesheet(cls) -> str:
        """Return the QSS stylesheet content (cached)."""
        if THEME_FILE in _stylesheet_cache:
            return _stylesheet_cache[THEME_FILE]

        qss_path = THEMES_DIR / THEME_FILE
        if not qss_path.exists():
            log_warning(f"Theme file not found: {qss_path}", "theme")
            return ""

        content = qss_path.read_text(encoding=DEFAULT_ENCODING)
        _stylesheet_cache[THEME_FILE] = content
        return content

    @classmethod
    def apply_to_widget(cls, widget) -> None:
        """Apply the stylesheet to a specific widget (never globally)."""
        register_fonts()
        widget.setStyleSheet(cls.get_stylesheet())
