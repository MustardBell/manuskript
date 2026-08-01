import pytest

from PyQt5.QtCore import QItemSelectionModel, QModelIndex
from PyQt5.QtWidgets import QVBoxLayout, QWidget, qApp

from manuskript.enums import Outline
from manuskript.models.outlineItem import outlineItem
from manuskript.plugins.api import (
    EditorWorkspaceContribution,
    ExtensionDescriptor,
)
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)


PLUGIN_ID = "example.variant-workspace"
CONTRIBUTION_ID = "example.variant-workspace.compare"


def _install_workspace(window, received, endpoint_box):
    def factory(context, parent):
        received.append(context)
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        endpoint = context.editors.create(
            context.selected_item_ids[0],
            parent=widget,
            editing_locked=True,
        )
        endpoint_box.append(endpoint)
        layout.addWidget(endpoint.widget)
        return widget

    registrar = window.pluginRuntime.registry.registrar(PLUGIN_ID)
    registrar.register_editor_workspace(
        EditorWorkspaceContribution(
            descriptor=ExtensionDescriptor(
                id=CONTRIBUTION_ID,
                name="Compare variants",
                description="Compare independently editable scene variants.",
            ),
            workspace_factory=factory,
            action_label="Open variant workspace",
            shortcut="Ctrl+Alt+V",
            minimum_selection=1,
            maximum_selection=5,
        )
    )
    window.pluginRuntime.registry.install(
        PLUGIN_ID,
        registrar.contributions,
    )
    window.pluginUi.refresh_contributions()


def _remove_workspace(window):
    window.pluginUi.editorWorkspaces.close_workspace()
    window.pluginRuntime.registry.remove_plugin(PLUGIN_ID)
    window.pluginUi.refresh_contributions()


def test_workspace_gets_guarded_project_capabilities(MWEmptyProject):
    window = MWEmptyProject
    received = []
    endpoints = []
    item = outlineItem(title="Original", _type="md")
    item.setData(Outline.text, "Original paragraph.")
    window.mdlOutline.appendItem(item)
    index = window.mdlOutline.indexFromItem(item)
    window.treeRedacOutline.selectionModel().setCurrentIndex(
        index,
        QItemSelectionModel.ClearAndSelect
        | QItemSelectionModel.Rows,
    )
    _install_workspace(window, received, endpoints)
    try:
        host = window.pluginUi.editorWorkspaces
        qApp.processEvents()
        assert host.actions[CONTRIBUTION_ID].isEnabled()

        shell = host.open_workspace(CONTRIBUTION_ID)
        qApp.processEvents()

        assert shell is not None
        assert window.mainEditor.pluginWorkspaceActive
        assert received[0].plugin_id == PLUGIN_ID
        assert received[0].selected_item_ids == (item.ID(),)
        assert received[0].outline.document(item.ID()).text == (
            "Original paragraph."
        )
        duplicate = received[0].outline.duplicate_text_document(
            item.ID(),
            title="Translation",
        )
        assert duplicate.title == "Translation"
        assert duplicate.text == "Original paragraph."
        assert not duplicate.compile
        assert window.mdlOutline.getItemByID(duplicate.id) is not None

        endpoint = endpoints[0]
        assert endpoint.editing_locked
        with pytest.raises(PermissionError):
            endpoint.insert_at_cursor("No")
        assert item.text() == "Original paragraph."

        endpoint.set_editing_locked(False)
        endpoint.replace_text(
            "Independent translation.\n\nSecond paragraph.\n\nThird."
        )
        assert item.text().startswith("Independent translation.")
        endpoint.set_presentation_mode(
            MarkdownPresentationMode.SOURCE
        )
        assert (
            endpoint.presentation.mode
            is MarkdownPresentationMode.SOURCE
        )

        endpoint.set_cursor_position(5, anchor=1)
        caret = endpoint.cursor_position
        selection = endpoint.selection_range()
        endpoint.scroll_to_block(2)
        endpoint.scroll_to_text_offset(len(endpoint.text()))
        assert endpoint.cursor_position == caret
        assert endpoint.selection_range() == selection
        assert endpoint.first_visible_block >= 0

        endpoint.set_maximum_text_width(520)
        assert endpoint.widget.effectiveMaximumWidth == 520
        endpoint.clear_maximum_text_width()
        assert endpoint.widget.effectiveMaximumWidth == (
            window.settingsManager.textEditor["maxWidth"]
            or endpoint.widget.maximumWidth()
        )

        received[0].files.write("groups.json", "{}")
        assert window.projectPluginData.namespace(PLUGIN_ID).read(
            "groups.json"
        ) == "{}"

        received[0].close_workspace()
        qApp.processEvents()
        assert not window.mainEditor.pluginWorkspaceActive
    finally:
        _remove_workspace(window)


def test_workspace_action_respects_selection_and_disable(MWEmptyProject):
    window = MWEmptyProject
    received = []
    endpoints = []
    _install_workspace(window, received, endpoints)
    try:
        window.treeRedacOutline.clearSelection()
        window.treeRedacOutline.setCurrentIndex(QModelIndex())
        window.pluginUi.editorWorkspaces._update_action_states()
        assert not window.pluginUi.editorWorkspaces.actions[
            CONTRIBUTION_ID
        ].isEnabled()

        window.pluginRuntime.registry.remove_plugin(PLUGIN_ID)
        window.pluginUi.refresh_contributions()
        assert window.pluginUi.editorWorkspaces.actions == {}
        assert not window.mainEditor.pluginWorkspaceActive
    finally:
        if window.pluginRuntime.registry.records("editor_workspace"):
            _remove_workspace(window)
