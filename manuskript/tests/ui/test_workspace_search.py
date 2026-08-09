from unittest.mock import MagicMock

from manuskript.ui.workspace_search import WorkspaceSearchController


def test_show_reveals_search_and_selects_the_existing_query():
    views = MagicMock()
    controller = WorkspaceSearchController(views)

    controller.show()

    views.dock.show.assert_called_once_with()
    views.dock.activateWindow.assert_called_once_with()
    views.query.setFocus.assert_called_once_with()
    views.query.selectAll.assert_called_once_with()


def test_dispose_releases_search_widgets():
    controller = WorkspaceSearchController(MagicMock())

    controller.dispose()

    assert controller._views is None


def test_search_action_focuses_the_real_workspace_query(MWEmptyProject):
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import qApp

    window = MWEmptyProject
    was_visible = window.isVisible()
    window.show()
    window.raise_()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window)
    query = window.widget.searchTextInput
    query.setText("selected query")
    window.actSearch.trigger()
    qApp.processEvents()
    try:
        assert window.dckSearch.isVisible()
        assert query.hasFocus()
        assert query.selectedText() == "selected query"
    finally:
        window.dckSearch.hide()
        if not was_visible:
            window.hide()
