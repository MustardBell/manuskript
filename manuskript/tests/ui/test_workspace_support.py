from unittest.mock import MagicMock

from manuskript.ui.workspace_support import (
    SUPPORT_URL,
    WorkspaceSupportController,
    WorkspaceSupportViews,
)


def _views(logfile=""):
    return WorkspaceSupportViews(
        translate=lambda value: value,
        show_information=MagicMock(return_value=True),
        show_critical=MagicMock(),
        open_url=MagicMock(),
        log_path=MagicMock(return_value=logfile),
        show_file=MagicMock(return_value=True),
    )


def test_support_opens_the_support_page():
    views = _views()
    WorkspaceSupportController(views).open_support()

    views.open_url.assert_called_once_with(SUPPORT_URL)


def test_missing_log_reports_that_logging_is_disabled():
    views = _views()
    WorkspaceSupportController(views).locate_log()

    title, message = views.show_information.call_args.args
    assert title == "Sorry!"
    assert "not being logged" in message
    views.show_file.assert_not_called()


def test_confirmed_log_is_opened_in_the_file_manager():
    views = _views("/tmp/manuskript.log")
    WorkspaceSupportController(views).locate_log()

    views.show_file.assert_called_once_with("/tmp/manuskript.log")
    views.show_critical.assert_not_called()


def test_file_manager_failure_reports_the_path():
    views = _views("/tmp/manuskript.log")
    views.show_file.return_value = False
    WorkspaceSupportController(views).locate_log()

    title, message = views.show_critical.call_args.args
    assert title == "Error!"
    assert "/tmp/manuskript.log" in message


def test_dispose_releases_support_capabilities():
    controller = WorkspaceSupportController(_views())

    controller.dispose()

    assert controller._views is None
