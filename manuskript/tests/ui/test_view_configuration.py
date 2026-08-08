from unittest.mock import MagicMock

from manuskript.enums import Outline
from manuskript.ui.view_configuration import (
    MainViewConfiguration,
    ViewConfigurationViews,
    ViewSettingsMenuBuilder,
    ViewSettingsMenuViews,
)
from manuskript.ui.views.outlineView import outlineView
from manuskript.ui.views.propertiesView import propertiesView


def make_view():
    window = MagicMock()
    properties = MagicMock()
    outline = MagicMock()

    def find_children(widget_type):
        if widget_type is propertiesView:
            return [properties]
        if widget_type is outlineView:
            return [outline]
        return []

    window.findChildren.side_effect = find_children
    return (
        MainViewConfiguration(ViewConfigurationViews.for_window(window)),
        window,
        properties,
        outline,
    )


def test_simple_mode_suppresses_pov_without_changing_settings():
    view, window, properties, outline = make_view()
    window.settingsManager.outlineViewColumns = [
        Outline.title,
        Outline.POV,
    ]
    original_columns = list(window.settingsManager.outlineViewColumns)

    view.set_fiction_features_visible(False)

    window.toolbar.setDockVisibility.assert_called_once_with(
        window.dckNavigation,
        False,
    )
    properties.lblPOV.setVisible.assert_called_once_with(False)
    properties.cmbPOV.setVisible.assert_called_once_with(False)
    outline.hideColumns.assert_called_once_with()
    outline.hideColumn.assert_called_once_with(Outline.POV)
    assert list(window.settingsManager.outlineViewColumns) == original_columns


def test_fiction_mode_reapplies_saved_outline_columns():
    view, _window, properties, outline = make_view()

    view.set_fiction_features_visible(True)

    properties.lblPOV.setVisible.assert_called_once_with(True)
    outline.hideColumns.assert_called_once_with()
    outline.hideColumn.assert_not_called()


def test_view_configuration_has_no_main_window_escape_hatch():
    configuration = MainViewConfiguration(MagicMock())
    menu_builder = ViewSettingsMenuBuilder(MagicMock(), MagicMock())

    assert not hasattr(configuration, "window")
    assert not hasattr(menu_builder, "window")


def test_menu_views_expose_only_menu_building_capabilities():
    window = MagicMock()

    views = ViewSettingsMenuViews.for_window(window)

    assert views.menu is window.menuView
    assert views.mode_menu is window.menuMode
    assert views.markdown_menu is window.menuMarkdownMode
    assert views.translate is window.tr
