from unittest.mock import MagicMock

from manuskript.ui.navigation_view import MainNavigationView


def make_window():
    window = MagicMock()
    window.TabPersos = 2
    window.TabPlots = 3
    window.TabWorld = 4
    window.TabOutline = 5
    window.TabRedac = 6
    return window


def test_plot_navigation_does_not_reselect_current_plot():
    window = make_window()
    window.tabMain.currentIndex.return_value = window.TabPlots
    window.lstPlots.currentPlotID.return_value = "plot-1"
    view = MainNavigationView(window)

    view.navigate(("plot", "plot-1"))

    window.lstPlots.getItemByID.assert_not_called()
    window.lstPlots.setCurrentItem.assert_not_called()


def test_outline_navigation_selects_target_from_invalid_selection():
    window = make_window()
    current = MagicMock()
    current.isValid.return_value = False
    window.treeOutlineOutline.selectionModel.return_value.currentIndex.return_value = current
    target = MagicMock()
    window.mdlOutline.getIndexByID.return_value = target
    view = MainNavigationView(window)

    view.navigate(("outline", "scene-1"))

    window.tabMain.setCurrentIndex.assert_called_once_with(
        window.TabOutline
    )
    window.treeOutlineOutline.setCurrentIndex.assert_called_once_with(
        target
    )


def test_character_navigation_clears_selection_for_empty_target():
    window = make_window()
    view = MainNavigationView(window)

    view.navigate(("character", None))

    window.lstCharacters.setCurrentItem.assert_called_once_with(None)
    window.lstCharacters.clearSelection.assert_called_once_with()


def test_navigation_view_updates_history_actions():
    window = make_window()
    view = MainNavigationView(window)

    view.set_history_actions(
        can_go_back=True,
        can_go_forward=False,
    )

    window.actBack.setEnabled.assert_called_once_with(True)
    window.actForward.setEnabled.assert_called_once_with(False)
