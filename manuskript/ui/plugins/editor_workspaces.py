import logging

from functools import partial

from PyQt5.QtCore import QModelIndex, QObject, QPoint, Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence, QTextCursor
from PyQt5.QtWidgets import (
    QAction,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QShortcut,
    QVBoxLayout,
    QWidget,
)

from manuskript.enums import Outline
from manuskript.models.outlineItem import outlineItem
from manuskript.plugins.api import EditorWorkspaceContext, WorkspaceDocument
from manuskript.plugins.capabilities import (
    CAPABILITY_EDITOR_CONTROL,
    CAPABILITY_OUTLINE_READ,
    CAPABILITY_OUTLINE_WRITE,
)
from manuskript.ui.plugins.story_capabilities import (
    build_story_capability,
)
from manuskript.ui.connections import SignalConnectionRegistry
from manuskript.ui.editors.markdownEditorHost import MarkdownEditorHost
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationDefaults,
    MarkdownPresentationMode,
    MarkdownPresentationState,
)
from manuskript.ui.views.MDEditView import MDEditView


LOGGER = logging.getLogger(__name__)


def _discard_endpoint(endpoints, endpoint, *_args):
    """Forget an endpoint without dereferencing its QObject owner.

    A host widget can outlive the factory's C++ object during project or
    interpreter teardown.  Connecting ``destroyed`` to a bound factory method
    then asks PyQt to invoke a deleted QObject wrapper.  The list is ordinary
    Python state and is all cleanup needs, so the callback captures only that.
    """
    if endpoint in endpoints:
        endpoints.remove(endpoint)


class WorkspaceOutlineGateway(QObject):
    """Guard project-outline mutations exposed to editor workspaces."""

    documentChanged = pyqtSignal(str)
    structureChanged = pyqtSignal()
    selectionChanged = pyqtSignal(object)

    def __init__(self, model, tree, parent=None):
        super().__init__(parent)
        self.model = model
        self.tree = tree
        self._connections = SignalConnectionRegistry()
        self._connections.connect(model.dataChanged, self._data_changed)
        for signal_name in (
            "rowsInserted",
            "rowsRemoved",
            "modelReset",
            "layoutChanged",
        ):
            signal = getattr(model, signal_name, None)
            if signal is not None:
                self._connections.connect(signal, self._structure_changed)
        selection_model = tree.selectionModel()
        if selection_model is not None:
            self._connections.connect(
                selection_model.selectionChanged,
                self._selection_changed,
            )

    def close(self):
        self._connections.disconnect_all()

    def selected_item_ids(self):
        selection_model = self.tree.selectionModel()
        if selection_model is None:
            return ()
        indexes = selection_model.selectedRows(Outline.title)
        if not indexes:
            current = self.tree.currentIndex()
            indexes = [current] if current.isValid() else []
        return tuple(dict.fromkeys(
            str(index.internalPointer().ID())
            for index in indexes
            if index.isValid()
        ))

    def documents(self):
        result = []

        def visit(item):
            if item is not self.model.rootItem:
                result.append(self._snapshot(item))
            for child in item.children():
                visit(child)

        visit(self.model.rootItem)
        return tuple(result)

    def document(self, item_id):
        item = self.model.getItemByID(str(item_id))
        return self._snapshot(item) if item is not None else None

    def set_text(self, item_id, text):
        return self._set(item_id, Outline.text, str(text), text_only=True)

    def set_title(self, item_id, title):
        return self._set(item_id, Outline.title, str(title))

    def set_compile(self, item_id, compile_document):
        return self._set(
            item_id,
            Outline.compile,
            2 if bool(compile_document) else 0,
        )

    def set_compile_many(self, compile_by_id):
        changed = False
        batch = getattr(self.model, "batchWordCountUpdates", None)
        context = batch() if callable(batch) else _NullContext()
        with context:
            for item_id, value in compile_by_id.items():
                changed = self.set_compile(item_id, value) or changed
        return changed

    def create_text_document(
            self, title, text="", parent_id=None, after_id=None,
            compile_document=False):
        """Create ordinary outline prose for a plugin-managed relationship."""
        parent_index = QModelIndex()
        if after_id is not None:
            after_index = self.model.getIndexByID(str(after_id))
            if not after_index.isValid():
                raise KeyError(
                    "Unknown outline item {!r}.".format(after_id)
                )
            parent_index = after_index.parent()
        elif parent_id is not None:
            parent_index = self.model.getIndexByID(str(parent_id))
            if not parent_index.isValid():
                raise KeyError(
                    "Unknown outline parent {!r}.".format(parent_id)
                )
            if not parent_index.internalPointer().isFolder():
                raise ValueError("New text documents require a folder parent.")

        item = outlineItem(
            title=str(title),
            _type="md",
            settings=getattr(self.model, "settings", None),
        )
        item.setData(Outline.text, str(text))
        item.setData(
            Outline.compile,
            2 if bool(compile_document) else 0,
        )
        if after_id is not None:
            inserted = self.model.insertItem(
                item,
                after_index.row() + 1,
                parent_index,
            )
        else:
            inserted = self.model.insertItem(
                item,
                self.model.rowCount(parent_index),
                parent_index,
            )
        if not inserted:
            raise RuntimeError("The outline rejected the new text document.")
        return self._snapshot(item)

    def duplicate_text_document(
            self, item_id, title=None, compile_document=False):
        source = self.document(item_id)
        if source is None:
            raise KeyError("Unknown outline item {!r}.".format(item_id))
        if source.kind != "md":
            raise ValueError("Only text documents can be duplicated.")
        return self.create_text_document(
            title=title or "{} copy".format(source.title),
            text=source.text,
            after_id=source.id,
            compile_document=compile_document,
        )

    def _set(self, item_id, column, value, text_only=False):
        item = self.model.getItemByID(str(item_id))
        if item is None:
            raise KeyError("Unknown outline item {!r}.".format(item_id))
        if text_only and not item.isText():
            raise ValueError("Only text outline items have editable prose.")
        index = self.model.getIndexByID(str(item_id), column=column)
        if not index.isValid():
            raise KeyError("Unknown outline item {!r}.".format(item_id))
        if index.data(Qt.EditRole) == value:
            return False
        self.model.setData(index, value, Qt.EditRole)
        return True

    def _snapshot(self, item):
        parent = item.parent()
        return WorkspaceDocument(
            id=str(item.ID()),
            title=str(item.title()),
            kind=str(item.type()),
            text=str(item.text() or "") if item.isText() else "",
            compile=bool(item.compile()),
            parent_id=(
                str(parent.ID())
                if parent is not None and parent is not self.model.rootItem
                else None
            ),
        )

    def _data_changed(self, top_left, bottom_right, *_args):
        parent = top_left.parent()
        for row in range(top_left.row(), bottom_right.row() + 1):
            index = self.model.index(row, Outline.title, parent)
            if index.isValid():
                self.documentChanged.emit(
                    str(index.internalPointer().ID())
                )

    def _structure_changed(self, *_args):
        self.structureChanged.emit()

    def _selection_changed(self, *_args):
        self.selectionChanged.emit(self.selected_item_ids())


class ReadOnlyOutlineView:
    """The manuscript as a plugin that only reads it sees the manuscript.

    Not the gateway with its mutators disabled: the mutators are not here
    at all. A plugin calling one gets an AttributeError naming the method
    it should not have called, and anything asking whether it may write --
    including the plugin itself -- is told the truth by ``hasattr``.

    The signals are the gateway's own, passed through rather than
    re-emitted. Watching the manuscript change is reading it.
    """

    def __init__(self, gateway):
        self._gateway = gateway
        self.documentChanged = gateway.documentChanged
        self.structureChanged = gateway.structureChanged
        self.selectionChanged = gateway.selectionChanged

    def selected_item_ids(self):
        return self._gateway.selected_item_ids()

    def documents(self):
        return self._gateway.documents()

    def document(self, item_id):
        return self._gateway.document(item_id)


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class WorkspaceEditorEndpoint(QObject):
    """Public, geometry-aware façade around one native Markdown editor."""

    scrolled = pyqtSignal(int)
    cursorChanged = pyqtSignal(int, int)
    selectionChanged = pyqtSignal(int, int)
    textChanged = pyqtSignal()
    #: The document has finished laying itself out and now reports a real
    #: size. Anything a workspace measures in pixels before this -- block
    #: positions, scroll extents -- describes a document that has not been
    #: laid out, so a plugin waits for this rather than guessing.
    layoutChanged = pyqtSignal()

    def __init__(
            self, item_id, editor, host, presentation,
            markup_profile=None, page_type=None, parent=None):
        super().__init__(parent or host)
        self.item_id = str(item_id)
        self.widget = host
        self.editor = editor
        self.presentation = presentation
        self.markup_profile = markup_profile
        self.page_type = page_type
        scrollbar = editor.verticalScrollBar()
        scrollbar.valueChanged.connect(self.scrolled)
        editor.cursorPositionChanged.connect(self._cursor_changed)
        editor.selectionChanged.connect(self._selection_changed)
        editor.textChanged.connect(self._text_changed)
        #: Whether the layout has reported a size since the text last
        #: changed. Asking the document how big it is does not answer this:
        #: it answers with whatever it last computed, which for text that has
        #: just been set is a size describing the text before it.
        self._laid_out = False
        layout = editor.document().documentLayout()
        if layout is not None:
            layout.documentSizeChanged.connect(self._document_size_changed)

    @property
    def title(self):
        index = self.editor.currentIndex()
        return (
            str(index.internalPointer().title())
            if index.isValid()
            else ""
        )

    def text(self):
        return self.editor.toPlainText()

    def selected_text(self):
        return self.editor.textCursor().selectedText().replace("\u2029", "\n")

    def selection_range(self):
        cursor = self.editor.textCursor()
        return (cursor.selectionStart(), cursor.selectionEnd())

    def set_cursor_position(self, position, anchor=None):
        text_length = len(self.text())
        position = max(0, min(int(position), text_length))
        cursor = self.editor.textCursor()
        if anchor is None:
            cursor.setPosition(position)
        else:
            anchor = max(0, min(int(anchor), text_length))
            cursor.setPosition(anchor)
            cursor.setPosition(position, QTextCursor.KeepAnchor)
        self.editor.setTextCursor(cursor)

    def insert_at_cursor(self, text):
        if self.editor.editingLocked:
            raise PermissionError("This workspace editor is locked.")
        self.editor.textCursor().insertText(str(text))
        self.submit()

    def replace_text(self, text):
        if self.editor.editingLocked:
            raise PermissionError("This workspace editor is locked.")
        self.editor.setPlainText(str(text))
        self.submit()

    def submit(self):
        self.editor.submit()

    @property
    def editing_locked(self):
        return self.editor.editingLocked

    def set_editing_locked(self, locked):
        self.editor.setEditingLocked(locked)

    def set_presentation_mode(self, mode):
        mode = MarkdownPresentationMode.from_value(mode)
        if mode not in (
            MarkdownPresentationMode.SOURCE,
            MarkdownPresentationMode.FORMATTED_SOURCE,
        ):
            raise ValueError(
                "Workspace editors support source presentation modes only."
            )
        self.presentation.set_mode(mode)

    def _text_changed(self):
        self._laid_out = False
        self.textChanged.emit()

    def _document_size_changed(self, *_args):
        self._laid_out = True
        self.layoutChanged.emit()

    @property
    def layout_is_ready(self):
        """Whether this pane's geometry describes a laid-out document.

        Until the layout has run, block positions and the scroll extent
        describe nothing: a document of eighty blocks can report a scroll
        maximum of zero. A workspace that places panes against those numbers
        gets an answer the scrollbar then silently clamps into something
        plausible and wrong.
        """

        return self._laid_out

    def set_maximum_text_width(self, width):
        self.widget.setMaximumWidthOverride(width)

    def clear_maximum_text_width(self):
        self.widget.clearMaximumWidthOverride()

    @property
    def viewport_width(self):
        return self.editor.viewport().width()

    @property
    def scroll_value(self):
        return self.editor.verticalScrollBar().value()

    @property
    def scroll_maximum(self):
        return self.editor.verticalScrollBar().maximum()

    def set_scroll_value(self, value):
        scrollbar = self.editor.verticalScrollBar()
        scrollbar.setValue(max(scrollbar.minimum(), min(
            int(value), scrollbar.maximum()
        )))

    @property
    def cursor_block(self):
        return self.editor.textCursor().blockNumber()

    @property
    def cursor_position(self):
        return self.editor.textCursor().position()

    @property
    def first_visible_block(self):
        return self.editor.cursorForPosition(QPoint(1, 1)).blockNumber()

    @property
    def first_visible_block_fraction(self):
        """How far the viewport top sits through its first visible block.

        A block number says which paragraph a reader is on but not where
        between two of them they are, which is the difference between panes
        that step paragraph by paragraph and panes that scroll together.
        """
        document = self.editor.document()
        block = document.findBlockByNumber(self.first_visible_block)
        if not block.isValid():
            return 0.0
        bounds = document.documentLayout().blockBoundingRect(block)
        if bounds.height() <= 0:
            return 0.0
        return max(0.0, min(
            (self.scroll_value - bounds.top()) / bounds.height(),
            1.0,
        ))

    @property
    def block_count(self):
        return self.editor.document().blockCount()

    def scroll_value_for_block(self, block_number, fraction=0.0):
        """The scroll value that puts a point inside a block at the top."""
        document = self.editor.document()
        block = document.findBlockByNumber(
            max(0, min(int(block_number), self.block_count - 1))
        )
        if not block.isValid():
            return self.scroll_value
        bounds = document.documentLayout().blockBoundingRect(block)
        fraction = max(0.0, min(float(fraction), 1.0))
        return round(bounds.top() + fraction * bounds.height())

    def scroll_value_for_text_offset(self, offset):
        """The scroll value that puts the block holding an offset at the top."""
        block = self.editor.document().findBlock(
            max(0, min(int(offset), len(self.text())))
        )
        if not block.isValid():
            return self.scroll_value
        return self.scroll_value_for_block(block.blockNumber())

    def scroll_to_block(self, block_number, fraction=0.0):
        self.set_scroll_value(
            self.scroll_value_for_block(block_number, fraction)
        )

    def scroll_to_text_offset(self, offset):
        self.set_scroll_value(self.scroll_value_for_text_offset(offset))

    def close(self):
        self.submit()

    def _cursor_changed(self):
        cursor = self.editor.textCursor()
        self.cursorChanged.emit(cursor.position(), cursor.blockNumber())

    def _selection_changed(self):
        self.selectionChanged.emit(*self.selection_range())


class WorkspaceEditorFactory(QObject):
    """Build native editor endpoints without exposing editor internals."""

    def __init__(self, editor_context, outline, parent=None):
        super().__init__(parent)
        self.editor_context = editor_context
        self.outline = outline
        self._endpoints = []

    def create(self, item_id, parent=None, editing_locked=False):
        document = self.outline.document(item_id)
        if document is None:
            raise KeyError("Unknown outline item {!r}.".format(item_id))
        if document.kind != "md":
            raise ValueError("Workspace editor panes require text items.")

        text_context = self.editor_context.text_editor
        editor = MDEditView(
            parent=None,
            settings=(text_context.settings if text_context else None),
        )
        if text_context is not None:
            editor.set_text_editor_context(text_context)
        host = MarkdownEditorHost(editor, parent)
        presentation = MarkdownPresentationState(
            MarkdownPresentationDefaults.load(text_context.settings)
            if text_context is not None
            else MarkdownPresentationMode.FORMATTED_SOURCE,
            parent=host,
        )
        editor.setPresentationState(presentation)

        markup_profile = None
        page_type = None
        if text_context is not None and text_context.markup_profiles is not None:
            markup_profile = text_context.markup_profiles.create_state(
                parent=host
            )
            editor.setMarkupProfileState(markup_profile)
        item = self.editor_context.outline_model.getItemByID(str(item_id))
        if text_context is not None and text_context.page_types is not None:
            page_type = text_context.page_types.create_state(
                item=item,
                parent=host,
            )
            editor.setPageTypeState(page_type)

        index = self.editor_context.outline_model.getIndexByID(
            str(item_id),
            column=Outline.text,
        )
        editor.setCurrentModelIndex(index)
        editor.setEditingLocked(editing_locked)
        endpoint = WorkspaceEditorEndpoint(
            item_id,
            editor,
            host,
            presentation,
            markup_profile=markup_profile,
            page_type=page_type,
            parent=host,
        )
        self._endpoints.append(endpoint)
        host.destroyed.connect(partial(
            _discard_endpoint, self._endpoints, endpoint,
        ))
        return endpoint

    def close_all(self):
        endpoints = tuple(self._endpoints)
        # Keep the list object stable: destroyed callbacks hold this ordinary
        # Python collection precisely so they never have to reach a factory
        # QObject whose C++ lifetime may already have ended.
        self._endpoints.clear()
        for endpoint in endpoints:
            endpoint.close()


class EditorWorkspaceShell(QFrame):
    """Accessible application-owned chrome around a plugin workspace."""

    def __init__(self, title, description, workspace, close_callback, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.setObjectName("editorWorkspaceShell")
        self.setFrameShape(QFrame.NoFrame)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        heading_layout = QHBoxLayout()
        heading = QLabel(title, self)
        heading.setObjectName("editorWorkspaceHeading")
        heading.setAccessibleName(title)
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        heading_layout.addWidget(heading)
        heading_layout.addStretch(1)
        close_button = QPushButton(self.tr("Close workspace"), self)
        close_button.setObjectName("closeEditorWorkspace")
        close_button.setToolTip(self.tr("Return to the normal editor"))
        close_button.setMinimumHeight(32)
        close_button.clicked.connect(close_callback)
        heading_layout.addWidget(close_button)
        layout.addLayout(heading_layout)
        layout.addWidget(workspace, 1)
        self.closeShortcut = QShortcut(
            QKeySequence(Qt.Key_Escape),
            self,
        )
        self.closeShortcut.activated.connect(close_callback)


class EditorWorkspaceHost(QObject):
    """Own plugin workspace actions and project-scoped lifecycles."""

    def __init__(self, views, runtime, menu, parent=None):
        super().__init__(parent or views.editor_host)
        self.views = views
        self.runtime = runtime
        self.menu = menu
        self.actions = {}
        self._menu_entries = []
        self._active_id = None
        self._active_plugin_id = None
        self._outline = None
        self._editors = None
        self._shell = None
        self._project_open = False
        self.refresh()

    def refresh(self):
        records = {
            record.id: record
            for record in self.runtime.registry.records("editor_workspace")
        }
        if self._active_id is not None and self._active_id not in records:
            self.close_workspace()
        for action in self._menu_entries:
            self.menu.removeAction(action)
            action.deleteLater()
        self._menu_entries = []
        self.actions = {}
        if records:
            separator = self.menu.addSeparator()
            self._menu_entries.append(separator)
        for contribution_id, record in sorted(
                records.items(),
                key=lambda value: value[1].contribution.descriptor.name):
            contribution = record.contribution
            action = QAction(contribution.action_label, self.menu)
            action.setObjectName("editorWorkspace.{}".format(contribution_id))
            action.setStatusTip(contribution.descriptor.description)
            action.setToolTip(contribution.descriptor.description)
            if contribution.shortcut:
                action.setShortcut(QKeySequence(contribution.shortcut))
            action.triggered.connect(
                partial(self.open_workspace, contribution_id)
            )
            self.menu.addAction(action)
            self._menu_entries.append(action)
            self.actions[contribution_id] = action
        self._update_action_states()

    def project_opened(self):
        self._project_open = True
        self._install_services()
        self._update_action_states()

    def prepare_project_close(self):
        self.close_workspace()
        self._release_services()
        self._project_open = False
        self._update_action_states()

    def open_workspace(self, contribution_id):
        if not self._project_open:
            return None
        record = next((
            value
            for value in self.runtime.registry.records("editor_workspace")
            if value.id == contribution_id
        ), None)
        if record is None:
            return None
        self._install_services()
        selected_ids = self._outline.selected_item_ids()
        contribution = record.contribution
        if not self._selection_allowed(contribution, selected_ids):
            self._update_action_states()
            return None

        self.close_workspace()
        self._install_services()
        context = EditorWorkspaceContext(
            plugin_id=record.plugin_id,
            project_file=self.views.project.current_file(),
            selected_item_ids=selected_ids,
            files=self.views.project.plugin_data().namespace(
                record.plugin_id,
                on_change=self.views.project.mark_changed,
            ),
            outline=self._granted_outline(record.plugin_id),
            editors=self._granted_editors(record.plugin_id),
            show_status=self.views.project.show_status,
            close_workspace=self.close_workspace,
            capability=partial(
                self._workspace_capability, record.plugin_id
            ),
        )
        try:
            workspace = contribution.workspace_factory(
                context,
                self.views.editor_host,
            )
            if not isinstance(workspace, QWidget):
                raise TypeError(
                    "Editor workspace factories must return QWidget instances."
                )
        except Exception as error:
            self._report_failure(contribution.descriptor, error)
            return None

        self._shell = EditorWorkspaceShell(
            contribution.descriptor.name,
            contribution.descriptor.description,
            workspace,
            self.close_workspace,
            parent=self.views.editor_host,
        )
        self._active_id = contribution_id
        self._active_plugin_id = record.plugin_id
        self.views.editor_host.showPluginWorkspace(self._shell)
        return self._shell

    def close_workspace(self):
        shell = self._shell
        workspace = getattr(shell, "workspace", None)
        prepare_close = getattr(workspace, "prepare_close", None)
        if callable(prepare_close):
            try:
                prepare_close()
            except Exception as error:
                self.views.project.show_status(
                    self.tr("Plugin workspace cleanup failed: {}").format(
                        error
                    ),
                    8000,
                    2,
                )
        if self._editors is not None:
            self._editors.close_all()
        self._shell = None
        self._active_id = None
        self._active_plugin_id = None
        self.views.editor_host.closePluginWorkspace()
        if shell is not None:
            shell.deleteLater()

    def close_plugin(self, plugin_id):
        if self._active_plugin_id == plugin_id:
            self.close_workspace()

    def _report_failure(self, descriptor, error):
        """Say a workspace could not be opened, without waiting for anybody.

        This was a modal dialog, and gating made the modal reachable in a
        new way: a plugin that declares nothing is handed no manuscript and
        no editors, so its factory raises on the first thing it reaches
        for. A modal there stops the application on a plugin's mistake, and
        in a test run stops it with nobody to press the button -- the same
        fault the panel host had, with the same fix.
        """
        message = self.views.translate(
            "The {} workspace could not be opened: {}"
        ).format(descriptor.name, error)
        LOGGER.warning(
            "Editor workspace %s failed to open: %s", descriptor.id, error,
        )
        self.views.project.show_status(message, 8000, 2)
        return message

    def _granted_outline(self, plugin_id):
        """As much of the manuscript as this plugin declared it needs.

        Registering an editor workspace used to be the whole negotiation:
        every workspace was handed the gateway that can rewrite any
        document's text and title, create documents and change what
        compiles, whether it asked or not. The one that ships uses five of
        those operations and never touches text or titles.

        Writing includes reading, so a plugin declaring outline.write need
        not also declare outline.read; declaring neither is a workspace
        that works on its own files and is given no manuscript at all.
        """
        if self.runtime.declares(plugin_id, CAPABILITY_OUTLINE_WRITE):
            return self._outline
        if self.runtime.declares(plugin_id, CAPABILITY_OUTLINE_READ):
            return ReadOnlyOutlineView(self._outline)
        return None

    def _granted_editors(self, plugin_id):
        """The editor factory, for a plugin that said it puts panes up."""
        if self.runtime.declares(plugin_id, CAPABILITY_EDITOR_CONTROL):
            return self._editors
        return None

    def _workspace_capability(self, plugin_id, name):
        manager = self.views.project.story_services()
        return build_story_capability(
            self.runtime,
            manager,
            plugin_id,
            name,
            source_gateway=self._outline,
        )

    def _install_services(self):
        if self._outline is not None:
            return
        context = self.views.editor_host.editor_context
        if context is None:
            return
        self._outline = WorkspaceOutlineGateway(
            context.outline_model,
            context.outline_tree,
            parent=self,
        )
        self._outline.selectionChanged.connect(self._update_action_states)
        self._editors = WorkspaceEditorFactory(
            context,
            self._outline,
            parent=self,
        )

    def _release_services(self):
        if self._editors is not None:
            self._editors.close_all()
            self._editors.deleteLater()
        self._editors = None
        if self._outline is not None:
            self._outline.close()
            self._outline.deleteLater()
        self._outline = None

    def _update_action_states(self, *_args):
        selected_ids = (
            self._outline.selected_item_ids()
            if self._outline is not None
            else ()
        )
        records = {
            record.id: record
            for record in self.runtime.registry.records("editor_workspace")
        }
        for contribution_id, action in self.actions.items():
            record = records.get(contribution_id)
            action.setEnabled(bool(
                self._project_open
                and record is not None
                and self._selection_allowed(
                    record.contribution,
                    selected_ids,
                )
            ))

    @staticmethod
    def _selection_allowed(contribution, selected_ids):
        count = len(selected_ids)
        return (
            count >= contribution.minimum_selection
            and (
                contribution.maximum_selection is None
                or count <= contribution.maximum_selection
            )
        )
