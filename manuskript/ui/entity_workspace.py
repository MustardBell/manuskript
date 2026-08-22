"""Window-local control of the canonical entity dock surfaces."""

from PyQt5.QtWidgets import QInputDialog, QMessageBox

from manuskript.panels.core import (
    CHARACTER_ENTITIES,
    PLOT_ENTITIES,
    PROJECT_ENTITIES,
    WORLD_ENTITIES,
)
from manuskript.ui.connections import SignalConnectionRegistry
from manuskript.ui.connections import weak_callback
from manuskript.ui.entity_editor import EntityEditorController


ENTITY_SURFACES = {
    PROJECT_ENTITIES,
    CHARACTER_ENTITIES,
    PLOT_ENTITIES,
    WORLD_ENTITIES,
}


class EntityWorkspaceController:
    """Bind one window's entity docks to the project-owned catalogue."""

    def __init__(self, parent, runtime, panels):
        self.parent = parent
        self.runtime = runtime
        self.panels = list(panels)
        self.catalog = None
        self.manager = None
        self.editors = {}
        self._connections = {}
        self.bound = False
        # The catalogue belongs to the project and outlives every window
        # onto it, so what it holds must not be this window. A stale
        # subscription resolves to nothing rather than to a closed
        # workspace.
        self._onCatalogChanged = weak_callback(self.refresh)

    def bind(self, connect):
        if self.bound:
            raise RuntimeError(
                "Entity workspace must be released before rebinding."
            )
        self.manager = self.runtime.projectManager
        if self.manager is None:
            raise RuntimeError("Entity workspace requires a project manager.")
        self.catalog = self.manager.storage.entity_catalog
        for panel in self.panels:
            self._bind_panel(panel)
        self.catalog.subscribe(self._onCatalogChanged)
        self.bound = True
        self.refresh()

    def unbind(self):
        if not self.bound:
            return
        self.catalog.unsubscribe(self._onCatalogChanged)
        for panel in self.panels:
            self._unbind_panel(panel)
        self.catalog = None
        self.manager = None
        self.bound = False

    def attach_surface(self, instance):
        """Adopt an entity browser when its surface enters this workspace."""

        if instance.id not in ENTITY_SURFACES:
            return
        panel = instance.widget
        if panel in self.panels:
            return
        self.panels.append(panel)
        if self.bound:
            self._bind_panel(panel)
            self.refresh()

    def detach_surface(self, instance):
        """Release an entity browser before it leaves this workspace."""

        if instance.id not in ENTITY_SURFACES:
            return
        panel = instance.widget
        if panel not in self.panels:
            return
        if self.bound:
            self._unbind_panel(panel)
        self.panels.remove(panel)

    def _bind_panel(self, panel):
        # One detail controller per browser. The browser travels between
        # workspaces; its dialogs are window-local and are closed when that
        # browser leaves rather than remaining owned by the source window.
        editor = EntityEditorController(
            self.parent,
            self.catalog,
            self.manager.updateEntity,
            self.manager.storage.morphology_schemas,
            morphology_enabled=lambda manager=self.manager: manager.storage
            .persistence_strategy.supports(
                "morphology.entities", write=True
            ),
        )
        connections = SignalConnectionRegistry()
        connections.connect(panel.createRequested, self.create)
        connections.connect(panel.editRequested, self.open)
        connections.connect(panel.selectionActivated, self.retarget)
        connections.connect(panel.deleteRequested, self.delete)
        self.editors[panel] = editor
        self._connections[panel] = connections

    def _unbind_panel(self, panel):
        connections = self._connections.pop(panel, None)
        if connections is not None:
            connections.disconnect_all()
        editor = self.editors.pop(panel, None)
        if editor is not None:
            editor.close_all()
        panel.set_catalogue((), (), False)

    def refresh(self):
        if self.catalog is None:
            return
        deletable = tuple(
            entity.id for entity in self.catalog.entities
            if entity.type != "project" and self.catalog.can_delete(entity.id)
        )
        for panel in self.panels:
            creatable = any(
                self.catalog.can_create(schema.type)
                for schema in self.catalog.schemas.schemas
                if (
                    (not panel.creatableTypes or schema.type in panel.creatableTypes)
                    and (not panel.acceptedTypes or schema.type in panel.acceptedTypes)
                    and schema.type not in panel.excludedTypes
                )
            )
            panel.set_catalogue(
                self.catalog.entities,
                self.catalog.schemas.schemas,
                creatable,
                deletable,
            )

    def create(self, entity_type):
        if self.catalog is None or not self.catalog.can_create(entity_type):
            return False
        schema = self.catalog.schemas.get(entity_type)
        label = schema.label if schema is not None else self.parent.tr("Entity")
        title, accepted = QInputDialog.getText(
            self.parent,
            self.parent.tr("New {}").format(label),
            self.parent.tr("{} name:").format(label),
        )
        title = " ".join(str(title).split())
        if not accepted or not title:
            return False
        try:
            entity = self.manager.createEntity(entity_type, title)
        except (PermissionError, ValueError) as error:
            QMessageBox.warning(
                self.parent,
                self.parent.tr("Cannot create {}").format(label),
                str(error),
            )
            return False
        return self.open(entity.id)

    def open(self, entity_id, new_window=False):
        """Open a browser-reachable detail window for an entity."""
        panel = self.panel_for(entity_id)
        if panel is None:
            return False
        editor = self.editors.get(panel)
        if editor is None or not editor.open(entity_id, new_window):
            return False
        return True

    def retarget(self, entity_id, new_window=False):
        panel = self.panel_for(entity_id)
        editor = self.editors.get(panel) if panel is not None else None
        if editor is None:
            return False
        return editor.retarget(entity_id, new_window)

    def dialog_for(self, entity_id):
        """The open form for one entity, wherever it is being edited."""
        panel = self.panel_for(entity_id)
        editor = self.editors.get(panel) if panel is not None else None
        if editor is None:
            return None
        return editor.dialog_for(entity_id)

    def current_editor(self):
        """The entity form now on screen, if one is."""
        for controller in self.editors.values():
            editor = controller.current_editor()
            if editor is not None:
                return editor
        return None

    def panel_for(self, entity_id):
        if self.catalog is None:
            return None
        entity = self.catalog.find(entity_id)
        if entity is None:
            return None
        return next(
            (panel for panel in self.panels if panel.accepts(entity)), None
        )

    def pending_editors(self):
        return tuple(
            dialog
            for editor in self.editors.values()
            for dialog in editor.pending_editors()
        )

    def delete(self, entity_id):
        if self.catalog is None:
            return False
        entity = self.catalog.find(entity_id)
        if (
            entity is None
            or entity.type == "project"
            or not self.catalog.can_delete(entity_id)
        ):
            return False
        answer = QMessageBox.question(
            self.parent,
            self.parent.tr("Delete entity"),
            self.parent.tr(
                "Delete '{}'? References to it will become unresolved."
            ).format(entity.title),
            QMessageBox.Delete | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Delete:
            return False
        try:
            self.manager.deleteEntity(entity_id)
        except (KeyError, PermissionError, ValueError) as error:
            QMessageBox.warning(
                self.parent,
                self.parent.tr("Cannot delete entity"),
                str(error),
            )
            return False
        return True

    def dispose(self):
        self.unbind()
        self.panels = ()
        self.parent = None
        self.runtime = None
