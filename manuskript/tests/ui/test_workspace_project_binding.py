from unittest.mock import MagicMock

from manuskript.ui.workspace_project_binding import (
    WorkspaceProjectBinding,
)


def test_connect_delegates_to_the_project_binding():
    binding = MagicMock()
    controller = WorkspaceProjectBinding(binding, MagicMock())

    controller.connect()

    binding.bind.assert_called_once_with()


def test_disconnect_releases_binding_and_markdown_state():
    binding = MagicMock()
    markdown_menu = MagicMock()
    controller = WorkspaceProjectBinding(binding, markdown_menu)

    controller.disconnect()

    binding.unbind.assert_called_once_with()
    markdown_menu.attach.assert_called_once_with(None)


def test_project_contexts_are_exposed_by_the_binding_that_owns_them():
    binding = MagicMock()
    controller = WorkspaceProjectBinding(binding, MagicMock())

    assert controller.reference_service is binding.reference_service
    assert controller.text_editor_context is binding.text_editor_context


def test_dispose_releases_collaborators_after_disconnect():
    binding = MagicMock()
    markdown_menu = MagicMock()
    controller = WorkspaceProjectBinding(binding, markdown_menu)

    controller.dispose()

    binding.unbind.assert_called_once_with()
    markdown_menu.attach.assert_called_once_with(None)
    assert controller._binding is None
    assert controller._markdown_menu is None
