from unittest.mock import MagicMock, patch

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget

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
    parent = QWidget()
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


def test_format_one_story_models_appear_in_entity_docks(MWSampleProject):
    window = MWSampleProject

    assert len(window.corePanels.project_entities.entities) == 1
    assert len(window.corePanels.character_entities.entities) == 6
    assert len(window.corePanels.plot_entities.entities) == 3
    assert len(window.corePanels.world_entities.entities) > 0
    assert not window.corePanels.character_entities.newButton.isEnabled()


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


def test_an_entity_is_edited_where_it_is_listed(MWEmptyProject):
    """There is no entity editor to be left looking at on its own.

    Editing a character is something done to a character, so the form is
    the browser's other half rather than a surface of its own that can
    be opened, moved or closed without the list it belongs to.
    """
    window = MWEmptyProject

    assert not hasattr(window.corePanels, "entity_editor")
    assert all(
        "editor" not in panel_id
        for panel_id in window.panelHost.instances
    )

    panels = window.entityWorkspace.panels
    # Each browser edits in a half of its own, and that half is a child
    # of the browser -- so it cannot outlive it or be reached without it.
    halves = {id(panel.editor) for panel in panels}
    assert len(halves) == len(panels)
    for panel in panels:
        assert panel.isAncestorOf(panel.editor)


def test_closing_an_entity_dock_leaves_the_catalogue_usable(MWEmptyProject):
    """Reported: creating a character raised RuntimeError after a dock
    was closed with its X. Delete-on-close destroyed the panel, and the
    next catalogue change wrote into its deleted tree.
    """
    from PyQt5 import sip
    from PyQt5.QtCore import QCoreApplication, QEvent
    from PyQt5.QtWidgets import qApp

    from manuskript.panels.core import CHARACTER_ENTITIES

    window = MWEmptyProject
    instance = window.panelHost.instance(CHARACTER_ENTITIES)
    panel = instance.widget

    instance.container.close()
    qApp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    qApp.processEvents()

    assert not sip.isdeleted(panel)
    assert window.panelHost.instance(CHARACTER_ENTITIES) is not None

    # What the crash came through: a catalogue change reaching the panel.
    window.entityWorkspace.refresh()

    window.panelHost.set_visible(CHARACTER_ENTITIES, True)
    assert not instance.container.isHidden()


def test_legacy_story_pages_are_not_user_interface(MWEmptyProject):
    """The pages go; the navigation rows stay and open docks instead.

    Only the old widgets are unreachable -- taking the rows away as well
    would move where the person looks for characters, which is not what
    replacing the surface behind them was meant to do.
    """
    window = MWEmptyProject
    for index in (
        window.TabSummary,
        window.TabPersos,
        window.TabPlots,
        window.TabWorld,
    ):
        assert not window.tabMain.isTabVisible(index)
        assert not window.lstTabs.item(index).isHidden()
        # The row is still there and now opens the dock instead.
        assert window.navigator.target(index).opens_panel
