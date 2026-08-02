"""Ruled index card: rounded border, coloured title bar, notebook rules."""

from PyQt5.QtCore import QPoint, QRect, QSize, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QRegion

from manuskript.enums import Outline
from manuskript.functions import mixColors
from manuskript.ui.views.cards.base import CardLayout, IndexCardStyle


CORNER_RADIUS = 10
RULE_COLOR = "#EEE"


class RuledCardStyle(IndexCardStyle):
    id = "manuskript.card.ruled"
    name = "Ruled index card"

    def size_hint(self, factor):
        return self.scaled(QSize(300, 200), factor)

    def layout(self, ctx):
        margin = int(ctx.margin)
        icon_size = int(max(16 * ctx.factor, 12))

        item = ctx.option.rect.adjusted(margin, margin, -margin, -margin)
        icon = QRect(
            item.topLeft() + QPoint(margin, margin),
            QSize(icon_size, icon_size))
        label = QRect(
            item.topRight() - QPoint(icon_size + margin, 0),
            item.topRight() + QPoint(0, icon_size + 2 * margin))
        title = QRect(
            icon.topRight() + QPoint(margin, 0),
            label.bottomLeft() - QPoint(margin, margin))
        bottom = QRect(
            QPoint(item.x(), icon.bottom() + margin),
            QPoint(item.right(), item.bottom()))
        top = QRect(item.topLeft(), bottom.topRight())
        main = bottom.adjusted(margin, margin, -margin, -margin)
        main_line = QRect(
            main.topLeft(), main.topRight() + QPoint(0, icon_size))
        main_text = QRect(
            main_line.bottomLeft() + QPoint(0, margin), main.bottomRight())
        if not ctx.item.data(Outline.summarySentence):
            main_text.setTopLeft(main_line.topLeft())
        if ctx.item.data(Outline.label) in ["", "0", 0]:
            title.setBottomRight(
                label.bottomRight() - QPoint(ctx.margin, ctx.margin))

        return CardLayout(
            item=item, top=top, bottom=bottom, icon=icon, label=label,
            title=title, main=main, main_line=main_line,
            main_text=main_text)

    def fill_selection(self, p, ctx, layout):
        p.drawRoundedRect(ctx.option.rect, 12, 12)

    def draw_chrome(self, p, ctx, layout):
        # A folder with children sits on a small stack of blank cards.
        if ctx.item.isFolder() and ctx.item.childCount() > 0:
            p.save()
            p.setBrush(Qt.white)
            for offset in reversed(range(3)):
                p.drawRoundedRect(
                    layout.item.adjusted(
                        2 * offset, 2 * offset, -2 * offset, 2 * offset),
                    CORNER_RADIUS, CORNER_RADIUS)
            p.restore()

        p.save()
        if ctx.shows("Background"):
            ctx.background = mixColors(
                ctx.color_for("Background"), QColor(Qt.white), .2)
        else:
            ctx.background = QColor(Qt.white)
        p.setBrush(ctx.background)
        ctx.bg_colors[ctx.index] = ctx.background.name()
        pen = p.pen()
        pen.setWidth(2)
        p.setPen(pen)
        p.drawRoundedRect(layout.item, CORNER_RADIUS, CORNER_RADIUS)
        p.restore()

        # Title bar, clipped so only the rounded top shows.
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(
            QColor(Qt.darkGreen)
            if ctx.item.isFolder()
            else QColor(Qt.blue).lighter(175))
        p.setClipRegion(QRegion(layout.top))
        p.drawRoundedRect(layout.item, CORNER_RADIUS, CORNER_RADIUS)
        p.restore()

    def draw_label_corner(self, p, ctx, layout):
        if not ctx.shows("Corner"):
            return
        color = ctx.color_for("Corner")
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.setClipRegion(QRegion(layout.label))
        p.drawRoundedRect(layout.item, CORNER_RADIUS, CORNER_RADIUS)
        p.restore()
        if color != Qt.transparent:
            p.drawLine(layout.label.topLeft(), layout.label.bottomLeft())

    def draw_summary_backdrop(self, p, ctx, layout):
        line = ctx.item.data(Outline.summarySentence)
        full = ctx.item.data(Outline.summaryFull)
        if not (line or not full):
            return
        m = ctx.margin
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(RULE_COLOR))
        p.drawRect(layout.main_line.adjusted(-m, -m, m, int(m / 2)))
        p.restore()

    def draw_border(self, p, ctx, layout):
        p.save()
        p.setBrush(Qt.NoBrush)
        pen = p.pen()
        pen.setWidth(2)
        if ctx.shows("Border"):
            col = ctx.color_for("Border")
            if col == Qt.transparent:
                col = Qt.black
            pen.setColor(col)
        p.setPen(pen)
        p.drawRoundedRect(layout.item, CORNER_RADIUS, CORNER_RADIUS)
        p.restore()

    def draw_overlay(self, p, ctx, layout):
        # Divider under the title bar.
        p.save()
        p.drawLine(layout.bottom.topLeft(), layout.bottom.topRight())
        p.restore()

        # Notebook rules across the body.
        p.save()
        p.setPen(QColor(RULE_COLOR))
        height = QFontMetrics(ctx.option.font).lineSpacing()
        cursor = layout.main_text.topLeft() + QPoint(0, height)
        while layout.main_text.contains(cursor):
            p.drawLine(
                cursor, QPoint(layout.main_text.right(), cursor.y()))
            cursor.setY(cursor.y() + height)
        p.restore()

    def title_alignment(self):
        return Qt.AlignCenter

    def summary_font(self, base):
        f = QFont(base)
        f.setItalic(True)
        return f

    def summary_alignment(self):
        return Qt.AlignCenter

    def uses_text_color(self):
        # Ruled cards draw summaries in the painter's inherited pen.
        return False

    def watermark_lightness(self):
        return 175

    def configure_editor(self, editor, field_name, base_font):
        if field_name == Outline.summarySentence:
            base_font.setItalic(True)
            editor.setAlignment(Qt.AlignCenter)
        elif field_name == Outline.title:
            base_font.setBold(True)
            editor.setAlignment(Qt.AlignCenter)
        editor.setFont(base_font)
