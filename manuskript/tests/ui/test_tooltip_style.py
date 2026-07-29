import pytest
from PyQt5.QtGui import QColor, QPalette

from manuskript.ui.tooltip_style import (
    MINIMUM_TEXT_CONTRAST,
    accessible_tooltip_palette,
    contrast_ratio,
)


def tooltip_palette(text, background):
    palette = QPalette()
    palette.setColor(
        QPalette.Inactive,
        QPalette.ToolTipText,
        QColor(text),
    )
    palette.setColor(
        QPalette.Inactive,
        QPalette.ToolTipBase,
        QColor(background),
    )
    return palette


def test_contrast_ratio_matches_wcag_reference_values():
    assert contrast_ratio(
        QColor("black"),
        QColor("white"),
    ) == pytest.approx(21.0)


def test_inaccessible_linux_tooltip_palette_is_repaired():
    source = tooltip_palette("#ffffff", "#ffffdc")

    repaired = accessible_tooltip_palette(source)

    assert repaired.color(
        QPalette.Inactive,
        QPalette.ToolTipBase,
    ) == QColor("#ffffdc")
    assert repaired.color(
        QPalette.Inactive,
        QPalette.ToolTipText,
    ) == QColor("black")
    assert contrast_ratio(
        repaired.color(QPalette.Inactive, QPalette.ToolTipText),
        repaired.color(QPalette.Inactive, QPalette.ToolTipBase),
    ) >= MINIMUM_TEXT_CONTRAST


def test_accessible_system_tooltip_palette_is_unchanged():
    source = tooltip_palette("#202020", "#ffffdc")

    repaired = accessible_tooltip_palette(source)

    assert repaired.color(
        QPalette.Inactive,
        QPalette.ToolTipText,
    ) == QColor("#202020")
    assert repaired.color(
        QPalette.Inactive,
        QPalette.ToolTipBase,
    ) == QColor("#ffffdc")
