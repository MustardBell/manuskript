from unittest.mock import MagicMock, patch

from PyQt5.QtWidgets import QWidget

from manuskript.domain.entity_catalog import (
    EntityCatalog,
    first_party_story_entity_schemas,
)
from manuskript.linguistics import first_party_morphology_providers
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
    storage.morphology_providers = first_party_morphology_providers()
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
    dialog = controller.editor._dialogs["new-character"]
    assert dialog.morphologyButton.isEnabled()
    controller.unbind()
    connections.disconnect_all()
    parent.close()


def test_format_one_story_models_appear_in_entity_docks(MWSampleProject):
    window = MWSampleProject

    assert window.corePanels.project_entities.tree.topLevelItemCount() == 1
    assert window.corePanels.character_entities.tree.topLevelItemCount() == 6
    assert window.corePanels.plot_entities.tree.topLevelItemCount() == 3
    assert window.corePanels.world_entities.tree.topLevelItemCount() > 0
    assert not window.corePanels.character_entities.newButton.isEnabled()


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


def test_legacy_story_tabs_are_not_user_interface(MWEmptyProject):
    window = MWEmptyProject
    for index in (
        window.TabSummary,
        window.TabPersos,
        window.TabPlots,
        window.TabWorld,
    ):
        assert window.lstTabs.item(index).isHidden()
        assert not window.tabMain.isTabVisible(index)
