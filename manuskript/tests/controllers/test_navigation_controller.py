from unittest.mock import MagicMock, call

from manuskript.controllers.navigation_controller import (
    NavigationController,
)


def test_navigation_controller_traverses_history_and_updates_actions():
    view = MagicMock()
    controller = NavigationController(view)

    controller.record(("character", "alice"))
    controller.record(("plot", "main"))
    controller.back()
    controller.forward()

    assert view.navigate.call_args_list == [
        call(("character", "alice")),
        call(("plot", "main")),
        call(("character", "alice")),
        call(("plot", "main")),
    ]
    view.set_history_actions.assert_called_with(
        can_go_back=True,
        can_go_forward=False,
    )


def test_navigation_controller_can_replace_empty_selection_entry():
    view = MagicMock()
    controller = NavigationController(view)

    controller.record(("character", None))
    controller.record(
        ("character", "alice"),
        replace=True,
    )
    controller.back()

    assert view.navigate.call_args_list == [
        call(("character", None)),
        call(("character", "alice")),
    ]


def test_navigation_controller_dispose_releases_history_callback_and_view():
    view = MagicMock()
    controller = NavigationController(view)

    assert controller.history.navigated._methods == [controller.navigated]

    controller.dispose()

    assert controller.history.navigated._methods == []
    assert controller.view is None


def test_dispose_preserves_other_history_observers():
    view = MagicMock()
    observer = MagicMock()
    controller = NavigationController(view)
    controller.history.navigated.connect(observer)

    controller.dispose()
    controller.history.next(("main", 1))

    observer.assert_called_once()
    view.navigate.assert_not_called()
