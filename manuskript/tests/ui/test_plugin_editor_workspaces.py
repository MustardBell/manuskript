from pathlib import Path

import pytest

from PyQt5.QtCore import QItemSelectionModel, QModelIndex
from PyQt5.QtWidgets import QVBoxLayout, QWidget, qApp

from manuskript.enums import Outline
from manuskript.models.outlineItem import outlineItem
from manuskript.plugins.api import (
    EditorWorkspaceContribution,
    ExtensionDescriptor,
)
from manuskript.plugins.capabilities import (
    CAPABILITY_EDITOR_CONTROL,
    CAPABILITY_OUTLINE_READ,
    CAPABILITY_OUTLINE_WRITE,
    CAPABILITY_QUERY_EXECUTE,
)
from manuskript.plugins.errors import PluginScopeError
from manuskript.plugins import All, QueryScope
from manuskript.plugins.manifest import (
    PluginManifest,
    ProjectFormatCompatibility,
)
from manuskript.plugins.runtimes import PythonRuntime
from manuskript.plugins.runtime import PluginRecord, PluginStatus
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)
from manuskript.ui.plugins.editor_workspaces import _discard_endpoint


PLUGIN_ID = "example.variant-workspace"
CONTRIBUTION_ID = "example.variant-workspace.compare"


def test_editor_workspace_host_has_no_main_window_service_locator(
        MWEmptyProject):
    host = MWEmptyProject.pluginUi.editorWorkspaces

    assert not hasattr(host, "window")
    assert not hasattr(host.views, "window")


def test_endpoint_destruction_cleanup_needs_no_live_qobject_owner():
    """Late QWidget destruction operates on plain state, not a dead factory."""
    endpoint = object()
    endpoints = [endpoint]

    _discard_endpoint(endpoints, endpoint)

    assert endpoints == []


def _declare(window, requires):
    """Give the test plugin a manifest, as a loaded plugin has.

    Contributions arrive from loaded plugins, and what a plugin may touch
    is read from the manifest it was loaded with. A test that installs
    contributions straight into the registry has to supply one too, or it
    is exercising a plugin core has never heard of.
    """
    window.pluginRuntime.records[PLUGIN_ID] = PluginRecord(
        manifest=PluginManifest(
            id=PLUGIN_ID,
            name="Variant workspace",
            version="1.0.0",
            api_version=1,
            runtime=PythonRuntime("plugin", "register"),
            root=Path("."),
            project_formats=ProjectFormatCompatibility(0, 2),
            requires=tuple(requires),
        ),
        status=PluginStatus.LOADED,
    )


def _install_workspace(
        window, received, endpoint_box,
        requires=(CAPABILITY_OUTLINE_WRITE, CAPABILITY_EDITOR_CONTROL)):
    def factory(context, parent):
        received.append(context)
        class TestWorkspace(QWidget):
            def prepare_close(self):
                self.prepared = True

        widget = TestWorkspace(parent)
        widget.prepared = False
        layout = QVBoxLayout(widget)
        endpoint = context.editors.create(
            context.selected_item_ids[0],
            parent=widget,
            editing_locked=True,
        )
        endpoint_box.append(endpoint)
        layout.addWidget(endpoint.widget)
        return widget

    _declare(window, requires)
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
    window.pluginRuntime.records.pop(PLUGIN_ID, None)
    window.pluginUi.refresh_contributions()


def test_workspace_gets_guarded_project_capabilities(MWEmptyProject):
    window = MWEmptyProject
    received = []
    endpoints = []
    item = outlineItem(title="Original", _type="md")
    item.setData(Outline.text, "Original paragraph.")
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)
    window.corePanels.project_tree.tree.selectionModel().setCurrentIndex(
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
        assert window.projectRuntime.models.outline.getItemByID(duplicate.id) is not None

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

        # Where a pane sits between two paragraphs, so a workspace can carry
        # a scroll across without rounding it to the nearest paragraph.
        tops = [
            endpoint.scroll_value_for_block(number)
            for number in range(endpoint.block_count)
        ]
        assert tops == sorted(tops)
        assert tops[1] <= endpoint.scroll_value_for_block(1, 0.5) <= tops[2]
        assert endpoint.scroll_value_for_block(-5) == tops[0]
        assert endpoint.scroll_value_for_block(9999) == tops[-1]
        assert endpoint.scroll_value_for_text_offset(0) == tops[0]
        assert 0.0 <= endpoint.first_visible_block_fraction <= 1.0

        endpoint.set_maximum_text_width(520)
        assert endpoint.widget.effectiveMaximumWidth == 520
        endpoint.clear_maximum_text_width()
        assert endpoint.widget.effectiveMaximumWidth == (
            window.projectRuntime.settingsManager.textEditor["maxWidth"]
            or endpoint.widget.maximumWidth()
        )

        received[0].files.write("groups.json", "{}")
        assert window.projectRuntime.models.plugin_data.namespace(PLUGIN_ID).read(
            "groups.json"
        ) == "{}"

        received[0].close_workspace()
        qApp.processEvents()
        assert shell.workspace.prepared
        assert not window.mainEditor.pluginWorkspaceActive
    finally:
        _remove_workspace(window)


def _open_with(window, requires):
    """Open a workspace declaring ``requires``, and answer with its context.

    The factory here reaches for nothing, so what a plugin was granted can
    be looked at without a workspace that would fall over without it.
    """
    received = []

    def factory(context, parent):
        received.append(context)
        return QWidget(parent)

    item = outlineItem(title="Scene", _type="md")
    item.setData(Outline.text, "A paragraph.")
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)
    window.corePanels.project_tree.tree.selectionModel().setCurrentIndex(
        index,
        QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
    )
    _declare(window, requires)
    registrar = window.pluginRuntime.registry.registrar(PLUGIN_ID)
    registrar.register_editor_workspace(
        EditorWorkspaceContribution(
            descriptor=ExtensionDescriptor(
                id=CONTRIBUTION_ID,
                name="Compare variants",
                description="Compare scene variants.",
            ),
            workspace_factory=factory,
            action_label="Open variant workspace",
            minimum_selection=1,
        )
    )
    window.pluginRuntime.registry.install(PLUGIN_ID, registrar.contributions)
    window.pluginUi.refresh_contributions()
    window.pluginUi.editorWorkspaces.open_workspace(CONTRIBUTION_ID)
    qApp.processEvents()
    return received[0] if received else None, item


def test_a_workspace_that_declared_nothing_is_given_nothing(
        MWEmptyProject):
    """Registering a workspace used to be the whole negotiation: every one
    of them got the gateway that can rewrite any document in the book.
    """
    window = MWEmptyProject
    try:
        context, _item = _open_with(window, ())

        assert context is not None
        assert context.outline is None
        assert context.editors is None
        with pytest.raises(PluginScopeError, match="did not declare"):
            context.capability(CAPABILITY_QUERY_EXECUTE)
        # What it was opened on is the argument of the call, not a view of
        # the manuscript, so it arrives either way.
        assert len(context.selected_item_ids) == 1
    finally:
        _remove_workspace(window)


def test_workspace_resolves_declared_story_capability_at_use_time(
        MWEmptyProject):
    window = MWEmptyProject
    try:
        context, _item = _open_with(window, (CAPABILITY_QUERY_EXECUTE,))

        capability = context.capability(CAPABILITY_QUERY_EXECUTE)

        assert capability.execute(All(QueryScope.ASSERTION)) == ()
    finally:
        _remove_workspace(window)


def test_declaring_outline_read_grants_reading_and_not_writing(
        MWEmptyProject):
    window = MWEmptyProject
    try:
        context, item = _open_with(window, (CAPABILITY_OUTLINE_READ,))

        outline = context.outline
        assert outline.document(item.ID()).text == "A paragraph."
        assert outline.documents()
        assert outline.selected_item_ids() == (item.ID(),)

        # The mutators are not disabled -- they are not there. A plugin
        # asking whether it may write gets a straight answer.
        for method in (
            "set_text",
            "set_title",
            "set_compile",
            "set_compile_many",
            "create_text_document",
            "duplicate_text_document",
        ):
            assert not hasattr(outline, method), method
        with pytest.raises(AttributeError):
            outline.set_text(item.ID(), "Rewritten by a reader.")
        assert item.text() == "A paragraph."

        # Watching the manuscript change is reading it.
        seen = []
        outline.documentChanged.connect(seen.append)
        window.projectRuntime.models.outline.getItemByID(item.ID()).setData(
            Outline.text, "Changed elsewhere.",
        )
        qApp.processEvents()
        # However many times: one edit reaches several columns, and word
        # counts propagate up the tree behind it.
        assert item.ID() in seen
    finally:
        _remove_workspace(window)


def test_declaring_outline_write_grants_the_whole_gateway(MWEmptyProject):
    """Writing includes reading, so a plugin need not declare both."""
    window = MWEmptyProject
    try:
        context, item = _open_with(window, (CAPABILITY_OUTLINE_WRITE,))

        outline = context.outline
        assert outline is window.pluginUi.editorWorkspaces._outline
        assert outline.document(item.ID()) is not None
        assert outline.set_text(item.ID(), "Rewritten.")
        assert item.text() == "Rewritten."
    finally:
        _remove_workspace(window)


def test_editor_panes_need_declaring_too(MWEmptyProject):
    window = MWEmptyProject
    try:
        context, _item = _open_with(window, (CAPABILITY_OUTLINE_READ,))
        assert context.editors is None
    finally:
        _remove_workspace(window)

    try:
        context, _item = _open_with(window, (CAPABILITY_EDITOR_CONTROL,))
        assert context.editors is (
            window.pluginUi.editorWorkspaces._editors
        )
    finally:
        _remove_workspace(window)


def test_a_workspace_that_falls_over_does_not_wait_for_anybody(
        MWEmptyProject):
    """It was a modal dialog, and gating makes it reachable in a new way: a
    plugin that declared nothing reaches for an outline that is not there.
    A modal stops the application on a plugin's mistake -- and in a test
    run stops it with nobody to press the button.
    """
    window = MWEmptyProject
    said = []
    window.statusPresenter.show = lambda *args: said.append(args)

    def factory(context, parent):
        return context.outline.documents()

    item = outlineItem(title="Scene", _type="md")
    window.projectRuntime.models.outline.appendItem(item)
    window.corePanels.project_tree.tree.selectionModel().setCurrentIndex(
        window.projectRuntime.models.outline.indexFromItem(item),
        QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
    )
    _declare(window, ())
    registrar = window.pluginRuntime.registry.registrar(PLUGIN_ID)
    registrar.register_editor_workspace(
        EditorWorkspaceContribution(
            descriptor=ExtensionDescriptor(
                id=CONTRIBUTION_ID,
                name="Compare variants",
                description="Compare scene variants.",
            ),
            workspace_factory=factory,
            action_label="Open variant workspace",
            minimum_selection=1,
        )
    )
    window.pluginRuntime.registry.install(PLUGIN_ID, registrar.contributions)
    window.pluginUi.refresh_contributions()
    try:
        assert window.pluginUi.editorWorkspaces.open_workspace(
            CONTRIBUTION_ID
        ) is None
        assert not window.mainEditor.pluginWorkspaceActive
        assert said and "Compare variants" in said[0][0]
    finally:
        del window.statusPresenter.show
        _remove_workspace(window)


def test_workspace_action_respects_selection_and_disable(MWEmptyProject):
    window = MWEmptyProject
    received = []
    endpoints = []
    _install_workspace(window, received, endpoints)
    try:
        window.corePanels.project_tree.tree.clearSelection()
        window.corePanels.project_tree.tree.setCurrentIndex(QModelIndex())
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


def test_a_workspace_pane_wraps_to_itself_not_to_the_editor_it_replaced(
        MWEmptyProject):
    """A workspace projection wraps to its own width.

    Text is shared with the native tabs, but QTextDocument layout is not.
    The pane is much narrower than the native editor and must neither clip
    prose nor acquire a horizontal scrollbar when outline selection changes.
    """
    window = MWEmptyProject
    received = []
    endpoints = []
    outline = window.projectRuntime.models.outline
    items = []
    for title in ("Scene one", "Scene two"):
        item = outlineItem(title=title, _type="md")
        item.setData(Outline.text, "A paragraph of quite ordinary prose. " * 60)
        outline.appendItem(item)
        items.append(item)
    tree = window.corePanels.project_tree.tree

    def select(item):
        tree.selectionModel().setCurrentIndex(
            outline.indexFromItem(item),
            QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
        )
        window.mainEditor.selectionChanged()
        qApp.processEvents()

    select(items[0])
    select(items[1])
    assert window.mainEditor.currentEditor() is not None

    _install_workspace(window, received, endpoints)
    try:
        host = window.pluginUi.editorWorkspaces
        host.open_workspace(CONTRIBUTION_ID)
        qApp.processEvents()
        endpoint = endpoints[0]
        endpoint.set_maximum_text_width(240)
        qApp.processEvents()

        def pane_is_readable():
            layout = endpoint.editor.document().documentLayout()
            return (
                layout.documentSize().width()
                <= endpoint.editor.viewport().width()
                and endpoint.editor.horizontalScrollBar().maximum() == 0
            )

        assert pane_is_readable()

        # Reading around the outline while the workspace stands in for the
        # editor must not hand the document back to a tab nobody can see.
        select(items[0])
        select(items[1])

        assert pane_is_readable()

        host.close_workspace()
        qApp.processEvents()
        # The editor takes its documents back when it is on screen again.
        assert window.mainEditor.currentEditor().currentIndex.isValid()
        assert window.mainEditor.currentEditor().txtRedacText.toPlainText()
    finally:
        _remove_workspace(window)
