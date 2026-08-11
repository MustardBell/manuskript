"""Compact dock views over the canonical project entity catalogue."""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class EntityBrowserPanel(QWidget):
    """A model-free entity list suitable for a narrow QDockWidget."""

    createRequested = pyqtSignal(str)
    editRequested = pyqtSignal(str)
    deleteRequested = pyqtSignal(str)

    def __init__(
        self,
        title,
        accepted_types=(),
        excluded_types=(),
        creatable_types=(),
        parent=None,
    ):
        super().__init__(parent)
        self.title = str(title)
        self.acceptedTypes = tuple(accepted_types)
        self.excludedTypes = tuple(excluded_types)
        self.creatableTypes = tuple(creatable_types)
        self.schemas = ()
        self.entities = ()
        self.editableIds = set()
        self.writable = False
        self.setObjectName("entityBrowserPanel")
        self.setMinimumSize(180, 120)

        self.filterEdit = QLineEdit(self)
        self.filterEdit.setObjectName("entityFilter")
        self.filterEdit.setAccessibleName(
            self.tr("Filter {}").format(title)
        )
        self.filterEdit.setPlaceholderText(self.tr("Filter by name or alias…"))

        self.tree = QTreeWidget(self)
        self.tree.setObjectName("entityTree")
        self.tree.setAccessibleName(self.tr("{} entities").format(title))
        self.tree.setHeaderLabels((self.tr("Name"), self.tr("Type")))
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QTreeWidget.SingleSelection)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)

        self.countLabel = QLabel(self)
        self.countLabel.setObjectName("entityCount")
        self.countLabel.setAccessibleName(self.tr("Entity count"))

        self.newButton = QPushButton(self.tr("&New…"), self)
        self.newButton.setObjectName("newEntityButton")
        self.editButton = QPushButton(self.tr("&Edit…"), self)
        self.editButton.setObjectName("editEntityButton")
        self.deleteButton = QPushButton(self.tr("&Delete"), self)
        self.deleteButton.setObjectName("deleteEntityButton")
        self.editButton.setEnabled(False)
        self.deleteButton.setEnabled(False)

        actions = QHBoxLayout()
        actions.addWidget(self.newButton)
        actions.addWidget(self.editButton)
        actions.addWidget(self.deleteButton)
        actions.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.filterEdit)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.countLabel)
        layout.addLayout(actions)

        self.filterEdit.textChanged.connect(self._apply_filter)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.itemDoubleClicked.connect(self._edit_item)
        self.editButton.clicked.connect(self._edit_current)
        self.deleteButton.clicked.connect(self._delete_current)
        self.newButton.clicked.connect(self._show_create_menu)

    def accepts(self, entity):
        if self.acceptedTypes and entity.type not in self.acceptedTypes:
            return False
        return entity.type not in self.excludedTypes

    def set_catalogue(
        self, entities, schemas, writable, editable_entity_ids=()
    ):
        selected = self.current_entity_id()
        labels = {schema.type: schema.label for schema in schemas}
        self.schemas = tuple(schemas)
        self.writable = bool(writable)
        self.editableIds = set(editable_entity_ids)
        self.entities = tuple(
            entity for entity in entities if self.accepts(entity)
        )
        self.tree.clear()
        selected_item = None
        for entity in sorted(
            self.entities,
            key=lambda item: (item.title.casefold(), item.id),
        ):
            item = QTreeWidgetItem((
                entity.title,
                labels.get(
                    entity.type,
                    entity.type.replace("-", " ").title(),
                ),
            ))
            item.setData(0, Qt.UserRole, entity.id)
            item.setToolTip(0, "\n".join((entity.title,) + entity.aliases))
            self.tree.addTopLevelItem(item)
            if entity.id == selected:
                selected_item = item
        if selected_item is not None:
            self.tree.setCurrentItem(selected_item)
        self.newButton.setEnabled(bool(writable and self._creation_schemas()))
        self._apply_filter(self.filterEdit.text())
        self._selection_changed()

    def current_entity_id(self):
        item = self.tree.currentItem()
        return str(item.data(0, Qt.UserRole)) if item is not None else ""

    def _creation_schemas(self):
        return tuple(
            schema for schema in self.schemas
            if (
                not self.creatableTypes
                or schema.type in self.creatableTypes
            )
            and (
                not self.acceptedTypes
                or schema.type in self.acceptedTypes
            )
            and schema.type not in self.excludedTypes
        )

    def _show_create_menu(self):
        schemas = self._creation_schemas()
        if len(schemas) == 1:
            self.createRequested.emit(schemas[0].type)
            return
        menu = QMenu(self)
        for schema in schemas:
            action = menu.addAction(schema.label)
            action.triggered.connect(
                lambda _checked=False, entity_type=schema.type:
                    self.createRequested.emit(entity_type)
            )
        menu.exec_(
            self.newButton.mapToGlobal(self.newButton.rect().bottomLeft())
        )

    def _apply_filter(self, text):
        query = " ".join(str(text).split()).casefold()
        visible = 0
        by_id = {entity.id: entity for entity in self.entities}
        for row in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(row)
            entity = by_id.get(str(item.data(0, Qt.UserRole)))
            surfaces = (
                (entity.title,) + entity.aliases if entity is not None else ()
            )
            hidden = bool(query) and not any(
                query in value.casefold() for value in surfaces
            )
            item.setHidden(hidden)
            visible += int(not hidden)
        self.countLabel.setText(
            self.tr("{} shown / {} total").format(
                visible, len(self.entities)
            )
        )

    def _selection_changed(self):
        identifier = self.current_entity_id()
        self.editButton.setEnabled(bool(identifier))
        self.deleteButton.setEnabled(
            bool(identifier and identifier in self.editableIds)
        )

    def _edit_item(self, item, _column):
        identifier = str(item.data(0, Qt.UserRole))
        if identifier:
            self.editRequested.emit(identifier)

    def _edit_current(self):
        identifier = self.current_entity_id()
        if identifier:
            self.editRequested.emit(identifier)

    def _delete_current(self):
        identifier = self.current_entity_id()
        if identifier:
            self.deleteRequested.emit(identifier)


class EntityEditorPanel(QWidget):
    """Stable dock content into which the selected entity form is mounted."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("entityEditorPanel")
        self.setMinimumSize(260, 180)
        self._editor = None
        self.placeholder = QLabel(
            self.tr(
                "Select an entity from an entity browser, then choose Edit."
            ),
            self,
        )
        self.placeholder.setObjectName("entityEditorPlaceholder")
        self.placeholder.setWordWrap(True)
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setAccessibleName(self.tr("No entity selected"))
        self.scrollArea = QScrollArea(self)
        self.scrollArea.setObjectName("entityEditorScrollArea")
        self.scrollArea.setAccessibleName(self.tr("Entity editor form"))
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setFrameShape(QScrollArea.NoFrame)
        self.scrollArea.hide()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self.placeholder, 1)
        self._layout.addWidget(self.scrollArea, 1)

    @property
    def editor(self):
        return self._editor

    def set_editor(self, editor):
        self.clear()
        self._editor = editor
        self.placeholder.hide()
        editor.setParent(self)
        editor.setWindowFlags(Qt.Widget)
        editor.setWindowModality(Qt.NonModal)
        editor.setMinimumSize(520, 520)
        self.scrollArea.setWidget(editor)
        self.scrollArea.show()
        editor.destroyed.connect(self._editor_destroyed)
        editor.show()

    def clear(self):
        editor = self._editor
        self._editor = None
        if editor is not None:
            if self.scrollArea.widget() is editor:
                self.scrollArea.takeWidget()
            editor.setParent(None)
            editor.deleteLater()
        self.scrollArea.hide()
        self.placeholder.show()

    def _editor_destroyed(self, _object=None):
        self._editor = None
        self.scrollArea.hide()
        self.placeholder.show()


def build_entity_editor(_context, parent):
    return EntityEditorPanel(parent)


def build_project_entities(context, parent):
    return EntityBrowserPanel(
        context.translate("Project"),
        accepted_types=("project",),
        parent=parent,
    )


def build_character_entities(context, parent):
    return EntityBrowserPanel(
        context.translate("Characters"),
        accepted_types=("character",),
        creatable_types=("character",),
        parent=parent,
    )


def build_plot_entities(context, parent):
    return EntityBrowserPanel(
        context.translate("Plots"),
        accepted_types=("plot",),
        creatable_types=("plot",),
        parent=parent,
    )


def build_world_entities(context, parent):
    return EntityBrowserPanel(
        context.translate("World & entities"),
        excluded_types=("project", "character", "plot"),
        creatable_types=(
            "world", "place", "object", "organization", "concept",
            "event", "entity",
        ),
        parent=parent,
    )
