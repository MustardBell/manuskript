from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow

from manuskript.domain.entity_catalog import (
    EntityCatalog,
    first_party_story_entity_schemas,
)
from manuskript.linguistics import first_party_morphology_schemas
from manuskript.ui.connections import SignalConnectionRegistry
from manuskript.ui.entity_workspace import EntityWorkspaceController
from manuskript.ui.panels.core.entities import (
    build_character_entities,
    build_plot_entities,
    build_project_entities,
    build_world_entities,
)
from manuskript.panels import PanelContext
from manuskript.panels.core import CHARACTER_ENTITIES, EDITOR


def _workspace(parent):
    catalog = EntityCatalog(
        first_party_story_entity_schemas(),
        id_factory=lambda: "new-character",
    )
    catalog.replace((), writable=True)
    storage = MagicMock()
    storage.entity_catalog = catalog
    storage.morphology_schemas = first_party_morphology_schemas()
    manager = MagicMock()
    manager.storage = storage
    manager.createEntity.side_effect = catalog.create
    manager.updateEntity.side_effect = catalog.update
    manager.deleteEntity.side_effect = catalog.delete
    runtime = MagicMock()
    runtime.projectManager = manager
    context = PanelContext(translate=lambda text: text)
    panels = (
        build_project_entities(context, parent),
        build_character_entities(context, parent),
        build_plot_entities(context, parent),
        build_world_entities(context, parent),
    )
    return EntityWorkspaceController(parent, runtime, panels), catalog, panels


def test_entity_workspace_routes_creation_to_the_matching_dock(
        test_application):
    parent = QMainWindow()
    controller, catalog, panels = _workspace(parent)
    connections = SignalConnectionRegistry()
    controller.bind(connections.connect)

    with patch(
        "manuskript.ui.entity_workspace.QInputDialog.getText",
        return_value=("Olena", True),
    ):
        assert controller.create("character")

    assert catalog.find("new-character").title == "Olena"
    assert panels[1].tree.topLevelItemCount() == 1
    assert panels[2].tree.topLevelItemCount() == 0
    dialog = controller.dialog_for("new-character")
    assert dialog.morphologyButton.isEnabled()
    controller.unbind()
    connections.disconnect_all()
    parent.close()


def test_entity_browser_binding_follows_surface_ownership(test_application):
    parent = QMainWindow()
    controller, _catalog, panels = _workspace(parent)
    connections = SignalConnectionRegistry()
    controller.bind(connections.connect)
    character_panel = panels[1]
    instance = SimpleNamespace(
        id=CHARACTER_ENTITIES,
        widget=character_panel,
    )

    controller.detach_surface(instance)

    assert character_panel not in controller.panels
    assert character_panel not in controller.editors
    assert character_panel.tree.topLevelItemCount() == 0

    controller.attach_surface(instance)

    assert character_panel in controller.panels
    assert character_panel in controller.editors
    controller.unbind()
    connections.disconnect_all()
    parent.close()


def test_format_one_story_models_appear_in_entity_docks(MWSampleProject):
    window = MWSampleProject

    assert len(window.corePanels.project_entities.entities) == 1
    assert len(window.corePanels.character_entities.entities) == 6
    assert len(window.corePanels.plot_entities.entities) == 3
    assert len(window.corePanels.world_entities.entities) > 0
    assert window.corePanels.character_entities.newButton.isEnabled()
    catalog = window.projectManager.storage.entity_catalog
    assert catalog.can_edit(
        window.corePanels.character_entities.entities[0].id
    )
    # Legacy write-through is not permission to activate Format 2 syntax.
    assert not catalog.writable


def test_characters_are_read_under_main_secondary_and_minor(MWSampleProject):
    """The importance grouping is how a cast has always been read.

    A flat alphabetical run says nothing about who the story is about,
    which is what the generic entity list lost.
    """
    tree = MWSampleProject.corePanels.character_entities.tree

    headings = [
        tree.topLevelItem(i).text(0)
        for i in range(tree.topLevelItemCount())
    ]
    assert headings == ["Main", "Secondary", "Minor"]

    listed = {
        tree.topLevelItem(i).text(0): [
            tree.topLevelItem(i).child(j).text(0)
            for j in range(tree.topLevelItem(i).childCount())
        ]
        for i in range(tree.topLevelItemCount())
    }
    assert listed["Main"] == ["Paul", "Peter"]
    assert listed["Minor"] == ["Herod"]
    # A heading stands for no entity, so nothing can be edited through it.
    assert tree.topLevelItem(0).data(0, Qt.UserRole) is None


def test_entity_detail_is_browser_reachable_but_not_browser_embedded(
    MWEmptyProject,
):
    """The browser remains an overview while details get usable space."""
    window = MWEmptyProject

    assert not hasattr(window.corePanels, "entity_editor")
    assert {
        surface_id
        for surface_id in window.surfaceHost.instances
        if "editor" in surface_id
    } == {EDITOR}

    assert all(
        not hasattr(panel, "editor")
        for panel in window.entityWorkspace.panels
    )
    assert "Hold Alt" in (
        window.corePanels.character_entities.editButton.toolTip()
    )


def test_leaving_a_catalogue_browser_leaves_it_usable(MWEmptyProject):
    """Reported when browsers were docks: creating a character raised
    RuntimeError after one was closed with its X. Delete-on-close
    destroyed the panel, and the next catalogue change wrote into its
    deleted tree.

    Browsers are independently docked surfaces again. Closing one must hide
    its presentation without destroying the living surface owned by the
    workspace; activation must reveal that same instance again.
    """
    from PyQt5 import sip
    from PyQt5.QtCore import QCoreApplication, QEvent
    from PyQt5.QtWidgets import qApp

    from manuskript.panels.core import CHARACTER_ENTITIES, EDITOR

    window = MWEmptyProject
    instance = window.surfaceHost.instance(CHARACTER_ENTITIES)
    panel = instance.widget
    dock = instance.container

    assert dock.close()
    qApp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    qApp.processEvents()

    assert dock.isHidden()
    assert not sip.isdeleted(panel)
    assert window.surfaceHost.contains(CHARACTER_ENTITIES)

    # What the crash came through: a catalogue change reaching the panel.
    window.entityWorkspace.refresh()

    assert window.activatePanel(CHARACTER_ENTITIES)
    assert window.surfaceHost.current() == CHARACTER_ENTITIES
    assert instance.widget is panel
    assert not dock.isHidden()


def test_legacy_story_pages_are_not_user_interface(MWEmptyProject):
    """The tab-era pages are absent; descriptor-backed navigation remains.

    The central container is only the welcome/developer shell. Project
    surfaces are descriptor-built docks and never compatibility pages in it.
    """
    window = MWEmptyProject
    assert window.tabMain.count() == 1
    assert window.tabMain.widget(window.DebugPage).objectName() == "lytTabDebug"
    for panel_id in (
        "core.entities.project",
        "core.entities.characters",
        "core.entities.plots",
        "core.entities.world",
    ):
        row = window.navigator.row_for_panel(panel_id)
        assert row is not None
        assert not window.lstTabs.item(row).isHidden()
        assert window.navigator.target(row).opens_panel
