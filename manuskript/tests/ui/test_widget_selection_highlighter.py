from PyQt5.QtGui import QColor, QFocusEvent, QPalette
from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QLabel

from manuskript.ui.highlighters.searchResultHighlighters.widgetSelectionHighlighter import (
    widgetSelectionHighlighter,
)


def test_label_highlight_preserves_stylesheet_and_restores_palette():
    label = QLabel("Result")
    label.setStyleSheet("font-weight: bold; color: green")
    original_palette = label.palette()
    original_autofill = label.autoFillBackground()
    highlighter = widgetSelectionHighlighter()

    highlighter._highlightLabelSearchResult(
        label,
        clearOnFocusOut=True,
    )

    assert label.styleSheet() == "font-weight: bold; color: green"
    assert label.autoFillBackground()
    assert label.palette().color(QPalette.Window) == QColor("steelblue")

    label.focusOutEvent(QFocusEvent(QEvent.FocusOut))

    assert label.styleSheet() == "font-weight: bold; color: green"
    assert label.palette() == original_palette
    assert label.autoFillBackground() == original_autofill
