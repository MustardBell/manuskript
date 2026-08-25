from unittest.mock import MagicMock

from manuskript.panels.core import (
    CHARACTER_ENTITIES,
    OUTLINE,
    PLOT_ENTITIES,
)
from manuskript.ui.navigation_view import MainNavigationView, NavigationViews


def make_views():
    surfaces = {
        CHARACTER_ENTITIES: MagicMock(),
        PLOT_ENTITIES: MagicMock(),
        "core.entities.world": MagicMock(),
        OUTLINE: MagicMock(),
    }
    return NavigationViews(
        activate_panel=MagicMock(return_value=True),
        surface_widget=surfaces.get,
        outline_selection=MagicMock(),
        back_action=MagicMock(),
        forward_action=MagicMock(),
    )


def test_plot_navigation_reveals_catalogue_and_selects_entity():
    views = make_views()
    panel = views.surface_widget(PLOT_ENTITIES)
    panel.select_entity.return_value = True
    view = MainNavigationView(views, MagicMock())

    view.navigate(("plot", "plot-1"))

    views.activate_panel.assert_called_once_with(PLOT_ENTITIES)
    panel.select_entity.assert_called_once_with("plot-1")


def test_outline_navigation_selects_target_from_invalid_selection():
    views = make_views()
    runtime = MagicMock()
    outline = views.surface_widget(OUTLINE).treeOutlineOutline
    current = outline.selectionModel().currentIndex()
    current.isValid.return_value = False
    target = MagicMock()
    runtime.models.outline.getIndexByID.return_value = target
    view = MainNavigationView(views, runtime)

    view.navigate(("outline", "scene-1"))

    views.activate_panel.assert_called_once_with(OUTLINE)
    outline.setCurrentIndex.assert_called_once_with(target)


def test_character_navigation_clears_selection_for_empty_target():
    views = make_views()
    view = MainNavigationView(views, MagicMock())

    view.navigate(("character", None))

    views.activate_panel.assert_called_once_with(CHARACTER_ENTITIES)
    panel = views.surface_widget(CHARACTER_ENTITIES)
    panel.tree.setCurrentItem.assert_called_once_with(None)
    panel.tree.clearSelection.assert_called_once()


def test_navigation_view_updates_history_actions():
    views = make_views()
    view = MainNavigationView(views, MagicMock())

    view.set_history_actions(can_go_back=True, can_go_forward=False)

    views.back_action.setEnabled.assert_called_once_with(True)
    views.forward_action.setEnabled.assert_called_once_with(False)


def test_navigation_uses_the_replacement_project_models():
    views = make_views()
    runtime = MagicMock()
    view = MainNavigationView(views, runtime)
    outline = views.surface_widget(OUTLINE).treeOutlineOutline
    current = outline.selectionModel().currentIndex()
    current.isValid.return_value = False
    first = runtime.models
    first.outline.getIndexByID.return_value = MagicMock()

    view.navigate(("outline", "first"))
    replacement = MagicMock()
    replacement.outline.getIndexByID.return_value = MagicMock()
    runtime.models = replacement
    view.navigate(("outline", "second"))

    first.outline.getIndexByID.assert_called_once_with("first")
    replacement.outline.getIndexByID.assert_called_once_with("second")


def test_navigation_does_not_recreate_or_use_an_absent_surface():
    views = make_views()
    views.activate_panel.return_value = False
    view = MainNavigationView(views, MagicMock())

    view.navigate(("outline", "scene-1"))

    views.activate_panel.assert_called_once_with(OUTLINE)


def test_navigation_view_has_no_main_window_escape_hatch():
    views = MagicMock()
    view = MainNavigationView(views, MagicMock())

    assert view.views is views
    assert not hasattr(view, "window")
