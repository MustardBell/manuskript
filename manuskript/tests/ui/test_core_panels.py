"""Core project surfaces use the same native dock infrastructure as plugins."""

from dataclasses import fields

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDockWidget, QMainWindow

from manuskript.panels import DOCK, PanelContext, PanelRegistry
from manuskript.panels.core import (
    CHARACTER_ENTITIES,
    ENTITY_EDITOR,
    METADATA,
    PLOT_ENTITIES,
    PROJECT_ENTITIES,
    PROJECT_TREE,
    STORYLINE,
    WORLD_ENTITIES,
    core_panel_descriptors,
    register_core_panels,
)


CORE_IDS = (
    PROJECT_TREE,
    METADATA,
    STORYLINE,
    PROJECT_ENTITIES,
    CHARACTER_ENTITIES,
    PLOT_ENTITIES,
    WORLD_ENTITIES,
    ENTITY_EDITOR,
)


def test_panel_factories_receive_no_main_window_escape_hatch():
    assert tuple(field.name for field in fields(PanelContext)) == (
        "translate", "show_status", "plugin_project",
    )
    assert not hasattr(PanelContext(), "window")


def test_core_surfaces_are_attached_as_registry_panels(MWEmptyProject):
    window = MWEmptyProject
    widgets = (
        window.corePanels.project_tree.panel,
        window.corePanels.metadata,
        window.corePanels.storyline,
        window.corePanels.project_entities,
        window.corePanels.character_entities,
        window.corePanels.plot_entities,
        window.corePanels.world_entities,
        window.corePanels.entity_editor,
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
        "project_tree",
        "metadata",
        "storyline",
        "project_entities",
        "character_entities",
        "plot_entities",
        "world_entities",
        "entity_editor",
    ]
    assert not hasattr(MWEmptyProject.corePanels, "book_summary")


def test_every_core_panel_is_movable_floatable_and_nestable(MWEmptyProject):
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
    assert all(
        descriptor.placement == DOCK
        for descriptor in core_panel_descriptors(6)
    )


ENTITY_IDS = (
    PROJECT_ENTITIES,
    CHARACTER_ENTITIES,
    PLOT_ENTITIES,
    WORLD_ENTITIES,
    ENTITY_EDITOR,
)


def test_entity_panels_belong_to_no_single_main_tab():
    """They describe the whole project, so no tab may own their toggle."""

    groups = {
        descriptor.id: descriptor.group
        for descriptor in core_panel_descriptors(6)
    }
    assert all(groups[panel_id] is None for panel_id in ENTITY_IDS)


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


def test_switching_main_tab_keeps_ungrouped_panel_toggles_reachable(
        MWEmptyProject):
    """An ungrouped toggle is shown all the time, per the toolbar contract.

    The entity docks are closed by default, so hiding their buttons on a
    tab change would leave no way to bring them back.
    """

    window = MWEmptyProject
    toolbar = window.toolbar

    for group in (window.TabRedac, window.TabOutline, window.TabRedac):
        toolbar.setCurrentGroup(group)
        for panel_id in ENTITY_IDS:
            entry = toolbar._panelToggles[panel_id][1]
            assert entry.isVisible(), (panel_id, group)
