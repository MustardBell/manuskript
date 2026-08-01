from unittest.mock import MagicMock

from manuskript.enums import Outline
from manuskript.ui.view_configuration import MainViewConfiguration
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
    return MainViewConfiguration(window), window, properties, outline


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
