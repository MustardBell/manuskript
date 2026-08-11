"""Window-local control of the canonical entity dock surfaces."""

from PyQt5.QtWidgets import QInputDialog, QMessageBox

from manuskript.ui.connections import weak_callback
from manuskript.ui.entity_editor import EntityEditorController


class EntityWorkspaceController:
    """Bind one window's entity docks to the project-owned catalogue."""

    def __init__(self, parent, runtime, panels):
        self.parent = parent
        self.runtime = runtime
        self.panels = tuple(panels)
        self.catalog = None
        self.manager = None
        self.editors = {}
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
        # One editor per browser, mounted in that browser's own half.
        # An entity is edited where it is listed, so there is no editor
        # to be left looking at without the list it came from.
        self.editors = {
            panel: EntityEditorController(
                self.parent,
                self.catalog,
                self.manager.updateEntity,
                self.manager.storage.morphology_providers,
                host_panel=panel.editor,
            )
            for panel in self.panels
        }
        for panel in self.panels:
            connect(panel.createRequested, self.create)
            connect(panel.editRequested, self.open)
            connect(panel.deleteRequested, self.delete)
        self.catalog.subscribe(self._onCatalogChanged)
        self.bound = True
        self.refresh()

    def unbind(self):
        if not self.bound:
            return
        self.catalog.unsubscribe(self._onCatalogChanged)
        for editor in self.editors.values():
            editor.close_all()
        self.editors = {}
        for panel in self.panels:
            panel.set_catalogue((), (), False)
        self.catalog = None
        self.manager = None
        self.bound = False

    def refresh(self):
        if self.catalog is None:
            return
        editable = tuple(
            entity.id for entity in self.catalog.native_entities
            if entity.type != "project"
        ) if self.catalog.writable else ()
        for panel in self.panels:
            panel.set_catalogue(
                self.catalog.entities,
                self.catalog.schemas.schemas,
                self.catalog.writable,
                editable,
            )

    def create(self, entity_type):
        if self.catalog is None or not self.catalog.writable:
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

    def open(self, entity_id):
        """Edit an entity in the browser that lists it."""
        panel = self.panel_for(entity_id)
        if panel is None:
            return False
        editor = self.editors.get(panel)
        if editor is None or not editor.open(entity_id):
            return False
        panel.show_editor()
        return True

    def dialog_for(self, entity_id):
        """The open form for one entity, wherever it is being edited."""
        panel = self.panel_for(entity_id)
        editor = self.editors.get(panel) if panel is not None else None
        if editor is None:
            return None
        return editor._dialogs.get(entity_id)

    def current_editor(self):
        """The entity form now on screen, if one is."""
        for panel in self.panels:
            editor = panel.editor.editor
            if editor is not None and not panel.editor.isHidden():
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
            or entity not in self.catalog.native_entities
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
