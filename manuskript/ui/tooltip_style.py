from PyQt5.QtGui import QColor, QPalette


MINIMUM_TEXT_CONTRAST = 4.5


def contrast_ratio(foreground, background):
    """Return the visible WCAG contrast of a foreground and background."""
    foreground = _composite_over(foreground, background)
    lighter = max(
        _relative_luminance(foreground),
        _relative_luminance(background),
    )
    darker = min(
        _relative_luminance(foreground),
        _relative_luminance(background),
    )
    return (lighter + 0.05) / (darker + 0.05)


def accessible_tooltip_palette(
        source_palette,
        minimum_contrast=MINIMUM_TEXT_CONTRAST):
    """Repair only an inaccessible tooltip foreground palette role."""
    palette = QPalette(source_palette)
    group = QPalette.Inactive
    background = palette.color(group, QPalette.ToolTipBase)
    foreground = palette.color(group, QPalette.ToolTipText)
    if contrast_ratio(foreground, background) >= minimum_contrast:
        return palette

    candidates = (
        palette.color(group, QPalette.Text),
        palette.color(group, QPalette.WindowText),
        QColor("black"),
        QColor("white"),
    )
    foreground = max(
        candidates,
        key=lambda color: contrast_ratio(color, background),
    )
    palette.setColor(group, QPalette.ToolTipText, foreground)
    return palette


def _relative_luminance(color):
    channels = (
        color.redF(),
        color.greenF(),
        color.blueF(),
    )
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return (
        0.2126 * linear[0]
        + 0.7152 * linear[1]
        + 0.0722 * linear[2]
    )


def _composite_over(foreground, background):
    alpha = foreground.alphaF()
    if alpha >= 1.0:
        return foreground
    inverse = 1.0 - alpha
    return QColor.fromRgbF(
        foreground.redF() * alpha + background.redF() * inverse,
        foreground.greenF() * alpha + background.greenF() * inverse,
        foreground.blueF() * alpha + background.blueF() * inverse,
    )
