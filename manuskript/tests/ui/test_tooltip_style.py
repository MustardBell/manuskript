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


def assert_same_color(actual, expected):
    """Compare rendered channels, not Qt's platform-specific color spec."""
    assert actual.rgba() == QColor(expected).rgba()


def test_contrast_ratio_matches_wcag_reference_values():
    assert contrast_ratio(
        QColor("black"),
        QColor("white"),
    ) == pytest.approx(21.0)


def test_contrast_ratio_accounts_for_foreground_opacity():
    transparent_black = QColor("black")
    transparent_black.setAlpha(0)

    assert contrast_ratio(
        transparent_black,
        QColor("white"),
    ) == pytest.approx(1.0)


def test_inaccessible_tooltip_palette_is_repaired():
    source = tooltip_palette("#ffffff", "#ffffdc")

    repaired = accessible_tooltip_palette(source)

    assert_same_color(repaired.color(
        QPalette.Inactive,
        QPalette.ToolTipBase,
    ), "#ffffdc")
    assert_same_color(repaired.color(
        QPalette.Inactive,
        QPalette.ToolTipText,
    ), "black")
    assert contrast_ratio(
        repaired.color(QPalette.Inactive, QPalette.ToolTipText),
        repaired.color(QPalette.Inactive, QPalette.ToolTipBase),
    ) >= MINIMUM_TEXT_CONTRAST


def test_accessible_system_tooltip_palette_is_unchanged():
    source = tooltip_palette("#202020", "#ffffdc")

    repaired = accessible_tooltip_palette(source)

    assert_same_color(repaired.color(
        QPalette.Inactive,
        QPalette.ToolTipText,
    ), "#202020")
    assert_same_color(repaired.color(
        QPalette.Inactive,
        QPalette.ToolTipBase,
    ), "#ffffdc")
