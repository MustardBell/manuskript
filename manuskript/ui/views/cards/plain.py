"""Flat index card: no border chrome, a folder tab, a corner label flag."""

from PyQt5.QtCore import QPoint, QPointF, QRect, QSize, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPolygonF

from manuskript.enums import Outline
from manuskript.functions import mixColors
from manuskript.ui.views.cards.base import CardLayout, IndexCardStyle


class PlainCardStyle(IndexCardStyle):
    id = "manuskript.card.plain"
    name = "Plain card"

    def size_hint(self, factor):
        return self.scaled(QSize(300, 210), factor)

    def layout(self, ctx):
        margin = int(ctx.margin * 2)
        icon_size = int(max(24 * ctx.factor, 18))
        fm = QFontMetrics(ctx.option.font)
        line_height = int(fm.lineSpacing())

        item = ctx.option.rect.adjusted(margin, margin, -margin, -margin)
        top_height = int(15 * ctx.factor)
        top = QRect(item)
        top.setHeight(top_height)

        card = QRect(
            item.topLeft() + QPoint(0, top_height), item.bottomRight())
        icon = QRect(
            card.topLeft() + QPoint(margin, margin),
            QSize(icon_size, icon_size))
        label = QRect(
            card.topRight() - QPoint(int(margin + ctx.factor * 18), 1),
            card.topRight() + QPoint(
                int(-margin - ctx.factor * 4), int(ctx.factor * 24)))
        title = QRect(
            icon.topRight() + QPoint(margin, 0),
            label.bottomLeft() - QPoint(margin, margin))
        title.setBottom(icon.bottom())
        main = QRect(
            icon.bottomLeft() + QPoint(0, margin),
            card.bottomRight() - QPoint(margin, 2 * margin))
        main.setLeft(title.left())
        main_line = QRect(
            main.topLeft(), main.topRight() + QPoint(0, line_height))
        main_text = QRect(
            main_line.bottomLeft() + QPoint(0, margin), main.bottomRight())
        if not ctx.item.data(Outline.summarySentence):
            main_text.setTopLeft(main_line.topLeft())

        # With no corner flag the title may run the full width.
        if not ctx.shows("Corner") or ctx.color_for("Corner") == Qt.transparent:
            title.setRight(main.right())

        return CardLayout(
            item=item, top=top, card=card, icon=icon, label=label,
            title=title, main=main, main_line=main_line,
            main_text=main_text)

    def draw_chrome(self, p, ctx, layout):
        p.save()
        if ctx.shows("Background"):
            c = ctx.color_for("Background")
            if c == QColor(Qt.transparent):
                c = QColor(Qt.white)
            ctx.background = mixColors(c, QColor(Qt.white), .2)
        else:
            ctx.background = QColor(Qt.white)
        p.setBrush(ctx.background)
        ctx.bg_colors[ctx.index] = ctx.background.name()

        p.setPen(Qt.NoPen)
        p.drawRect(layout.card)
        if ctx.item.isFolder():
            width = layout.top.width()
            ctx.folder_polygon = QPolygonF([
                layout.top.topLeft(),
                layout.top.topLeft() + QPoint(int(width * .35), 0),
                layout.card.topLeft() + QPoint(int(width * .45), 0),
                layout.card.topRight(),
                layout.card.bottomRight(),
                layout.card.bottomLeft(),
            ])
            p.drawPolygon(ctx.folder_polygon)
        p.restore()

    def draw_label_corner(self, p, ctx, layout):
        if not ctx.shows("Corner"):
            return
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(ctx.color_for("Corner"))
        p.drawRect(layout.label)
        w = layout.label.width()
        p.drawPolygon(QPolygonF([
            layout.label.bottomLeft() + QPointF(0, 1),
            layout.label.bottomLeft() + QPointF(0, w / 2),
            layout.label.bottomLeft() + QPointF(w / 2, 1),
            layout.label.bottomRight() + QPointF(1, w / 2),
            layout.label.bottomRight() + QPointF(1, 1),
        ]))
        p.restore()

    def draw_border(self, p, ctx, layout):
        if not ctx.shows("Border"):
            return
        p.save()
        p.setBrush(Qt.NoBrush)
        pen = p.pen()
        pen.setWidth(2)
        pen.setColor(ctx.color_for("Border"))
        p.setPen(pen)
        if ctx.item.isFolder() and ctx.folder_polygon is not None:
            p.drawPolygon(ctx.folder_polygon)
        else:
            p.drawRect(layout.card)
        p.restore()

    def title_font(self, base):
        f = QFont(base)
        f.setPointSize(f.pointSize() + 4)
        f.setBold(True)
        return f
