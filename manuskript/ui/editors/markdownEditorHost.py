from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import (
    QFrame,
    QLabel,
    QStackedWidget,
    QWIDGETSIZE_MAX,
    QWidget,
)

from manuskript.ui.editors.markdownPresentation import (
    PresentationModeDefinition,
    core_presentation_mode,
    presentation_mode_key,
)
from manuskript.ui.views.markdownReadingView import MarkdownReadingView


class MarkdownEditorHost(QStackedWidget):
    """Own the mutually exclusive views of one Markdown document."""

    currentViewChanged = pyqtSignal(object)

    def __init__(self, source_editor, parent=None):
        super().__init__(parent)
        self.setObjectName("markdownEditorHost")
        self.setFrameShape(QFrame.NoFrame)
        self.sourceEditor = source_editor
        self.readingView = None
        self.readingRenderer = None
        self._contributedViews = {}
        self._sourceRefreshPending = False
        self._sourceDocument = None
        self._configuredMaximumWidth = QWIDGETSIZE_MAX
        self._maximumWidthOverride = None
        self.addWidget(source_editor)
        source_editor.setPresentationHost(self)
        source_editor.documentReplaced.connect(
            self._sourceDocumentReplaced
        )
        self._sourceDocumentReplaced()

    def setConfiguredMaximumWidth(self, width):
        """Apply the user's editor width unless a workspace overrides it."""
        self._configuredMaximumWidth = int(width or QWIDGETSIZE_MAX)
        self._applyMaximumWidth()

    def setMaximumWidthOverride(self, width):
        """Temporarily give a workspace identical editor geometry."""
        self._maximumWidthOverride = int(width or QWIDGETSIZE_MAX)
        self._applyMaximumWidth()

    def clearMaximumWidthOverride(self):
        self._maximumWidthOverride = None
        self._applyMaximumWidth()

    @property
    def effectiveMaximumWidth(self):
        return (
            self._configuredMaximumWidth
            if self._maximumWidthOverride is None
            else self._maximumWidthOverride
        )

    def _applyMaximumWidth(self):
        self.setMaximumWidth(self.effectiveMaximumWidth)

    @property
    def canonicalEditor(self):
        return self.sourceEditor

    def setPresentationMode(self, mode, definition=None):
        mode = presentation_mode_key(mode)
        definition = definition or core_presentation_mode(mode)
        if definition is None or definition.key != mode:
            raise ValueError(
                "No presentation-mode declaration realizes {!r}."
                .format(getattr(mode, "value", mode))
            )
        target = self._viewForDefinition(definition)
        previous = self.currentWidget()

        if previous is not target and hasattr(previous, "setActive"):
            previous.setActive(False)

        self.setCurrentWidget(target)
        # A presentation view may be constructed only when it is first
        # selected. QStackedWidget normally sizes that new page on a later
        # layout event; under a constrained native screen that leaves the
        # visible view at QWidget's 100-pixel construction width for a frame
        # even though this host is already laid out. A completed mode switch
        # must return a usable view, so establish the stack's current geometry
        # synchronously. The stacked layout remains its owner afterwards.
        target.setGeometry(self.contentsRect())
        if hasattr(target, "setActive"):
            target.setActive(True)
        self.setFocusProxy(target)
        self.currentViewChanged.emit(target)
        return target if target is not self.sourceEditor else None

    def _viewForDefinition(self, definition):
        context = _PresentationViewContext(self)
        try:
            target = definition.view_factory(context, definition)
            if not isinstance(target, QWidget):
                raise TypeError(
                    "Presentation mode factories must return QWidget "
                    "instances."
                )
            return target
        except Exception as error:
            if definition.error_handler is not None:
                definition.error_handler(error)
            return self._errorView(definition, error)

    def _ensureReadingView(self):
        if self.readingView is None:
            self.readingView = MarkdownReadingView(
                self.sourceEditor,
                self,
            )
            self.addWidget(self.readingView)
            self.sourceEditor.readingView = self.readingView
            self.readingView.setRenderer(self.readingRenderer)
        return self.readingView

    def setReadingRenderer(self, renderer):
        self.readingRenderer = renderer
        if self.readingView is not None:
            self.readingView.setRenderer(renderer)

    def contributedView(self, mode):
        """The realized plugin view for a mode, or None if not built yet."""

        record = self._contributedViews.get(presentation_mode_key(mode))
        return record[1] if record is not None else None

    def ensureContributedView(self, definition):
        """Build one declared plugin view and bridge source explicitly.

        Contributed widgets never receive the canonical QTextDocument.  A
        view may consume snapshots through ``load_source(str)`` and may ask
        the owner to replace that source through an ``applyRequested(str)``
        signal.  Read-only views can omit the latter.
        """

        if not isinstance(definition, PresentationModeDefinition):
            raise TypeError("Contributed views require a mode declaration.")
        existing = self._contributedViews.get(definition.key)
        if existing is not None and existing[0] == definition:
            return existing[1]
        if existing is not None:
            self._discardContributedView(definition.key)
        try:
            if definition.widget_factory is None:
                raise TypeError(
                    "Contributed presentation modes require a widget factory."
                )
            view = definition.widget_factory()
            if not isinstance(view, QWidget):
                raise TypeError(
                    "Presentation mode factories must return QWidget "
                    "instances."
                )
            load_source = getattr(view, "load_source", None)
            if load_source is not None and not callable(load_source):
                raise TypeError("load_source must be callable when present.")
            apply_requested = getattr(view, "applyRequested", None)
            if apply_requested is not None:
                if not hasattr(apply_requested, "connect"):
                    raise TypeError(
                        "applyRequested must be a Qt signal when present."
                    )
                apply_requested.connect(self._applyContributedSource)
        except Exception as error:
            if definition.error_handler is not None:
                definition.error_handler(error)
            view = self._errorView(definition, error)
        self._contributedViews[definition.key] = (definition, view)
        if self.indexOf(view) < 0:
            self.addWidget(view)
        self._loadContributedSource(view)
        return view

    def setAvailableModes(self, definitions):
        """Release plugin widgets whose declarations are no longer active."""

        available = {
            definition.key: definition
            for definition in definitions
            if isinstance(definition.key, str)
        }
        for key, (definition, _view) in tuple(
            self._contributedViews.items()
        ):
            if available.get(key) != definition:
                self._discardContributedView(key)

    def _discardContributedView(self, key):
        _definition, view = self._contributedViews.pop(key)
        self.removeWidget(view)
        view.deleteLater()

    def _errorView(self, definition, error):
        view = QLabel(
            self.tr("The {} view could not be loaded: {}")
            .format(definition.label, error),
            self,
        )
        view.setWordWrap(True)
        view.setAlignment(Qt.AlignCenter)
        if self.indexOf(view) < 0:
            self.addWidget(view)
        return view

    def _sourceChanged(self):
        if self.readingView is not None:
            self.readingView.scheduleRefresh()
        if not self._contributedViews or self._sourceRefreshPending:
            return
        self._sourceRefreshPending = True
        QTimer.singleShot(0, self._loadContributedSources)

    def _sourceDocumentReplaced(self):
        """Observe the projection the source editor currently displays.

        Project binding replaces the QTextDocument created with the widget by
        a view-local projection from DocumentBufferRegistry. QTextEdit has no
        native document-changed signal, so textEditView publishes this one.
        Holding a connection to the construction document makes Reading and
        contributed views stale as soon as a real manuscript page is opened.
        """
        previous = self._sourceDocument
        if previous is not None:
            try:
                previous.contentsChanged.disconnect(self._sourceChanged)
            except (TypeError, RuntimeError):
                # setDocument may have deleted a document owned by the editor
                # before documentReplaced can describe its successor.
                pass
        self._sourceDocument = self.sourceEditor.document()
        self._sourceDocument.contentsChanged.connect(self._sourceChanged)
        self._sourceChanged()

    def _loadContributedSources(self):
        self._sourceRefreshPending = False
        for _definition, view in self._contributedViews.values():
            self._loadContributedSource(view)

    def _loadContributedSource(self, view):
        load_source = getattr(view, "load_source", None)
        if not callable(load_source):
            return
        try:
            load_source(self.sourceEditor.toPlainText())
        except Exception as error:
            definition = next((
                definition
                for definition, candidate in self._contributedViews.values()
                if candidate is view
            ), None)
            if definition is not None and definition.error_handler is not None:
                definition.error_handler(error)

    def _applyContributedSource(self, source):
        source = str(source)
        editor = self.sourceEditor
        if source == editor.toPlainText():
            return
        old_cursor = editor.textCursor()
        position = old_cursor.position()
        cursor = QTextCursor(editor.document())
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(source)
        cursor.endEditBlock()
        old_cursor.setPosition(min(position, len(source)))
        editor.setTextCursor(old_cursor)
        # Persist through the editor/model owner immediately. The wizard never
        # writes an outline item or project file directly.
        editor.submit()


class _PresentationViewContext:
    """Host-owned realization operations passed to catalogue factories."""

    def __init__(self, host):
        self._host = host

    @property
    def source_editor(self):
        return self._host.sourceEditor

    def reading_view(self):
        return self._host._ensureReadingView()

    def contributed_view(self, definition):
        return self._host.ensureContributedView(definition)
