"""Two kinds of core widget, and the two owners they belong to.

Tool panels and workspace surfaces have different owners. Both may use
native docks as presentation, but a surface never enters PanelHost and a
tool panel never enters WorkspaceSurfaceHost merely because their Qt
containers look alike.
"""

from dataclasses import fields

import pytest

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDockWidget, QMainWindow, qApp

from manuskript.panels import DOCK, PanelContext, PanelRegistry
from manuskript.panels.core import (
    CHARACTER_ENTITIES,
    EDITOR,
    GENERAL,
    METADATA,
    OUTLINE,
    PLOT_ENTITIES,
    PROJECT_ENTITIES,
    PROJECT_TREE,
    STORYLINE,
    WORLD_ENTITIES,
    core_panel_descriptors,
    register_core_panels,
)


CORE_IDS = (
    GENERAL,
    PROJECT_TREE,
    METADATA,
    STORYLINE,
    PROJECT_ENTITIES,
    CHARACTER_ENTITIES,
    PLOT_ENTITIES,
    WORLD_ENTITIES,
    OUTLINE,
    EDITOR,
)


def test_panel_factories_receive_no_main_window_escape_hatch():
    assert tuple(field.name for field in fields(PanelContext)) == (
        "translate", "show_status", "plugin_project",
    )
    assert not hasattr(PanelContext(), "window")


#: Kept beside the writing, in docks.
TOOL_PANEL_IDS = (PROJECT_TREE, METADATA, STORYLINE)

#: Places the writer goes, each independently presentable and movable.
SURFACE_IDS = (
    GENERAL,
    PROJECT_ENTITIES,
    CHARACTER_ENTITIES,
    PLOT_ENTITIES,
    WORLD_ENTITIES,
    OUTLINE,
    EDITOR,
)


def test_tool_panels_are_docks_their_host_built(MWEmptyProject):
    window = MWEmptyProject
    widgets = (
        window.corePanels.project_tree.panel,
        window.corePanels.metadata,
        window.corePanels.storyline,
    )
    for panel_id, widget in zip(TOOL_PANEL_IDS, widgets):
        instance = window.panelHost.instance(panel_id)
        assert panel_id in window.panelRegistry
        assert instance.widget is widget
        assert isinstance(instance.container, QDockWidget)
        assert instance.action is not None


def test_surfaces_are_independent_docks_owned_by_the_surface_host(
        MWEmptyProject):
    """Presentation does not collapse the ownership boundary."""

    window = MWEmptyProject
    widgets = (
        window.corePanels.general,
        window.corePanels.project_entities,
        window.corePanels.character_entities,
        window.corePanels.plot_entities,
        window.corePanels.world_entities,
        window.corePanels.outline,
        window.corePanels.editor,
    )
    for surface_id, widget in zip(SURFACE_IDS, widgets):
        instance = window.surfaceHost.instance(surface_id)
        assert surface_id in window.panelRegistry
        assert instance.widget is widget
        assert isinstance(instance.container, QDockWidget)
        assert instance.container.widget() is widget
        assert window.tabMain.indexOf(widget) == -1
        assert window.panelHost.instance(surface_id) is None


def test_core_view_contract_contains_only_current_surfaces(MWEmptyProject):
    views = MWEmptyProject.corePanels
    names = {
        name
        for name in dir(views)
        if not name.startswith("_")
        and name not in {"from_hosts"}
    }
    assert names == {
        "general",
        "project_tree",
        "metadata",
        "storyline",
        "project_entities",
        "character_entities",
        "plot_entities",
        "world_entities",
            "outline",
            "editor",
            "optional_tool",
        }
    assert not hasattr(MWEmptyProject.corePanels, "book_summary")


def test_every_core_container_is_movable_floatable_and_nestable(
        MWEmptyProject):
    """Every core surface can begin the real-window tear-off gesture."""

    window = MWEmptyProject
    required = (
        QDockWidget.DockWidgetClosable
        | QDockWidget.DockWidgetMovable
        | QDockWidget.DockWidgetFloatable
    )
    docks = [
        window.panelHost.instance(panel_id).container
        for panel_id in TOOL_PANEL_IDS
    ] + [
        window.surfaceHost.instance(surface_id).container
        for surface_id in SURFACE_IDS
    ]
    for dock in docks:
        assert dock.features() & required == required
        assert dock.allowedAreas() == Qt.AllDockWidgetAreas
    assert window.dockOptions() & QMainWindow.AllowNestedDocks
    assert window.dockOptions() & QMainWindow.AllowTabbedDocks


def test_toggling_action_shows_and_hides_the_dock(MWEmptyProject):
    instance = MWEmptyProject.panelHost.instance(METADATA)
    was_checked = instance.action.isChecked()

    instance.action.setChecked(True)
    assert not instance.container.isHidden()
    instance.action.setChecked(False)
    assert instance.container.isHidden()

    instance.action.setChecked(was_checked)


def test_entity_docks_partition_one_catalogue(MWEmptyProject):
    views = MWEmptyProject.corePanels
    assert views.project_entities.acceptedTypes == ("project",)
    assert views.character_entities.acceptedTypes == ("character",)
    assert views.plot_entities.acceptedTypes == ("plot",)
    assert set(views.world_entities.excludedTypes) == {
        "project", "character", "plot",
    }


def test_metadata_state_and_project_tree_factory_contracts(MWEmptyProject):
    window = MWEmptyProject
    metadata = window.corePanels.metadata
    state = metadata.saveState()
    metadata.restoreState(state)
    assert metadata.saveState() == state

    tree = window.corePanels.project_tree
    assert tree.panel.objectName() == "treeRedacWidget"
    assert tree.tree.parent() is tree.panel
    for button in (tree.add_folder, tree.add_text, tree.remove_item):
        assert button.parent() is tree.panel


def test_declaring_core_panels_twice_is_harmless():
    registry = PanelRegistry()
    register_core_panels(registry, 6)
    register_core_panels(registry, 6)

    assert tuple(entry.id for entry in registry.descriptors()) == CORE_IDS
    # Only a tool panel has a placement to be asked about. A surface's native
    # dock is presentation, and answering DOCK from its descriptor would make
    # every old consumer believe PanelHost owns it again.
    assert all(
        descriptor.placement == DOCK
        for descriptor in registry.tool_panels()
    )


ENTITY_IDS = (
    PROJECT_ENTITIES,
    CHARACTER_ENTITIES,
    PLOT_ENTITIES,
    WORLD_ENTITIES,
)


def test_core_panels_belong_to_no_single_main_tab():
    """Independent surfaces have no central tab owning their toggle."""

    from manuskript.panels import group_of

    groups = {
        descriptor.id: group_of(descriptor)
        for descriptor in core_panel_descriptors(6)
    }
    assert all(groups[panel_id] is None for panel_id in CORE_IDS)


def test_the_welcome_screen_shows_no_project_panel(MWNoProject):
    """A tool panel is a dock, so nothing covers it any more.

    In a splitter it sat inside the project page and the welcome screen
    hid it by being on top; a dock hangs off the window and stays up
    over the welcome screen until it is put away on purpose.
    """
    window = MWNoProject

    for panel_id, instance in window.panelHost.instances.items():
        if not instance.descriptor.requires_project:
            continue
        shown = (
            instance.container
            if instance.container is not None
            else instance.widget
        )
        assert shown.isHidden(), panel_id


def test_the_welcome_screen_hides_every_surface(MWNoProject):
    """Independent docks must not remain interactive over the welcome UI."""

    window = MWNoProject

    assert window.stack.currentIndex() == 0
    for surface_id, instance in window.surfaceHost.instances.items():
        assert instance.container.isHidden(), surface_id


def test_deferred_default_layout_never_reopens_a_surface_over_welcome(
        MWNoProject):
    window = MWNoProject
    window._defaultDockLayoutPending = True

    window._settleDefaultCoreDocks()

    assert window._defaultDockLayoutPending
    assert window.stack.currentIndex() == 0
    assert window.centralWidget() is window._centralSurface
    for surface_id, instance in window.surfaceHost.instances.items():
        assert instance.container.isHidden(), surface_id


def test_every_story_surface_is_a_navigator_backed_independent_dock(
        MWEmptyProject):
    """General through Editor share one descriptor-driven route."""
    window = MWEmptyProject
    for surface_id in SURFACE_IDS:
        row = window.navigator.row_for_panel(surface_id)
        assert row is not None
        assert not window.lstTabs.item(row).isHidden()

    row = window.navigator.row_for_panel(CHARACTER_ENTITIES)
    window.activatePanel(EDITOR)
    assert window.surfaceHost.current() == EDITOR

    assert window.navigateTo(row)

    assert window.surfaceHost.current() == CHARACTER_ENTITIES
    assert window._activePanelId == CHARACTER_ENTITIES
    assert window.centralWidget() is None
    assert not window.surfaceHost.instance(
        CHARACTER_ENTITIES
    ).container.isHidden()


def test_navigator_selects_the_requested_work_surface(MWEmptyProject):
    """Navigation reveals its surface without hiding another visible one."""

    window = MWEmptyProject
    was_visible = window.isVisible()
    window.show()
    qApp.processEvents()
    try:
        assert window.activatePanel(EDITOR)
        editor = window.surfaceHost.instance(EDITOR).container
        assert not editor.isHidden()
        assert window.activatePanel(GENERAL)
        qApp.processEvents()

        assert window.surfaceHost.current() == GENERAL
        assert not window.surfaceHost.instance(GENERAL).container.isHidden()
        assert not editor.isHidden()
        assert window.lstTabs.currentRow() == window.navigator.row_for_panel(
            GENERAL
        )
    finally:
        if not was_visible:
            window.hide()


def test_the_debug_container_holds_no_workspace_surface(
        MWEmptyProject):
    """No central page stack remains as an alternate surface topology."""

    window = MWEmptyProject

    pages = [
        window.tabMain.widget(index)
        for index in range(window.tabMain.count())
    ]
    assert [page.objectName() for page in pages] == ["lytTabDebug"]
    assert all(
        window.tabMain.indexOf(
            window.surfaceHost.instance(surface_id).widget
        ) == -1
        for surface_id in SURFACE_IDS
    )
    for name in (
        "lytTabSummary", "lytTabPersos", "lytTabPlot", "lytTabContext",
        "lytTabOutline", "lytTabRedac",
    ):
        assert not hasattr(window, name)


def test_the_catalogue_browsers_are_four_places_not_one(MWEmptyProject):
    """Four surfaces, each reachable on its own.

    They answer different questions, so one of them is never a tab strip
    over the other three -- which is what they were when the four docks
    were tabbed together, and is why they were split apart then.
    """

    window = MWEmptyProject

    for panel_id in ENTITY_IDS:
        assert window.surfaceHost.contains(panel_id)
        assert window.activatePanel(panel_id)
        assert window.surfaceHost.current() == panel_id


def test_project_panels_return_with_the_surface_scene_they_declare(
        MWEmptyProject):
    from manuskript.services.workspace_state import WorkspaceStateStore

    source = MWEmptyProject
    fresh_id = "window-surface-panel-defaults"
    WorkspaceStateStore().forget(fresh_id)
    window = source.workspaceWindows.open(fresh_id)
    try:
        independent_before = {
            panel_id: window.panelHost.instance(panel_id).container.isHidden()
            for panel_id in (METADATA, STORYLINE)
        }

        assert window.activatePanel(GENERAL)
        assert window.panelHost.instance(PROJECT_TREE).container.isHidden()

        assert window.activatePanel(EDITOR)
        assert not window.panelHost.instance(PROJECT_TREE).container.isHidden()
        assert independent_before == {
            panel_id: window.panelHost.instance(panel_id).container.isHidden()
            for panel_id in (METADATA, STORYLINE)
        }
        # A surface is not brought back by being made visible: the workspace
        # is showing one of them, and which one is what it remembered.
        assert window.surfaceHost.current() in SURFACE_IDS
    finally:
        window.close()
        WorkspaceStateStore().forget(fresh_id)


def test_every_independently_visible_core_container_has_a_toggle(
        MWEmptyProject):

    window = MWEmptyProject
    toolbar = window.toolbar

    for group in ("anything", None, "plugin.surface"):
        toolbar.setCurrentGroup(group)
        for panel_id in TOOL_PANEL_IDS + SURFACE_IDS:
            entry = toolbar._panelToggles[panel_id][1]
            assert entry.isVisible(), (panel_id, group)


def test_the_two_kinds_are_declared_as_two_kinds():
    """The user's rule, made a type rather than a field to read.

    "Anything that navigation has is NOT a dock. It could be docked but
    anything that navigation has and can enable is a window." So the seven
    places the writer goes are workspace surfaces and the three things kept
    beside the writing are tool panels, and nothing has to inspect a
    navigator field to work out which it is holding.
    """

    from manuskript.panels import (
        PanelRegistry,
        ToolPanelDescriptor,
        WorkspaceSurfaceDescriptor,
    )

    registry = PanelRegistry()
    register_core_panels(registry, 6)

    surfaces = {descriptor.id for descriptor in registry.surfaces()}
    tools = {descriptor.id for descriptor in registry.tool_panels()}

    assert surfaces == {
        GENERAL, PROJECT_ENTITIES, CHARACTER_ENTITIES, PLOT_ENTITIES,
        WORLD_ENTITIES, OUTLINE, EDITOR,
    }
    assert tools == {PROJECT_TREE, METADATA, STORYLINE}
    assert all(
        isinstance(descriptor, WorkspaceSurfaceDescriptor)
        for descriptor in registry.surfaces()
    )
    assert all(
        isinstance(descriptor, ToolPanelDescriptor)
        for descriptor in registry.tool_panels()
    )


def test_a_tool_panel_has_no_navigator_row_to_ask_for():
    """Not a field that only accepts None, which is the contradiction kept
    in the type to make an error message nicer. There is no field."""

    from manuskript.panels import NavigatorEntry, ToolPanelDescriptor

    with pytest.raises(TypeError, match="navigator"):
        ToolPanelDescriptor(
            id="core.notes",
            title="Notes",
            navigator=NavigatorEntry(label="Notes"),
        )


def test_a_surface_has_no_tool_panel_placement_to_be_asked_about():
    """Its presentation may dock it; its public descriptor remains Qt-free."""

    from manuskript.panels import DOCK, WorkspaceSurfaceDescriptor

    surface = WorkspaceSurfaceDescriptor(id="core.editor", title="Editor")

    assert not hasattr(surface, "placement")
    assert not hasattr(surface, "slot")
    assert not hasattr(surface, "group")
    with pytest.raises(TypeError):
        WorkspaceSurfaceDescriptor(
            id="core.editor", title="Editor", placement=DOCK,
        )


def test_what_the_window_calls_active_is_a_visible_surface(MWEmptyProject):

    window = MWEmptyProject

    for surface_id in (EDITOR, OUTLINE, GENERAL):
        assert window.activatePanel(surface_id)
        assert window._activePanelId == surface_id
        assert window.surfaceHost.current() == surface_id
        assert not window.surfaceHost.instance(
            surface_id
        ).container.isHidden()


def test_a_workspace_with_nothing_saved_starts_on_general(MWEmptyProject):
    """What a reader opening Manuskript has always been shown first.

    Stated at composition rather than left to whichever surface happened
    to be opened first, and it is what the parity oracle compares
    against: upstream opens on General.

    Under a window id nothing has ever been filed under, because a
    workspace that has a record of its own is meant to reopen where it
    was -- that is a different rule and it wins.
    """

    from manuskript.services.workspace_state import WorkspaceStateStore

    window = MWEmptyProject
    fresh_id = "window-never-saved"
    WorkspaceStateStore().forget(fresh_id)
    other = window.workspaceWindows.open(fresh_id)
    try:
        assert other.surfaceHost.current() == GENERAL
        assert other._activePanelId == GENERAL
    finally:
        other.close()
        WorkspaceStateStore().forget(fresh_id)


def test_the_developer_page_leaves_no_surface_current(MWEmptyProject):
    """Debug temporarily owns the central frame but never surface identity."""

    window = MWEmptyProject
    debug_row = window.navigator.row_for_page(window.DebugPage)
    assert debug_row is not None
    assert window.activatePanel(EDITOR)

    window.navigateTo(debug_row)

    assert window.surfaceHost.current() is None
    assert window.tabMain.currentWidget().objectName() == "lytTabDebug"

    assert window.activatePanel(GENERAL)

    assert window.surfaceHost.current() == GENERAL
    assert window.centralWidget() is None
    assert not window.surfaceHost.instance(GENERAL).container.isHidden()


def test_the_navigator_lists_what_this_workspace_holds(MWEmptyProject):
    """Membership, not availability.

    Rows used to come from every surface in the registry -- the
    application's list rather than this window's -- so selecting one this
    workspace did not hold built it here. A window made to hold one
    surface would fill up with seven, a click at a time.
    """

    from manuskript.services.workspace_state import WorkspaceStateStore

    window = MWEmptyProject
    fresh_id = "window-navigator-membership"
    WorkspaceStateStore().forget(fresh_id)
    other = window.workspaceWindows.open(fresh_id)
    try:
        assert other.navigator.row_for_panel(OUTLINE) is not None

        moved = other.surfaceHost.detach(OUTLINE)

        assert other.navigator.row_for_panel(OUTLINE) is None
        # And selecting it is no longer a way to acquire it.
        assert not other.goToSurface(OUTLINE)
        assert not other.surfaceHost.contains(OUTLINE)

        other.surfaceHost.attach(moved)

        assert other.navigator.row_for_panel(OUTLINE) is not None
        assert other.goToSurface(OUTLINE)
    finally:
        other.close()
        WorkspaceStateStore().forget(fresh_id)
