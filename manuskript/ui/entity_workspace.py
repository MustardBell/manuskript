"""Window-local control of the canonical entity dock surfaces."""

from functools import partial
from weakref import ref

from PyQt5.QtWidgets import QInputDialog, QMessageBox

from manuskript.ui.connections import weak_callback
from manuskript.ui.entity_editor import EntityEditorController


def _reveal_panel(host_reference, panel_id):
    host = host_reference()
    if host is not None:
        host.reveal(panel_id)


def panel_revealer(host, panel_id):
    """Return a reveal command that cannot retain its workspace window."""

    return partial(_reveal_panel, ref(host), panel_id)


class EntityWorkspaceController:
    """Bind one window's entity docks to the project-owned catalogue."""

    def __init__(
        self, parent, runtime, panels, editor_panel=None, reveal_editor=None
    ):
        self.parent = parent
        self.runtime = runtime
        self.panels = tuple(panels)
        self.editorPanel = editor_panel
        self.revealEditor = reveal_editor
        self.catalog = None
        self.manager = None
        self.editor = None
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
        self.editor = EntityEditorController(
            self.parent,
            self.catalog,
            self.manager.updateEntity,
            self.manager.storage.morphology_providers,
            host_panel=self.editorPanel,
            reveal=self.revealEditor,
        )
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
        if self.editor is not None:
            self.editor.close_all()
        for panel in self.panels:
            panel.set_catalogue((), (), False)
        self.editor = None
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
        return bool(self.editor is not None and self.editor.open(entity_id))

    def pending_editors(self):
        if self.editor is None:
            return ()
        return self.editor.pending_editors()

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
        self.editorPanel = None
        self.revealEditor = None
        self.parent = None
        self.runtime = None
