from PyQt5.QtWidgets import QWidget

from manuskript.ui.workspace_dialogs import (
    ApplicationDialogFactories,
    AuthoringDialogFactories,
    WorkspaceDialogController,
    WorkspaceDialogViews,
)


class SettingsDialog(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.tabs = []

    def setTab(self, tab):
        self.tabs.append(tab)


def controller_fixture(project_open=True):
    parent = QWidget()
    centered = []
    created = {}

    def create(name, widget_type=QWidget):
        dialog = widget_type(parent)
        created.setdefault(name, []).append(dialog)
        return dialog

    views = WorkspaceDialogViews(
        dialog_parent=parent,
        center=centered.append,
        authoring=AuthoringDialogFactories(
            settings=lambda: create("settings", SettingsDialog),
            frequency=lambda: create("frequency"),
            targets=lambda: create("targets"),
            revisions=lambda host: QWidget(host),
            upgrade=lambda: create("upgrade"),
            project_is_open=lambda: project_open,
        ),
        application=ApplicationDialogFactories(
            media_types=lambda: create("media-types"),
            about=lambda: create("about"),
        ),
    )
    return WorkspaceDialogController(views), parent, centered, created


def test_settings_lifecycle_replaces_the_previous_dialog_cleanly():
    controller, _parent, centered, created = controller_fixture()

    first = controller.show_settings("General")
    second = controller.show_settings(3)

    assert first is not second
    assert first.isHidden()
    assert second.tabs == [3]
    assert controller.settings_dialog is second
    assert centered == [first, second]
    assert len(created["settings"]) == 2
    assert not hasattr(controller, "window")
    assert not hasattr(controller, "mw")
    controller.close_all()


def test_settings_action_checked_argument_is_not_a_page_index():
    controller, _parent, _centered, _created = controller_fixture()

    dialog = controller.show_settings(False)

    assert dialog.tabs == []
    controller.close_all()


def test_revision_history_is_singleton_and_can_follow_modal_settings():
    controller, parent, _centered, _created = controller_fixture()

    first = controller.show_revision_history()
    modal_host = QWidget(parent)
    second = controller.show_revision_history(modal_host)

    assert first is second
    assert second.parentWidget() is modal_host
    assert controller.revision_dialog is second
    controller.close_all()


def test_revision_history_is_not_created_without_an_open_project():
    controller, _parent, _centered, _created = controller_fixture(
        project_open=False
    )

    assert controller.show_revision_history() is None
    assert controller.revision_dialog is None


def test_upgrade_dialog_is_project_scoped():
    controller, _parent, _centered, created = controller_fixture()

    dialog = controller.show_upgrade()

    assert dialog is created["upgrade"][0]
    controller.close_all()

    closed, _parent, _centered, _created = controller_fixture(False)
    assert closed.show_upgrade() is None


def test_close_all_forgets_and_closes_every_workspace_tool():
    controller, _parent, _centered, _created = controller_fixture()
    dialogs = (
        controller.show_frequency(),
        controller.show_targets(),
        controller.show_media_types(),
        controller.show_about(),
    )

    controller.close_all()

    assert all(dialog.isHidden() for dialog in dialogs)
    assert controller.frequency_dialog is None
    assert controller.targets_dialog is None
    assert controller.media_type_dialog is None
    assert controller.about_dialog is None
