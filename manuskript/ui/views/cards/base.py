"""The drawing sequence every cork index card follows.

A card is painted in a fixed order: selection, chrome, label corner, summary
backdrop, border, icon, title, overlay, status watermark, summaries. That
order is the same for every style and belongs to this base class, so a style
cannot accidentally skip a phase or reinvent one.

A style supplies geometry and the phases that make it look like itself. Phases
it does not care about default to doing nothing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from PyQt5.QtCore import QRect, QSize, Qt
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QPalette,
    QPolygonF,
    QRegion,
)
from PyQt5.QtWidgets import QStyle, qApp

from manuskript.enums import Outline
from manuskript.functions import colorifyPixmap


@dataclass(frozen=True)
class CardLayout:
    """Where each part of one card is drawn."""

    item: QRect
    top: QRect
    icon: QRect
    label: QRect
    title: QRect
    main: QRect
    main_line: QRect
    main_text: QRect
    card: Optional[QRect] = None      # plain: the card below the folder tab
    bottom: Optional[QRect] = None    # ruled: the body under the title bar

    @property
    def body(self):
        """The region a watermark and background should cover."""
        return self.card if self.card is not None else self.main


@dataclass
class CardContext:
    """Per-paint scratchpad for one card.

    Deliberately mutable: earlier phases record what later ones need. The
    background colour decides the title colour, and a folder's outline shape
    is computed while filling it but reused when stroking the border.
    """

    index: Any
    option: Any
    item: Any
    colors: Any
    settings: Any
    factor: float
    margin: int
    status_item: Callable[[Any], Any]
    bg_colors: dict = field(default_factory=dict)

    background: QColor = field(default_factory=lambda: QColor(Qt.white))
    folder_polygon: Optional[QPolygonF] = None
    text_color: Optional[QColor] = None

    def view_setting(self, name):
        return self.settings.viewSettings["Cork"][name]

    def shows(self, name):
        return self.view_setting(name) != "Nothing"

    def color_for(self, name):
        return self.colors[self.view_setting(name)]


class IndexCardStyle(ABC):
    """Base class for every cork index card style."""

    #: Reverse-DNS identifier, matching the plugin ID convention.
    id = ""
    #: Human name shown in the settings dropdown.
    name = ""

    # ------------------------------------------------------------------
    # Geometry. Every style must answer these.

    @abstractmethod
    def size_hint(self, factor):
        """Card size before the cork size factor is applied."""

    @abstractmethod
    def layout(self, ctx):
        """Return a CardLayout for one item."""

    # ------------------------------------------------------------------
    # The fixed sequence. Not overridden.

    def paint(self, p, ctx, layout):
        self.draw_selection(p, ctx, layout)
        self.draw_chrome(p, ctx, layout)
        self.draw_label_corner(p, ctx, layout)
        self.draw_summary_backdrop(p, ctx, layout)
        self.draw_border(p, ctx, layout)
        self._draw_icon(p, ctx, layout)
        self._draw_title(p, ctx, layout)
        self.draw_overlay(p, ctx, layout)
        self._draw_status(p, ctx, layout)
        self._draw_summaries(p, ctx, layout)

    # ------------------------------------------------------------------
    # Phases a style may replace. Defaults draw nothing.

    def draw_selection(self, p, ctx, layout):
        if not ctx.option.state & QStyle.State_Selected:
            return
        p.save()
        p.setBrush(ctx.option.palette.brush(
            self._color_group(ctx), QPalette.Highlight))
        p.setPen(Qt.NoPen)
        self.fill_selection(p, ctx, layout)
        p.restore()

    def fill_selection(self, p, ctx, layout):
        p.drawRect(ctx.option.rect)

    def draw_chrome(self, p, ctx, layout):
        """Card body, and anything structural like a title bar or stack."""

    def draw_label_corner(self, p, ctx, layout):
        """The label colour marker."""

    def draw_summary_backdrop(self, p, ctx, layout):
        """Any fill behind the one-line summary."""

    def draw_border(self, p, ctx, layout):
        """The card outline."""

    def draw_overlay(self, p, ctx, layout):
        """Anything drawn over the body, such as rule lines."""

    # ------------------------------------------------------------------
    # Text presentation a style may tune.

    def title_font(self, base):
        f = QFont(base)
        f.setBold(True)
        return f

    def title_alignment(self):
        return Qt.AlignLeft | Qt.AlignVCenter

    def summary_font(self, base):
        f = QFont(base)
        f.setBold(True)
        return f

    def summary_alignment(self):
        return Qt.AlignLeft | Qt.AlignVCenter

    def uses_text_color(self):
        """Whether summaries are drawn in the resolved title colour."""
        return True

    def watermark_lightness(self):
        return 170

    def configure_editor(self, editor, field_name, base_font):
        """Match an inline editor to how this style draws that field."""
        if field_name == Outline.summarySentence:
            base_font.setBold(True)
        elif field_name == Outline.title:
            base_font.setPointSize(base_font.pointSize() + 4)
            base_font.setBold(True)
        editor.setFont(base_font)

    # ------------------------------------------------------------------
    # Shared phases.

    @staticmethod
    def _color_group(ctx):
        state = ctx.option.state
        group = QPalette.ColorGroup(
            QPalette.Normal
            if state & QStyle.State_Enabled
            else QPalette.Disabled
        )
        if group == QPalette.Normal and not state & QStyle.State_Active:
            group = QPalette.Inactive
        return group

    def _draw_icon(self, p, ctx, layout):
        style = qApp.style()
        mode = QIcon.Normal
        if not ctx.option.state & style.State_Enabled:
            mode = QIcon.Disabled
        elif ctx.option.state & style.State_Selected:
            mode = QIcon.Selected
        decoration = ctx.index.data(Qt.DecorationRole)
        if decoration is None:
            return
        icon = decoration.pixmap(layout.icon.size())
        if ctx.shows("Icon"):
            colorifyPixmap(icon, ctx.color_for("Icon"))
        QIcon(icon).paint(
            p, layout.icon, ctx.option.decorationAlignment, mode)

    def _draw_title(self, p, ctx, layout):
        text = ctx.index.data()
        if not text:
            return
        p.save()
        p.setPen(Qt.black)
        ctx.text_color = QColor(Qt.black)
        if ctx.shows("Text"):
            col = ctx.color_for("Text")
            if col == Qt.transparent:
                col = Qt.black
            if ctx.view_setting("Text") == "Compile":
                # Otherwise an uncompiled title is invisible in some themes.
                col = (
                    self._mixed_with_background(ctx)
                    if ctx.item.compile() in [0, "0"]
                    else Qt.black
                )
            ctx.text_color = QColor(col)
            p.setPen(col)
        f = self.title_font(ctx.option.font)
        p.setFont(f)
        elided = QFontMetrics(f).elidedText(
            text, Qt.ElideRight, layout.title.width())
        p.drawText(layout.title, self.title_alignment(), elided)
        p.restore()

    @staticmethod
    def _mixed_with_background(ctx):
        from manuskript.functions import mixColors
        return mixColors(QColor(Qt.black), ctx.background)

    def _draw_status(self, p, ctx, layout):
        status = ctx.item.data(Outline.status)
        if not status:
            return
        entry = ctx.status_item(status)
        if entry is None:
            return
        rect = layout.body
        p.save()
        p.setClipRegion(QRegion(rect))
        f = p.font()
        f.setPointSize(f.pointSize() + 12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(Qt.red).lighter(self.watermark_lightness()))
        p.translate(rect.center())
        p.rotate(-35)
        p.translate(-rect.center())
        p.drawText(rect, Qt.AlignCenter, entry.text())
        p.restore()

    def _draw_summaries(self, p, ctx, layout):
        line = ctx.item.data(Outline.summarySentence)
        full = ctx.item.data(Outline.summaryFull)
        colored = not self.uses_text_color() or ctx.text_color is not None

        if line and colored:
            p.save()
            f = self.summary_font(ctx.option.font)
            p.setFont(f)
            if self.uses_text_color():
                p.setPen(ctx.text_color)
            elided = QFontMetrics(f).elidedText(
                line, Qt.ElideRight, layout.main_line.width())
            p.drawText(layout.main_line, self.summary_alignment(), elided)
            p.restore()

        if full and colored:
            p.save()
            p.setFont(ctx.option.font)
            if self.uses_text_color():
                p.setPen(ctx.text_color)
            p.drawText(layout.main_text, Qt.TextWordWrap, full)
            p.restore()

    @staticmethod
    def scaled(size, factor):
        return QSize(size) * factor
