"""Design asset helpers: bundled fonts and SVG icons."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QFontDatabase, QIcon, QImage, QPainter, QPixmap
from qgis.PyQt.QtSvg import QSvgRenderer

from ..core.logger import log_warning

RESOURCES_DIR = Path(__file__).resolve().parents[1] / "resources"
ICONS_DIR = RESOURCES_DIR / "icons"
FONTS_DIR = RESOURCES_DIR / "fonts"

FONT_PRIMARY = "Jersey 15"
FONT_MONO = "JetBrains Mono"

_fonts_registered = False


def register_fonts() -> None:
    """Register bundled TTF fonts with Qt once (idempotent)."""
    global _fonts_registered
    if _fonts_registered:
        return
    _fonts_registered = True
    if not FONTS_DIR.is_dir():
        log_warning(f"Font directory not found: {FONTS_DIR}", "assets")
        return
    for font_file in sorted(FONTS_DIR.glob("*.ttf")):
        if QFontDatabase.addApplicationFont(str(font_file)) < 0:
            log_warning(f"Could not load font: {font_file.name}", "assets")


def icon_path(name: str) -> Path:
    """Return the path of a bundled icon (name without extension)."""
    return ICONS_DIR / f"{name}.svg"


def pixmap(name: str, size: QSize | int, dpr: float = 2.0) -> Optional[QPixmap]:
    """Render a bundled SVG to a transparent pixmap fitting within ``size``."""
    path = icon_path(name)
    if not path.exists():
        log_warning(f"Icon not found: {path}", "assets")
        return None
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        log_warning(f"Invalid SVG: {path}", "assets")
        return None
    if isinstance(size, int):
        size = QSize(size, size)
    target = renderer.defaultSize()
    target.scale(
        QSize(int(size.width() * dpr), int(size.height() * dpr)),
        Qt.AspectRatioMode.KeepAspectRatio,
    )
    image = QImage(target, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    result = QPixmap.fromImage(image)
    result.setDevicePixelRatio(dpr)
    return result


def icon(name: str, size: QSize | int = 64) -> QIcon:
    """Return a QIcon for a bundled SVG (empty icon when unavailable)."""
    pm = pixmap(name, size)
    return QIcon(pm) if pm is not None else QIcon()
