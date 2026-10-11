"""Shared pill-shaped card surface used by app and toolbox cards."""

from __future__ import annotations

from qgis.PyQt.QtCore import QPointF, QRectF, QSize, QSizeF, Qt
from qgis.PyQt.QtGui import QColor, QIcon, QPainter, QPen
from qgis.PyQt.QtWidgets import QFrame, QPushButton, QSizePolicy

COLOR_WHITE = "#FFFFFF"
COLOR_GREEN = "#8DAD25"
COLOR_BLACK = "#000000"

#: Extra pixels below the pill where the soft shadow falls.
SHADOW_OFFSET = 4
#: Padding on every side so the outline and shadow blur are never clipped.
EDGE_PAD = 7
#: Number of translucent layers used to build the blurred shadow.
SHADOW_LAYERS = 7


def apply_soft_shadow(widget, blur: int = 18, offset_y: int = 4, alpha: int = 70) -> None:
    """Give a widget a soft, natural drop shadow."""
    from qgis.PyQt.QtWidgets import QGraphicsDropShadowEffect

    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, offset_y)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)


def pill_margins(left: int, top: int, right: int, bottom: int) -> tuple[int, int, int, int]:
    """Return layout margins that keep content inside the pill outline."""
    pad = EDGE_PAD
    return (left + pad, top + pad, right + pad, bottom + pad + SHADOW_OFFSET)


class PillFrame(QFrame):
    """A stadium-shaped white surface with a black outline and offset shadow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hovered = False

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        body = QRectF(self.rect()).adjusted(
            EDGE_PAD, EDGE_PAD, -EDGE_PAD, -(EDGE_PAD + SHADOW_OFFSET)
        )
        radius = body.height() / 2.0

        # Soft shadow: stacked translucent rounded rects fading outwards.
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(SHADOW_LAYERS, 0, -1):
            alpha = int(20 * (1.0 - (i - 1) / SHADOW_LAYERS))
            painter.setBrush(QColor(0, 0, 0, alpha))
            grown = body.adjusted(-i, -i, i, i).translated(0, SHADOW_OFFSET * 0.6)
            painter.drawRoundedRect(grown, radius + i, radius + i)

        outline = COLOR_GREEN if self._hovered else COLOR_BLACK
        painter.setPen(QPen(QColor(outline), 1.5))
        painter.setBrush(QColor(COLOR_WHITE))
        painter.drawRoundedRect(body, radius, radius)
        painter.end()


class CircleButton(QPushButton):
    """Round icon button whose icon scales with the button size."""

    def __init__(self, size: int = 64, parent=None):
        super().__init__(parent)
        self.setFlat(True)
        self._diameter = size
        self._icon_rotation = 0.0
        self._icon_anchor = (0.5, 0.5)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        return QSize(self._diameter, self._diameter)

    def minimumSizeHint(self):
        return QSize(self._diameter, self._diameter)

    def set_icon_anchor(self, fx: float, fy: float) -> None:
        """Set the fractional point of the icon that sits at the button centre."""
        self._icon_anchor = (float(fx), float(fy))
        self.update()

    def set_icon_rotation(self, degrees: float) -> None:
        """Rotate the icon about its centre (clockwise degrees)."""
        self._icon_rotation = float(degrees)
        self.update()

    def set_diameter(self, size: int) -> None:
        self._diameter = size
        self.setFixedSize(size, size)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        enabled = self.isEnabled()
        if not enabled:
            border, fill = QColor("#8a8a8a"), QColor(COLOR_WHITE)
        elif self.isDown():
            border, fill = QColor(COLOR_BLACK), QColor(COLOR_GREEN)
        elif self.underMouse():
            border, fill = QColor(COLOR_GREEN), QColor(COLOR_WHITE)
        else:
            border, fill = QColor(COLOR_BLACK), QColor(COLOR_WHITE)
        painter.setPen(QPen(border, 2))
        painter.setBrush(fill)
        painter.drawEllipse(rect)

        icon = self.icon()
        if not icon.isNull():
            side = int(rect.width() * 0.6)
            mode = QIcon.Mode.Normal if enabled else QIcon.Mode.Disabled
            pixmap = icon.pixmap(QSize(side, side), mode)
            # Draw at the pixmap's own aspect ratio so icons are never stretched.
            ratio = pixmap.devicePixelRatio() or 1.0
            logical = QSizeF(pixmap.width() / ratio, pixmap.height() / ratio)
            painter.save()
            painter.translate(rect.center())
            if self._icon_rotation:
                painter.rotate(self._icon_rotation)
            painter.drawPixmap(
                QPointF(
                    -logical.width() * self._icon_anchor[0],
                    -logical.height() * self._icon_anchor[1],
                ),
                pixmap,
            )
            painter.restore()
        painter.end()


def build_dialog_shell(dialog, title: str):
    """Style a QDialog with the QGarage theme and return the inner panel layout."""
    from qgis.PyQt.QtWidgets import QLabel, QVBoxLayout

    from ..themes.theme_manager import ThemeManager

    dialog.setObjectName("qgarageDialog")
    dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    ThemeManager.apply_to_widget(dialog)

    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(20, 18, 20, 20)
    outer.setSpacing(12)

    title_label = QLabel(title)
    title_label.setObjectName("dialogTitle")
    outer.addWidget(title_label)

    panel = QFrame()
    panel.setObjectName("dialogPanel")
    apply_soft_shadow(panel)
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(18, 16, 18, 16)
    panel_layout.setSpacing(10)
    outer.addWidget(panel)
    return panel_layout
