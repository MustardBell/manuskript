from unittest.mock import MagicMock, patch


def test_close_event_is_ignored_when_project_close_is_cancelled(MW):
    event = MagicMock()

    with patch.object(MW.projectManager, "closeProject", return_value=False):
        MW.closeEvent(event)

    event.ignore.assert_called_once_with()
