"""Accessible Qt rendering for transport-neutral plugin UI documents."""

import logging
import uuid

from dataclasses import replace

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from manuskript.plugins.ui_contract import (
    UiControlKind,
    UiDocument,
    UiEvent,
    UiEventKind,
    UiResponse,
)


LOGGER = logging.getLogger(__name__)


class StaticUiController:
    """Host-local controller for a declaration containing its whole UI."""

    def __init__(self, document):
        if not isinstance(document, UiDocument):
            raise TypeError("Declarative panels require a UI document.")
        self.document = document

    def open(self, _scope, session_id):
        return UiResponse(self.document)

    def event(self, event):
        self.document = replace(
            self.document,
            revision=max(self.document.revision + 1, event.document_revision + 1),
            controls=_replace_control_value(
                self.document.controls, event.control_id, event.value
            ),
        )
        return UiResponse(self.document)

    def close(self, _session_id):
        return None


class _TaskSignals(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(object)


class _Task(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = _TaskSignals()

    def run(self):
        try:
            result = self.operation()
        except Exception as error:
            self.signals.failed.emit(error)
        else:
            self.signals.finished.emit(result)


class DeclarativeUiWidget(QScrollArea):
    """Render one plugin document without accepting a plugin-owned QWidget."""

    def __init__(self, controller, scope, parent=None, thread_pool=None):
        super().__init__(parent)
        self.controller = controller
        self.scope = str(scope)
        self.sessionId = str(uuid.uuid4())
        self.threadPool = thread_pool or QThreadPool.globalInstance()
        self.document = None
        self.controls = {}
        self._busy = False
        self._closed = False
        self._tasks = set()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setAccessibleName(self.tr("Plugin panel"))

        self.content = QWidget(self)
        self.layout = QVBoxLayout(self.content)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.status = QLabel(self.tr("Loading plugin panel…"), self.content)
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        self.status.setAccessibleName(self.tr("Plugin panel status"))
        self.layout.addWidget(self.status)
        self.layout.addStretch(1)
        self.setWidget(self.content)
        self._submit(
            lambda: self.controller.open(self.scope, self.sessionId),
            self._opened,
        )

    def closeEvent(self, event):
        self._closed = True
        try:
            self.controller.close(self.sessionId)
        except Exception:
            LOGGER.exception("Declarative plugin UI close failed.")
        super().closeEvent(event)

    def _opened(self, response):
        self._accept_response(response, rebuild=True)

    def _accept_response(self, response, rebuild=False):
        if not isinstance(response, UiResponse):
            self._failed(TypeError("Plugin UI operation returned no UI response."))
            return
        if (
            self.document is not None
            and response.document.revision < self.document.revision
        ):
            return
        structure_changed = (
            self.document is None
            or _structure(self.document) != _structure(response.document)
        )
        self.document = response.document
        if rebuild or structure_changed:
            self._build_document(response.document)
        else:
            self._apply_values(response.document.controls)
        self.status.setText(str(response.message))
        self.status.setVisible(bool(response.message))
        if response.focus and response.focus in self.controls:
            self.controls[response.focus].setFocus(Qt.OtherFocusReason)

    def _build_document(self, document):
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.controls = {}
        self.status = QLabel("", self.content)
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        self.status.setAccessibleName(self.tr("Plugin panel status"))
        self.status.setVisible(False)
        self.layout.addWidget(self.status)
        for control in document.controls:
            self._add_control(self.layout, control)
        self.layout.addStretch(1)

    def _add_control(self, layout, control):
        if not control.visible:
            return
        if control.kind is UiControlKind.GROUP:
            group = QGroupBox(str(control.label), self.content)
            group.setAccessibleName(str(control.accessible_name or control.label))
            group_layout = QVBoxLayout(group)
            for child in control.children:
                self._add_control(group_layout, child)
            layout.addWidget(group)
            self.controls[control.id] = group
            return

        widget = self._widget(control)
        widget.setObjectName("pluginUi." + control.id)
        widget.setAccessibleName(str(control.accessible_name))
        description = str(control.description)
        if control.error:
            description = "{} {}".format(
                description,
                self.tr("Error: {}").format(control.error),
            ).strip()
        widget.setAccessibleDescription(description)
        widget.setEnabled(bool(control.enabled))
        self.controls[control.id] = widget

        if control.kind in (
            UiControlKind.CHECKBOX,
            UiControlKind.BUTTON,
            UiControlKind.MESSAGE,
            UiControlKind.PROGRESS,
        ):
            layout.addWidget(widget)
            return
        row = QWidget(self.content)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        label_text = str(control.label) + (" *" if control.required else "")
        label = QLabel(label_text, row)
        label.setTextFormat(Qt.PlainText)
        label.setBuddy(widget)
        label.setAccessibleName(label_text)
        row_layout.addWidget(label)
        row_layout.addWidget(widget, 1)
        layout.addWidget(row)
        if control.error:
            error = QLabel(
                self.tr("Error: {}").format(control.error),
                self.content,
            )
            error.setWordWrap(True)
            error.setTextFormat(Qt.PlainText)
            error.setAccessibleName(
                self.tr("Error for {}").format(control.label)
            )
            layout.addWidget(error)

    def _widget(self, control):
        kind = control.kind
        if kind is UiControlKind.TEXT:
            widget = QLineEdit(self.content)
            widget.setText("" if control.value is None else str(control.value))
            widget.editingFinished.connect(
                lambda c=control, w=widget: self._event(
                    c, UiEventKind.CHANGE, w.text()
                )
            )
            return widget
        if kind is UiControlKind.CHECKBOX:
            widget = QCheckBox(str(control.label), self.content)
            widget.setChecked(bool(control.value))
            widget.toggled.connect(
                lambda value, c=control: self._event(
                    c, UiEventKind.CHANGE, bool(value)
                )
            )
            return widget
        if kind is UiControlKind.INTEGER:
            widget = QSpinBox(self.content)
            widget.setRange(
                int(control.minimum if control.minimum is not None else -2147483647),
                int(control.maximum if control.maximum is not None else 2147483647),
            )
            widget.setValue(int(control.value or 0))
            widget.editingFinished.connect(
                lambda c=control, w=widget: self._event(
                    c, UiEventKind.CHANGE, w.value()
                )
            )
            return widget
        if kind is UiControlKind.NUMBER:
            widget = QDoubleSpinBox(self.content)
            widget.setRange(
                float(control.minimum if control.minimum is not None else -1e12),
                float(control.maximum if control.maximum is not None else 1e12),
            )
            widget.setValue(float(control.value or 0.0))
            widget.editingFinished.connect(
                lambda c=control, w=widget: self._event(
                    c, UiEventKind.CHANGE, w.value()
                )
            )
            return widget
        if kind is UiControlKind.CHOICE:
            widget = QComboBox(self.content)
            for choice in control.choices:
                widget.addItem(str(choice.label), choice.value)
            index = next((
                index for index, choice in enumerate(control.choices)
                if choice.value == control.value
            ), 0)
            widget.setCurrentIndex(index)
            widget.currentIndexChanged.connect(
                lambda _index, c=control, w=widget: self._event(
                    c, UiEventKind.CHANGE, w.currentData()
                )
            )
            return widget
        if kind is UiControlKind.LIST:
            widget = QListWidget(self.content)
            for item in control.items:
                row = QListWidgetItem(str(item.label), widget)
                row.setData(Qt.UserRole, item.id)
                row.setFlags(
                    row.flags() if item.enabled else row.flags() & ~Qt.ItemIsEnabled
                )
                row.setSelected(item.id == control.value)
            widget.itemSelectionChanged.connect(
                lambda c=control, w=widget: self._event(
                    c,
                    UiEventKind.SELECT,
                    (
                        w.selectedItems()[0].data(Qt.UserRole)
                        if w.selectedItems() else None
                    ),
                )
            )
            if control.reorderable:
                widget.setDragDropMode(QAbstractItemView.InternalMove)
                widget.model().rowsMoved.connect(
                    lambda *_args, c=control, w=widget: self._event(
                        c, UiEventKind.REORDER, tuple(
                            w.item(index).data(Qt.UserRole)
                            for index in range(w.count())
                        )
                    )
                )
            return widget
        if kind is UiControlKind.TABLE:
            widget = QTableWidget(self.content)
            widget.setColumnCount(len(control.columns))
            widget.setHorizontalHeaderLabels([
                str(column.label) for column in control.columns
            ])
            widget.setRowCount(len(control.items))
            for row_number, item in enumerate(control.items):
                for column_number, column in enumerate(control.columns):
                    cell = QTableWidgetItem(str(item.cells.get(column.id, "")))
                    cell.setData(Qt.UserRole, item.id)
                    widget.setItem(row_number, column_number, cell)
            widget.setEditTriggers(QTableWidget.NoEditTriggers)
            widget.itemSelectionChanged.connect(
                lambda c=control, w=widget: self._event(
                    c, UiEventKind.SELECT, _selected_table_id(w)
                )
            )
            return widget
        if kind is UiControlKind.TREE:
            widget = QTreeWidget(self.content)
            headers = control.columns or ()
            widget.setHeaderLabels(
                [str(column.label) for column in headers]
                or [str(control.label)]
            )
            for item in control.items:
                _add_tree_item(widget, item, headers)
            widget.itemSelectionChanged.connect(
                lambda c=control, w=widget: self._event(
                    c,
                    UiEventKind.SELECT,
                    (
                        w.selectedItems()[0].data(0, Qt.UserRole)
                        if w.selectedItems() else None
                    ),
                )
            )
            if control.reorderable:
                widget.setDragDropMode(QAbstractItemView.InternalMove)
                widget.model().rowsMoved.connect(
                    lambda *_args, c=control, w=widget: self._event(
                        c, UiEventKind.REORDER, _tree_order(w)
                    )
                )
            return widget
        if kind is UiControlKind.BUTTON:
            widget = QPushButton(str(control.label), self.content)
            widget.clicked.connect(
                lambda _checked=False, c=control: self._event(
                    c, UiEventKind.ACTIVATE, None
                )
            )
            return widget
        if kind is UiControlKind.PROGRESS:
            widget = QProgressBar(self.content)
            widget.setRange(
                int(control.minimum or 0),
                int(control.maximum if control.maximum is not None else 100),
            )
            widget.setValue(int(control.value or 0))
            widget.setFormat(str(control.label or "%p%"))
            return widget
        if kind is UiControlKind.MESSAGE:
            widget = QLabel(str(control.value or control.label), self.content)
            widget.setWordWrap(True)
            widget.setTextFormat(Qt.PlainText)
            return widget
        raise ValueError("Unsupported plugin UI control {}.".format(kind.value))

    def _event(self, control, kind, value):
        if self._busy or self.document is None:
            return
        event = UiEvent(
            self.sessionId,
            self.document.revision,
            control.id,
            kind,
            value,
        )
        self._submit(lambda: self.controller.event(event), self._accept_response)

    def _submit(self, operation, completed):
        if self._busy:
            return
        self._busy = True
        self.content.setEnabled(False)
        task = _Task(operation)
        self._tasks.add(task)

        def finish(result):
            self._tasks.discard(task)
            self._busy = False
            if self._closed:
                return
            self.content.setEnabled(True)
            completed(result)

        def fail(error):
            self._tasks.discard(task)
            self._busy = False
            if self._closed:
                return
            self.content.setEnabled(True)
            self._failed(error)

        task.signals.finished.connect(finish)
        task.signals.failed.connect(fail)
        self.threadPool.start(task)

    def _failed(self, error):
        LOGGER.exception(
            "Declarative plugin UI operation failed: %s: %s",
            type(error).__name__,
            error,
            exc_info=(type(error), error, error.__traceback__),
        )
        self.status.setText(
            self.tr("This plugin panel could not be updated.")
            + "\n{}: {}".format(type(error).__name__, error)
        )
        self.status.setVisible(True)

    def _apply_values(self, controls):
        # Rebuilding on a structural change is deliberate. For a value-only
        # response, update only controls that can do so without emitting a
        # second user event or destroying keyboard focus.
        for control in _walk_controls(controls):
            widget = self.controls.get(control.id)
            if widget is None:
                continue
            blocked = widget.blockSignals(True)
            try:
                if isinstance(widget, QLineEdit):
                    widget.setText("" if control.value is None else str(control.value))
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(bool(control.value))
                elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                    widget.setValue(control.value or 0)
                elif isinstance(widget, QComboBox):
                    index = widget.findData(control.value)
                    if index >= 0:
                        widget.setCurrentIndex(index)
                elif isinstance(widget, QProgressBar):
                    widget.setValue(int(control.value or 0))
            finally:
                widget.blockSignals(blocked)
            widget.setEnabled(bool(control.enabled))
            widget.setVisible(bool(control.visible))


def build_static_ui_widget(document, parent=None):
    return DeclarativeUiWidget(
        StaticUiController(document), "static", parent=parent
    )


def _walk_controls(controls):
    for control in controls:
        yield control
        yield from _walk_controls(control.children)


def _replace_control_value(controls, control_id, value):
    return tuple(
        replace(
            control,
            value=value if control.id == control_id else control.value,
            children=_replace_control_value(
                control.children, control_id, value
            ),
        )
        for control in controls
    )


def _structure(document):
    return _structure_controls(document.controls)


def _structure_controls(controls):
    return tuple(
        replace(
            control,
            value=None,
            children=_structure_controls(control.children),
        )
        for control in controls
    )


def _selected_table_id(table):
    items = table.selectedItems()
    return items[0].data(Qt.UserRole) if items else None


def _add_tree_item(parent, item, columns):
    values = (
        [str(item.cells.get(column.id, "")) for column in columns]
        if columns else [str(item.label)]
    )
    row = QTreeWidgetItem(parent, values)
    row.setData(0, Qt.UserRole, item.id)
    row.setDisabled(not item.enabled)
    for child in item.children:
        _add_tree_item(row, child, columns)


def _tree_order(tree):
    def item_value(item):
        return {
            "id": item.data(0, Qt.UserRole),
            "children": tuple(
                item_value(item.child(index))
                for index in range(item.childCount())
            ),
        }

    return tuple(
        item_value(tree.topLevelItem(index))
        for index in range(tree.topLevelItemCount())
    )
