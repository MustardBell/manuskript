"""Every navigation entry names its icon the same way.

The navigator draws core panels and plugin panels from one list, so an icon
name is part of that list's vocabulary rather than each panel's private
business.  This stays Qt-free: it checks the vocabulary, not what a theme
happens to hold, which is the part that regressed.
"""

from manuskript.functions import themeIcon
from manuskript.panels.core import core_panel_descriptors


def navigator_icons():
    return tuple(
        descriptor.navigator.icon
        for descriptor in core_panel_descriptors()
        if descriptor.navigator is not None
    )


def test_every_core_panel_offers_the_navigator_an_icon():
    icons = navigator_icons()

    assert icons
    assert all(icons)


def test_core_panels_name_icons_semantically_rather_than_by_theme():
    """General, Summary and Editor once named raw theme icons.

    themeIcon answered those with nothing, so three entries in the
    navigator lost their icons while their neighbours kept theirs. The
    names are what tell the two categories apart, so the names are what
    this checks.
    """

    for icon in navigator_icons():
        assert icon.islower(), icon
        assert "-" not in icon, icon
        assert "_" not in icon, icon


def test_an_unknown_icon_name_still_reaches_the_theme():
    """A plugin cannot add a line to the semantic table.

    Returning a blank icon for a name the table does not hold loses
    silently, so an unrecognised name is passed to the theme as given.
    """

    assert themeIcon("vendor.unknown-icon") is not None
