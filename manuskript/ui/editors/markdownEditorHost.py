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
    MarkdownPresentationMode,
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
        self.pageWizard = None
        self.pageWizardFactory = None
        self.pageWizardErrorHandler = None
        self._wizardRefreshPending = False
        self._configuredMaximumWidth = QWIDGETSIZE_MAX
        self._maximumWidthOverride = None
        self.addWidget(source_editor)
        source_editor.setPresentationHost(self)
        source_editor.document().contentsChanged.connect(
            self._sourceChanged
        )

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

    def setPresentationMode(self, mode):
        mode = MarkdownPresentationMode.from_value(mode)
        target = self._viewForMode(mode)
        previous = self.currentWidget()

        if previous is not target and hasattr(previous, "setActive"):
            previous.setActive(False)

        self.setCurrentWidget(target)
        if hasattr(target, "setActive"):
            target.setActive(True)
        self.setFocusProxy(target)
        self.currentViewChanged.emit(target)
        return target if target is not self.sourceEditor else None

    def _viewForMode(self, mode):
        if mode is MarkdownPresentationMode.READING:
            return self._ensureReadingView()
        if (
            mode is MarkdownPresentationMode.LIVE_PREVIEW
            and self.pageWizardFactory is not None
        ):
            return self._ensurePageWizard()
        return self.sourceEditor

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

    def setPageWizardFactory(self, factory, error_handler=None):
        """Install an item-specific structured editor factory.

        Page wizard widgets are isolated from the canonical QTextDocument.
        They receive source through ``load_source(str)`` and may request one
        explicit replacement through an ``applyRequested(str)`` signal.
        """
        self.pageWizardErrorHandler = error_handler
        if factory is self.pageWizardFactory:
            return
        refresh_live_view = (
            self.currentWidget() is self.pageWizard
            or self.sourceEditor.presentationMode
            is MarkdownPresentationMode.LIVE_PREVIEW
        )
        if self.pageWizard is not None:
            self.removeWidget(self.pageWizard)
            self.pageWizard.deleteLater()
            self.pageWizard = None
        self.pageWizardFactory = factory
        if refresh_live_view:
            self.setPresentationMode(
                MarkdownPresentationMode.LIVE_PREVIEW
            )

    def _ensurePageWizard(self):
        if self.pageWizard is not None:
            return self.pageWizard
        try:
            wizard = self.pageWizardFactory()
            if not isinstance(wizard, QWidget):
                raise TypeError(
                    "Page wizard factories must return QWidget instances."
                )
            load_source = getattr(wizard, "load_source", None)
            apply_requested = getattr(wizard, "applyRequested", None)
            if not callable(load_source) or not hasattr(
                apply_requested, "connect"
            ):
                raise TypeError(
                    "Page wizards require load_source(source) and an "
                    "applyRequested(str) signal."
                )
            apply_requested.connect(self._applyWizardSource)
        except Exception as error:
            if self.pageWizardErrorHandler is not None:
                self.pageWizardErrorHandler(error)
            wizard = QLabel(
                self.tr("The page wizard could not be loaded: {}")
                .format(error),
                self,
            )
            wizard.setWordWrap(True)
            wizard.setAlignment(Qt.AlignCenter)
        self.pageWizard = wizard
        self.addWidget(wizard)
        self._loadWizardSource()
        return wizard

    def _sourceChanged(self):
        if self.pageWizard is None or self._wizardRefreshPending:
            return
        self._wizardRefreshPending = True
        QTimer.singleShot(0, self._loadWizardSource)

    def _loadWizardSource(self):
        self._wizardRefreshPending = False
        if self.pageWizard is None:
            return
        load_source = getattr(self.pageWizard, "load_source", None)
        if not callable(load_source):
            return
        try:
            load_source(self.sourceEditor.toPlainText())
        except Exception as error:
            if self.pageWizardErrorHandler is not None:
                self.pageWizardErrorHandler(error)

    def _applyWizardSource(self, source):
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
