"""Core project surfaces use the same native dock infrastructure as plugins."""

from dataclasses import fields

import pytest

from PyQt5 import sip
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDockWidget, QMainWindow, QTabBar, qApp

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


def test_core_surfaces_are_attached_as_registry_panels(MWEmptyProject):
    window = MWEmptyProject
    widgets = (
        window.corePanels.general,
        window.corePanels.project_tree.panel,
        window.corePanels.metadata,
        window.corePanels.storyline,
        window.corePanels.project_entities,
        window.corePanels.character_entities,
        window.corePanels.plot_entities,
        window.corePanels.world_entities,
        window.corePanels.outline,
        window.corePanels.editor,
    )
    for panel_id, widget in zip(CORE_IDS, widgets):
        instance = window.panelHost.instance(panel_id)
        assert panel_id in window.panelRegistry
        assert instance.widget is widget
        assert isinstance(instance.container, QDockWidget)
        assert instance.action is not None


def test_core_view_contract_contains_only_current_surfaces(MWEmptyProject):
    assert [
        field.name for field in fields(type(MWEmptyProject.corePanels))
    ] == [
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
    ]
    assert not hasattr(MWEmptyProject.corePanels, "book_summary")


def test_every_core_panel_is_movable_floatable_and_nestable(MWEmptyProject):
    """Floatable stays until there is a gesture to replace it with.

    A navigator surface is a window rather than a dock, and floating one
    gives it a utility window owned by this workspace. Saying so by taking
    Qt's floatable feature away was worse than the thing it corrected: Qt
    still begins the drag and the model vetoes the outcome, so the dock
    snaps back on release, and a session saved with the editor detached
    snapped it home the moment it was touched. The distinction lives in the
    Float Panel menu instead, until a detach gesture exists that ends in a
    real workspace.
    """

    window = MWEmptyProject
    required = (
        QDockWidget.DockWidgetClosable
        | QDockWidget.DockWidgetMovable
        | QDockWidget.DockWidgetFloatable
    )
    for panel_id in CORE_IDS:
        dock = window.panelHost.instance(panel_id).container
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
    # Only a tool panel has a placement to be asked about. A surface is
    # hosted centrally, and answering DOCK from a property was how every
    # old consumer went on believing everything has one.
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
    """A project panel is a dock now, so nothing covers it any more.

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


def test_every_story_surface_is_a_navigator_backed_dock(
        MWEmptyProject):
    """General through Editor share one descriptor-driven route."""
    window = MWEmptyProject
    for panel_id in (
        GENERAL,
        PROJECT_ENTITIES,
        CHARACTER_ENTITIES,
        PLOT_ENTITIES,
        WORLD_ENTITIES,
        OUTLINE,
        EDITOR,
    ):
        row = window.navigator.row_for_panel(panel_id)
        assert row is not None
        assert not window.lstTabs.item(row).isHidden()

    row = window.navigator.row_for_panel(CHARACTER_ENTITIES)
    window.panelHost.set_visible(CHARACTER_ENTITIES, False)
    dock = window.panelHost.instance(CHARACTER_ENTITIES).container
    assert dock.isHidden()

    assert window.navigateTo(row)

    assert not dock.isHidden()
    assert window._activePanelId == CHARACTER_ENTITIES
    assert window.centralWidget() is None


def test_navigator_selects_the_requested_tabified_work_surface(
        MWEmptyProject):
    """The highlighted navigator row and rendered dock must agree."""
    window = MWEmptyProject
    was_visible = window.isVisible()
    window.show()
    qApp.processEvents()
    general = window.panelHost.instance(GENERAL).container
    editor = window.panelHost.instance(EDITOR).container
    try:
        window.tabifyDockWidget(editor, general)
        qApp.processEvents()
        assert window.activatePanel(EDITOR)
        assert window.activatePanel(GENERAL)
        qApp.processEvents()

        address = sip.unwrapinstance(general)
        matching = [
            tab_bar
            for tab_bar in window.findChildren(QTabBar)
            if any(
                int(tab_bar.tabData(index)) == address
                for index in range(tab_bar.count())
            )
        ]
        assert len(matching) == 1
        current = matching[0].currentIndex()
        assert int(matching[0].tabData(current)) == address
        assert window.lstTabs.currentRow() == window.navigator.row_for_panel(
            GENERAL
        )
    finally:
        if not was_visible:
            window.hide()


def test_designer_contains_no_legacy_story_pages(MWEmptyProject):
    window = MWEmptyProject
    assert window.tabMain.count() == 1
    assert window.tabMain.widget(0).objectName() == "lytTabDebug"
    for name in (
        "lytTabSummary", "lytTabPersos", "lytTabPlot", "lytTabContext",
        "lytTabOutline", "lytTabRedac",
    ):
        assert not hasattr(window, name)


def test_entity_docks_land_as_neighbours_not_as_one_tabbed_dock(
        MWEmptyProject):
    """Five docks, not one dock with five tabs.

    They answer different questions and are read together, so tabbing
    them over each other hid four behind a tab strip and made a single
    dock out of the set.
    """
    window = MWEmptyProject

    for panel_id in ENTITY_IDS:
        window.panelHost.reveal(panel_id)

    docks = [
        window.panelHost.instance(panel_id).container
        for panel_id in ENTITY_IDS
    ]
    for dock in docks:
        assert window.tabifiedDockWidgets(dock) == [], dock.objectName()


def test_opening_a_project_brings_its_panels_back(MWEmptyProject):
    window = MWEmptyProject

    visible = {
        panel_id
        for panel_id, instance in window.panelHost.instances.items()
        if instance.descriptor.requires_project
        and instance.container is not None
        and not instance.container.isHidden()
    }
    assert CHARACTER_ENTITIES in visible
    assert PROJECT_TREE in visible


def test_every_core_panel_toggle_is_always_reachable(
        MWEmptyProject):
    window = MWEmptyProject
    toolbar = window.toolbar

    for group in ("anything", None, "plugin.surface"):
        toolbar.setCurrentGroup(group)
        for panel_id in CORE_IDS:
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


def test_a_surface_has_no_placement_to_be_asked_about():
    """It is hosted centrally, so the question does not apply to it.

    It briefly answered DOCK from a property so the panel host could mount
    one, which let every old consumer go on believing everything has a
    placement. The transitional wrongness lives in the host that is about
    to lose it instead.
    """

    from manuskript.panels import DOCK, WorkspaceSurfaceDescriptor

    surface = WorkspaceSurfaceDescriptor(id="core.editor", title="Editor")

    assert not hasattr(surface, "placement")
    assert not hasattr(surface, "slot")
    assert not hasattr(surface, "group")
    with pytest.raises(TypeError):
        WorkspaceSurfaceDescriptor(
            id="core.editor", title="Editor", placement=DOCK,
        )
