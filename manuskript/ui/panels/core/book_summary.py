"""The Book summary panel: one summary text per zoom level.

Recreates exactly what the Designer file used to declare inside
``splitterPlot`` -- same widget classes, same objectNames, same
combo-to-stack wiring -- so saved layouts and every existing caller
find nothing changed except who did the building.
"""

from PyQt5.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from manuskript.ui.views.MDEditCompleter import MDEditCompleter


def build_book_summary(context, parent):
    window = context.window
    panel = QGroupBox(window.tr("Summary"), parent)
    panel.setObjectName("grpPlotSummary")
    layout = QVBoxLayout(panel)

    combo = QComboBox(panel)
    combo.setFrame(False)
    combo.setObjectName("comboBox_2")
    combo.addItem(window.tr("One paragraph"))
    combo.addItem(window.tr("One page"))
    combo.addItem(window.tr("Full"))
    layout.addWidget(combo)

    stack = QStackedWidget(panel)
    stack.setObjectName("stkPlotSummary")
    editors = {}
    for page_name, editor_name in (
        ("page", "txtPlotSummaryPara"),
        ("page_2", "txtPlotSummaryPage"),
        ("page_3", "txtPlotSummaryFull"),
    ):
        page = QWidget()
        page.setObjectName(page_name)
        page_layout = QHBoxLayout(page)
        editor = MDEditCompleter(page)
        editor.setObjectName(editor_name)
        page_layout.addWidget(editor)
        stack.addWidget(page)
        editors[editor_name] = editor
    layout.addWidget(stack)

    combo.currentIndexChanged.connect(stack.setCurrentIndex)

    # The rest of the window still reaches these by attribute; the
    # aliases retire as callers learn to ask the panel host instead.
    window.grpPlotSummary = panel
    window.comboBox_2 = combo
    window.stkPlotSummary = stack
    window.txtPlotSummaryPara = editors["txtPlotSummaryPara"]
    window.txtPlotSummaryPage = editors["txtPlotSummaryPage"]
    window.txtPlotSummaryFull = editors["txtPlotSummaryFull"]
    return panel
