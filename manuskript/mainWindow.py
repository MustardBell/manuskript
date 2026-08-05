#!/usr/bin/env python
# --!-- coding: utf8 --!--
import importlib
import os
import re

from PyQt5.Qt import qVersion, PYQT_VERSION_STR
from PyQt5.QtCore import (pyqtSignal, QSignalMapper, Qt, QPoint,
                          QRegExp, QUrl, QSize, QModelIndex)
from PyQt5.QtGui import QIcon, QColor
from PyQt5.QtWidgets import QApplication, QMainWindow, QMenu, QActionGroup, QAction, QStyle, QListWidgetItem, \
    QLabel, QDockWidget, QWidget, QMessageBox, QLineEdit, QTextEdit, QTreeView, QTableView

from manuskript.commands import DocumentCommandRouter
from manuskript.controllers.character_controller import CharacterController
from manuskript.controllers.navigation_controller import NavigationController
from manuskript.controllers.plot_controller import PlotController
from manuskript.controllers.view_configuration_controller import (
    ViewConfigurationController,
)
from manuskript.controllers.world_controller import WorldController
from manuskript.media_types import core_registry
from manuskript.panels import PanelContext, PanelRegistry
from manuskript.panels import core as core_panels
from manuskript.panels.core import register_core_panels
from manuskript.ui.panels import PanelHost
from manuskript.ui.panels.core import core_panel_factories
from manuskript.services.project_runtime import ProjectRuntime
from manuskript.services.window_registry import WindowRegistry
from manuskript.services.media_type_preferences import (
    MediaTypePreferences,
)
from manuskript.ui.tools.media_type_inspector import (
    MediaTypeInspector,
)
from manuskript.functions import wordCount, appPath, openURL, showInFolder
import manuskript.functions as F
from manuskript.logging import getLogFilePath
from manuskript.models.characterModel import characterModel
from manuskript.models import outlineModel
from manuskript.models.plotModel import plotModel
from manuskript.models.worldModel import worldModel
from manuskript.exporter.context import ExportContext
from manuskript.services.external_process import ExternalProcessRunner
from manuskript.services.external_tools import ExternalToolPaths
from manuskript.services.application_preferences import (
    ApplicationPreferences,
)
from manuskript.services.theme_repository import ThemeRepository
from manuskript.settingsWindow import settingsWindow
from manuskript.ui import style
from manuskript.ui.about import aboutDialog
from manuskript.ui.collapsibleDockWidgets import collapsibleDockWidgets
from manuskript.ui.importers.importer import importerDialog
from manuskript.ui.importers.import_context import ImportContext
from manuskript.ui.exporters.exporter import exporterDialog
from manuskript.ui.git_revision_dialog import GitRevisionDialog
from manuskript.ui.helpLabel import helpLabel
from manuskript.ui.mainWindow import Ui_MainWindow
from manuskript.ui.main_window_action_binding import (
    MainWindowActionBinding,
)
from manuskript.ui.menu_tooltips import MenuTooltipController
from manuskript.ui.navigation_view import MainNavigationView
from manuskript.ui.project_binding import ProjectBinding
from manuskript.ui.project_lifecycle import ProjectLifecycleView
from manuskript.ui.tools.frequencyAnalyzer import frequencyAnalyzer
from manuskript.ui.tools.targets import TargetsDialog
from manuskript.ui.editors.themes import ThemePreviewRenderer
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)
from manuskript.ui.views.MDEditView import MDEditView
from manuskript.ui.statusLabel import statusLabel
from manuskript.ui.status_presenter import StatusPresenter
from manuskript.ui.plugins.controller import PluginUiController
from manuskript.ui.plugins.index_card_styles import (
    IndexCardStyleService,
)
from manuskript.ui.welcome_context import welcome_context_for

# Spellcheck support
from manuskript.ui.views.textEditView import textEditView
from manuskript.ui.view_configuration import (
    MainViewConfiguration,
    ViewSettingsMenuBuilder,
)
from manuskript.services.workspace_state import (
    PRIMARY as WORKSPACE_PRIMARY,
)
from manuskript.ui.workspace_state_controller import (
    WorkspaceStateController,
)
from manuskript.functions import Spellchecker

import logging
LOGGER = logging.getLogger(__name__)

class MainWindow(QMainWindow, Ui_MainWindow):
    # dictChanged = pyqtSignal(str)

    # Tab indexes
    TabInfos = 0
    TabSummary = 1
    TabPersos = 2
    TabPlots = 3
    TabWorld = 4
    TabOutline = 5
    TabRedac = 6
    TabDebug = 7

    SHOW_DEBUG_TAB = False

    def __init__(
        self,
        settings_manager,
        application_preferences=None,
        plugin_runtime=None,
        plugin_option_store=None,
        media_types=None,
        media_type_preferences=None,
        panel_registry=None,
        project_runtime=None,
        window_registry=None,
        window_id=WORKSPACE_PRIMARY,
    ):
        QMainWindow.__init__(self)
        self.setupUi(self)

        # Var
        self._lastFocus = None
        self._lastMDEditView = None
        self._markdownPresentationState = None
        self._defaultCursorFlashTime = 1000 # Overridden at startup with system
                                            # value. In manuskript.main.
        self._autoLoadProject = None  # Used to load a command line project
        self._restoredWorkspaceWindows = False
        self.sessionStartWordCount = 0  # Used to track session targets
        self._previousSelectionEmpty = True
        self.documentCommands = DocumentCommandRouter(
            lambda: self._lastFocus
        )
        self.characterController = CharacterController(self)
        self.plotController = PlotController(self)
        self.worldController = WorldController(self)
        self.navigationController = NavigationController(
            MainNavigationView(self)
        )
        self.history = self.navigationController.history
        # The project layer. A window is one view of it, so it may be
        # handed one that already exists; a window given none composes
        # its own, which is a single-window application.
        self.projectRuntime = (
            project_runtime
            if project_runtime is not None
            else ProjectRuntime(settings_manager=settings_manager)
        )
        # Aliases onto the runtime for everything that still reaches
        # these by attribute. They retire as callers learn to ask the
        # runtime; what they name has moved, not what it does.
        self.settingsManager = self.projectRuntime.settingsManager
        self.undoStack = self.projectRuntime.undoStack
        self.revisionCoordinator = self.projectRuntime.revisionCoordinator
        # Which windows are workspaces. Registering makes this one count
        # towards "the last window", and towards where commands go.
        self.windowRegistry = (
            window_registry
            if window_registry is not None
            else WindowRegistry()
        )
        self.windowRegistry.register(self)
        self.applicationPreferences = (
            application_preferences
            if application_preferences is not None
            else ApplicationPreferences()
        )
        self.settingsManager.configure_cursor_flash_time(
            lambda: self._defaultCursorFlashTime
        )
        self.viewConfigurationController = (
            ViewConfigurationController(
                MainViewConfiguration(self),
                self.settingsManager,
            )
        )
        self.viewSettingsMenu = ViewSettingsMenuBuilder(
            self,
            self.viewConfigurationController,
        )
        self.referenceService = None
        self.textEditorContext = None
        self.projectBinding = ProjectBinding(self)
        # This window's layout, filed under this window. Two windows
        # sharing one set of keys meant the second saved over the first.
        self.windowId = window_id
        self.windowState = WorkspaceStateController(
            self,
            window_id=window_id,
        )

        # Application scope: every window reads the same panel list. A
        # window without one gets an empty registry of its own, which is
        # a working application with no optional panels.
        self.panelRegistry = (
            panel_registry if panel_registry is not None
            else PanelRegistry()
        )
        # Window scope: this window's own copies of whatever the shared
        # registry describes.
        self.panelHost = PanelHost(self, self.panelRegistry)

        # UI. Panels are built before saved state is applied: a splitter
        # can only take back its saved sizes once every widget it is
        # meant to split exists.
        self.setupMoreUi()
        # After the panels exist: a splitter can only take back its
        # saved sizes once every widget it splits is there, and panel
        # visibility is restored by panel id through the host.
        self.windowState.restore()
        self.statusLabel = statusLabel(parent=self)
        self.statusLabel.setAutoFillBackground(True)
        self.statusLabel.hide()
        self.statusPresenter = StatusPresenter(self, self.statusLabel)
        self.pluginRuntime = plugin_runtime
        self.pluginOptionStore = plugin_option_store
        self.mediaTypes = (
            media_types if media_types is not None else core_registry()
        )
        self.mediaTypePreferences = (
            media_type_preferences
            if media_type_preferences is not None
            else MediaTypePreferences()
        )
        self.cardStyles = IndexCardStyleService(
            plugin_runtime.registry if plugin_runtime is not None else None,
            report_error=self.statusPresenter.show,
            parent=self,
        )
        self.pluginUi = (
            PluginUiController(
                self,
                plugin_runtime,
                plugin_option_store,
                media_types=self.mediaTypes,
            )
            if plugin_runtime is not None
            else None
        )
        self.buildDeveloperMenu()
        self.buildWorkspaceMenu()
        self.projectLifecycleView = ProjectLifecycleView(self)
        self.externalProcessRunner = ExternalProcessRunner()
        self.externalToolPaths = ExternalToolPaths()
        self.themeRepository = ThemeRepository()
        self.themePreviewRenderer = ThemePreviewRenderer()
        # The runtime builds the manager around the view side this
        # window supplies, rather than the window building one for
        # itself: the project is the runtime's, the view is the
        # window's.
        self.projectManager = self.projectRuntime.attach(
            self.projectLifecycleView,
            status_reporter=self.statusPresenter.show,
        )
        self.projectHistory = self.projectManager.last_project_store
        self.welcome.set_context(
            welcome_context_for(
                self,
                self.settingsManager,
                self.projectHistory,
            )
        )

        # Welcome
        self.welcome.updateValues()
        self.switchToWelcome()

        # Word count
        self.mprWordCount = QSignalMapper(self)
        for t, i in [
            (self.txtSummarySentence, 0),
            (self.txtSummaryPara, 1),
            (self.txtSummaryPage, 2),
            (self.txtSummaryFull, 3)
        ]:
            t.textChanged.connect(self.mprWordCount.map)
            self.mprWordCount.setMapping(t, i)
        self.mprWordCount.mapped.connect(self.wordCount)

        self.cmbSummary.setCurrentIndex(0)
        self.cmbSummary.currentIndexChanged.emit(0)

        self.actionBinding = MainWindowActionBinding(self)
        self.actionBinding.bind()
        self.menuTooltipController = MenuTooltipController(
            self.menubar,
            {
                self.menuFile: self.tr(
                    "Open, save, import, compile, and close projects"
                ),
                self.menuEdit: self.tr(
                    "Edit content, formatting, labels, and preferences"
                ),
                self.menuOrganize: self.tr(
                    "Reorder, split, merge, and duplicate project items"
                ),
                self.menuNavigate: self.tr(
                    "Move backward and forward through navigation history"
                ),
                self.menuView: self.tr(
                    "Change the workspace and Markdown presentation"
                ),
                self.menuTools: self.tr(
                    "Open writing analysis and target tools"
                ),
                self.menuHelp: self.tr(
                    "Open help, diagnostics, support, and application details"
                ),
            },
            self,
        )

        # Tools non-modal windows
        self.td = None  # Targets Dialog
        self.fw = None  # Frequency Window

        self.characterController.capture_tabs()

    @property
    def currentProject(self):
        """Compatibility view of the active project path."""
        return self.projectManager.currentProject

    @property
    def projectDirty(self):
        """Compatibility view of whether the active project has unsaved changes."""
        return self.projectManager.projectDirty

    def consumeAutoLoadProject(self):
        project = self._autoLoadProject
        self._autoLoadProject = None
        return project

    def switchToWelcome(self):
        """
        While switching to welcome screen, we have to hide all the docks.
        Otherwise one could use the search dock, and manuskript would crash.
        Plus it's unnecessary distraction.
        But we also want to restore them to their visibility prior to switching,
        so we store states.
        """
        self.windowState.hide_project_docks()
        # Hides the toolbar
        self.toolbar.setVisible(False)
        # Switch to welcome screen
        self.stack.setCurrentIndex(0)

    def switchToProject(self):
        """Restores docks and toolbar visibility, and switch to project."""
        self.windowState.restore_project_docks()
        # Show the toolbar
        self.toolbar.setVisible(True)
        self.stack.setCurrentIndex(1)

    def closeEvent(self, event):
        """Close this window, and the project only with the last one.

        A workspace window is one view of a project. Closing it puts
        that view away; the project goes when its last window does, and
        that is the only close that may ask about unsaved changes.
        """
        if self.windowRegistry.is_last(self):
            if not self.projectManager.closeProject():
                event.ignore()
                return
            if not self.windowRegistry.quitting:
                # Closed one at a time rather than quit: the windows
                # still open are the session to come back to.
                self.windowState.store.set_open_windows(
                    self.openWorkspaceIds()
                )
        self.closeToolWindows()
        self.windowState.save()
        self.projectRuntime.detach(self.projectLifecycleView)
        self.windowRegistry.unregister(self)
        super().closeEvent(event)

    def buildWorkspaceMenu(self):
        """Offer another window onto the same project.

        Built in code rather than in the Designer file: the action does
        nothing a window owns, and regenerating the whole .ui to add one
        menu entry buys nothing.
        """
        self.actNewWindow = QAction(self.tr("&New Window"), self)
        self.actNewWindow.setObjectName("actNewWindow")
        self.actNewWindow.setStatusTip(
            self.tr("Open another window onto this project")
        )
        self.actNewWindow.triggered.connect(self.openWorkspaceWindow)
        before = self.menuView.actions()
        self.menuView.insertAction(
            before[0] if before else None,
            self.actNewWindow,
        )
        self.menuView.insertSeparator(
            before[0] if before else None
        )

    def nextWorkspaceId(self):
        """An identifier no open window is already filing state under.

        Stable per window rather than positional, so a window keeps its
        own layout even when the windows before it have closed.
        """
        taken = {
            getattr(window, "windowId", None)
            for window in self.windowRegistry.workspace_windows
        }
        index = 2
        while "window-{}".format(index) in taken:
            index += 1
        return "window-{}".format(index)

    def openWorkspaceWindow(self, window_id=None):
        """Another view of this project, sharing everything it owns.

        The new window is handed the same project runtime, panel
        registry and plugin runtime, so it edits the one project rather
        than a copy of it, and it joins a project already open instead
        of going through the welcome screen.
        """
        window = MainWindow(
            self.settingsManager,
            application_preferences=self.applicationPreferences,
            plugin_runtime=self.pluginRuntime,
            plugin_option_store=self.pluginOptionStore,
            media_types=self.mediaTypes,
            media_type_preferences=self.mediaTypePreferences,
            panel_registry=self.panelRegistry,
            project_runtime=self.projectRuntime,
            window_registry=self.windowRegistry,
            window_id=window_id or self.nextWorkspaceId(),
        )
        window.adoptOpenProject()
        window.show()
        return window

    def adoptOpenProject(self):
        """Show the project this window's runtime already has open.

        A first window reaches a project by loading one; a later window
        finds it already loaded and only has to catch its own widgets
        up -- models installed, signals connected, saved view settings
        applied.
        """
        runtime = self.projectRuntime
        if not runtime.isOpen:
            return False
        view = self.projectLifecycleView
        view.install_models(runtime.models)
        view.sync_to_state(True)
        view.connect_project()
        view.apply_loaded_settings()
        view.project_opened()
        return True

    def quitApplication(self):
        """Close every workspace window, the primary last.

        Returns whether the application is actually going: a cancelled
        save prompt aborts the quit and leaves the windows standing.
        """
        session = self.openWorkspaceIds()
        if not self.windowRegistry.close_all():
            return False
        # Only once the quit succeeded, or a cancelled prompt would
        # record a session that never ended.
        self.windowState.store.set_open_windows(session)
        return True

    def openWorkspaceIds(self):
        return [
            getattr(window, "windowId", WORKSPACE_PRIMARY)
            for window in self.windowRegistry.workspace_windows
        ]

    def restoreWorkspaceWindows(self):
        """Reopen the windows the last session left open.

        Tied to a project opening rather than to launch, because a
        workspace window with no project is only a welcome screen. Runs
        once, from the window the project was opened in.
        """
        if self._restoredWorkspaceWindows:
            return ()
        if self.windowId != WORKSPACE_PRIMARY:
            return ()
        self._restoredWorkspaceWindows = True
        reopened = []
        for window_id in self.windowState.store.open_windows():
            if window_id in self.openWorkspaceIds():
                continue
            reopened.append(self.openWorkspaceWindow(window_id))
        return tuple(reopened)

    def closeToolWindows(self):
        """Close the tool windows this window opened.

        Only this window's own: another workspace's targets dialog is
        not ours to shut, which is what walking every top-level widget
        used to do.
        """
        for window in (self.td, self.fw, self.gitRevisionDialog):
            if window is not None:
                window.close()
        if self.pluginUi is not None:
            self.pluginUi.projectPanels.close_all()

    ###############################################################################
    # GENERAL / UI STUFF
    ###############################################################################

    def tabMainChanged(self):
        "Called when main tab changes."
        tabIsEditor = self.tabMain.currentIndex() == self.TabRedac
        self.menuOrganize.menuAction().setEnabled(tabIsEditor)
        for i in [self.actCut,
                  self.actCopy,
                  self.actPaste,
                  self.actDelete,
                  self.actRename]:
            i.setEnabled(tabIsEditor)
        tabIndex = self.tabMain.currentIndex()

        if tabIndex == self.TabPersos:
            self.characterController.record_current_selection()
        elif tabIndex == self.TabPlots:
            self.plotController.record_current_selection()
        elif tabIndex == self.TabWorld:
            self.worldController.record_current_selection()
        elif tabIndex == self.TabOutline:
            index = self.treeOutlineOutline.selectionModel().currentIndex()
            if index.isValid():
                id = self.mdlOutline.ID(index)
                self.pushHistory(("outline", id))
                self._previousSelectionEmpty = id is not None
            else:
                self.pushHistory(("outline", None))
                self._previousSelectionEmpty = False
        elif tabIndex == self.TabRedac:
            index = self.treeRedacOutline.selectionModel().currentIndex()
            if index.isValid():
                id = self.mdlOutline.ID(index)
                self.pushHistory(("redac", id))
                self._previousSelectionEmpty = id is not None
            else:
                self.pushHistory(("redac", None))
                self._previousSelectionEmpty = False
        else:
            self.pushHistory(("main", self.tabMain.currentIndex()))
            self._previousSelectionEmpty = False

    def focusChanged(self, old, new):
        """
        We get notified by qApp when focus changes, from old to new widget.
        """

        # Projection widgets are siblings of their canonical editor in a
        # MarkdownEditorHost.
        markdown_editor = new
        while (
            markdown_editor is not None
            and not isinstance(markdown_editor, MDEditView)
        ):
            canonical_editor = getattr(
                markdown_editor,
                "canonicalEditor",
                None,
            )
            if isinstance(canonical_editor, MDEditView):
                markdown_editor = canonical_editor
                break
            markdown_editor = markdown_editor.parent()
        self._lastMDEditView = markdown_editor

        # Determine which view had focus last, to send the keyboard shortcuts
        # to the right place

        targets = [
            self.treeRedacOutline,
            self.mainEditor
        ]

        while new is not None:
            if new in targets:
                self._lastFocus = new
                break
            new = new.parent()

    def projectName(self):
        """
        Returns a user-friendly name for the loaded project.
        """
        pName = os.path.split(self.currentProject)[1]
        if pName.endswith('.msk'):
            pName=pName[:-4]
        return pName

    ###############################################################################
    # OUTLINE
    ###############################################################################

    def outlineChanged(self, selected, deselected):
        index = self.treeOutlineOutline.selectionModel().currentIndex()
        if not index.isValid():
            self.pushHistory(("outline", None))
            self._previousSelectionEmpty = True
            return
        
        self.pushHistory(("outline", self.mdlOutline.ID(index)))
        self._previousSelectionEmpty = False


    def outlineRemoveItemsRedac(self):
        self.treeRedacOutline.delete()

    def outlineRemoveItemsOutline(self):
        self.treeOutlineOutline.delete()

    ###############################################################################
    # EDITOR
    ###############################################################################

    def redacOutlineChanged(self):
        index = self.treeRedacOutline.selectionModel().currentIndex()
        if not index.isValid():
            self.pushHistory(("redac", None))
            self._previousSelectionEmpty = True
            return
        
        self.pushHistory(("redac", self.mdlOutline.ID(index)))
        self._previousSelectionEmpty = False

    def openIndex(self, index):
        self.treeRedacOutline.setCurrentIndex(index)

    def openIndexes(self, indexes, newTab=True):
        self.mainEditor.openIndexes(indexes, newTab=True)

    # Menu #############################################################

    def doSearch(self):
        "Do a global search."
        self.dckSearch.show()
        self.dckSearch.activateWindow()
        searchTextInput = self.dckSearch.findChild(QLineEdit, 'searchTextInput')
        searchTextInput.setFocus()
        searchTextInput.selectAll()

    def showGitRevisions(self, parent=None):
        if not self.projectManager.session.is_open:
            return
        host = parent if isinstance(parent, QWidget) else self
        if self.gitRevisionDialog is None:
            self.gitRevisionDialog = GitRevisionDialog(
                self.projectManager,
                self.settingsManager,
                self.revisionCoordinator,
                host,
            )
            self.gitRevisionDialog.setAttribute(
                Qt.WA_DeleteOnClose,
            )
            self.gitRevisionDialog.destroyed.connect(
                self._gitRevisionDialogClosed
            )
        elif self.gitRevisionDialog.parentWidget() is not host:
            # A child window of an application-modal Settings window
            # remains interactive; a sibling window is blocked by it.
            self.gitRevisionDialog.hide()
            self.gitRevisionDialog.setParent(host, Qt.Dialog)
        self.gitRevisionDialog.show()
        self.gitRevisionDialog.raise_()
        self.gitRevisionDialog.activateWindow()

    def _gitRevisionDialogClosed(self):
        self.gitRevisionDialog = None

    # Formats
    def callLastMDEditView(self, functionName, params=()):
        """
        If last focused widget was MDEditView, call the given function.
        """
        if self._lastMDEditView:
            function = getattr(self._lastMDEditView, functionName)
            function(*params)
    def formatSetext1(self): self.callLastMDEditView("titleSetext", [1])
    def formatSetext2(self): self.callLastMDEditView("titleSetext", [2])
    def formatAtx1(self): self.callLastMDEditView("titleATX", [1])
    def formatAtx2(self): self.callLastMDEditView("titleATX", [2])
    def formatAtx3(self): self.callLastMDEditView("titleATX", [3])
    def formatAtx4(self): self.callLastMDEditView("titleATX", [4])
    def formatAtx5(self): self.callLastMDEditView("titleATX", [5])
    def formatAtx6(self): self.callLastMDEditView("titleATX", [6])
    def formatBold(self): self.callLastMDEditView("bold")
    def formatItalic(self): self.callLastMDEditView("italic")
    def formatUnderline(self): self.callLastMDEditView("underline")
    def formatStrike(self): self.callLastMDEditView("strike")
    def formatVerbatim(self): self.callLastMDEditView("verbatim")
    def formatSuperscript(self): self.callLastMDEditView("superscript")
    def formatSubscript(self): self.callLastMDEditView("subscript")
    def formatCommentLines(self): self.callLastMDEditView("commentLine")
    def formatList(self): self.callLastMDEditView("unorderedList")
    def formatOrderedList(self): self.callLastMDEditView("orderedList")
    def formatBlockquote(self): self.callLastMDEditView("blockquote")
    def formatCommentBlock(self): self.callLastMDEditView("comment")
    def formatClear(self): self.callLastMDEditView("clearFormat")

    def setMarkdownPresentationMode(self, mode):
        if self._markdownPresentationState is not None:
            self._markdownPresentationState.set_mode(mode)

    def attachMarkdownPresentationState(self, state):
        if self._markdownPresentationState is not None:
            try:
                self._markdownPresentationState.modeChanged.disconnect(
                    self.syncMarkdownPresentationActions
                )
                (
                    self._markdownPresentationState
                    .allowedModesChanged.disconnect(
                        self.syncMarkdownPresentationModes
                    )
                )
            except (RuntimeError, TypeError):
                pass

        self._markdownPresentationState = state
        self.menuMarkdownMode.setEnabled(state is not None)
        if state is None:
            return

        state.modeChanged.connect(
            self.syncMarkdownPresentationActions
        )
        state.allowedModesChanged.connect(
            self.syncMarkdownPresentationModes
        )
        self.syncMarkdownPresentationModes(state.allowed_modes)
        self.syncMarkdownPresentationActions(state.mode)

    def syncMarkdownPresentationActions(self, mode):
        mode = MarkdownPresentationMode.from_value(mode)
        actions = {
            MarkdownPresentationMode.SOURCE:
                self.actMarkdownSource,
            MarkdownPresentationMode.FORMATTED_SOURCE:
                self.actMarkdownFormattedSource,
            MarkdownPresentationMode.LIVE_PREVIEW:
                self.actMarkdownLivePreview,
            MarkdownPresentationMode.READING:
                self.actMarkdownReading,
        }
        actions[mode].setChecked(True)

    def syncMarkdownPresentationModes(self, modes):
        allowed = set(modes)
        for mode, action in {
            MarkdownPresentationMode.SOURCE:
                self.actMarkdownSource,
            MarkdownPresentationMode.FORMATTED_SOURCE:
                self.actMarkdownFormattedSource,
            MarkdownPresentationMode.LIVE_PREVIEW:
                self.actMarkdownLivePreview,
            MarkdownPresentationMode.READING:
                self.actMarkdownReading,
        }.items():
            action.setEnabled(mode in allowed)

    # Navigate
    
    def navigateBack(self):
        self.navigationController.back()

    def navigateForward(self):
        self.navigationController.forward()

    def pushHistory(self, entry):
        self.navigationController.record(
            entry,
            replace=self._previousSelectionEmpty,
        )

    def navigated(self, event):
        self.navigationController.navigated(event)

    def makeConnections(self):
        self.projectBinding.bind()
        self.referenceService = self.projectBinding.reference_service
        self.textEditorContext = self.projectBinding.text_editor_context

    def breakConnections(self):
        """Release every signal connection owned by the current project."""
        self.projectBinding.unbind()
        self.attachMarkdownPresentationState(None)
        self.textEditorContext = None
        self.referenceService = None

    ###############################################################################
    # HELP
    ###############################################################################

    def centerChildWindow(self, win):
        r = win.geometry()
        r2 = self.geometry()
        win.move(r2.center() - QPoint(int(r.width()/2), int(r.height()/2)))

    def support(self):
        openURL("https://github.com/olivierkes/manuskript/wiki/Technical-Support")

    def locateLogFile(self):
        logfile = getLogFilePath()

        # Make sure we are even logging to a file.
        if not logfile:
            QMessageBox(QMessageBox.Information,
                self.tr("Sorry!"),
                "<p><b>" +
                    self.tr("This session is not being logged.") +
                "</b></p>",
                QMessageBox.Ok).exec()
            return

        # Remind user that log files are at their best once they are complete.
        msg = QMessageBox(QMessageBox.Information,
            self.tr("A log file is a Work in Progress!"),
            "<p><b>" +
                self.tr("The log file \"{}\" will continue to be written to until Manuskript is closed.").format(os.path.basename(logfile)) +
            "</b></p>" +
            "<p>" +
                self.tr("It will now be displayed in your file manager, but is of limited use until you close Manuskript.") +
            "</p>",
            QMessageBox.Ok)

        ret = msg.exec()

        # Open the filemanager.
        if ret == QMessageBox.Ok:
            if not showInFolder(logfile):
                # If everything convenient fails, at least make sure the user can browse to its location manually.
                QMessageBox(QMessageBox.Critical,
                    self.tr("Error!"),
                    "<p><b>" +
                        self.tr("An error was encountered while trying to show the log file below in your file manager.") +
                    "</b></p>" +
                    "<p>" +
                        logfile +
                    "</p>",
                    QMessageBox.Ok).exec()


    def about(self):
        self.dialog = aboutDialog(mw=self)
        self.dialog.setFixedSize(self.dialog.size())
        self.dialog.show()
        # Center about dialog
        self.centerChildWindow(self.dialog)

    ###############################################################################
    # GENERAL AKA UNSORTED
    ###############################################################################

    def wordCount(self, i):

        src = {
            0: self.txtSummarySentence,
            1: self.txtSummaryPara,
            2: self.txtSummaryPage,
            3: self.txtSummaryFull
        }[i]

        lbl = {
            0: self.lblSummaryWCSentence,
            1: self.lblSummaryWCPara,
            2: self.lblSummaryWCPage,
            3: self.lblSummaryWCFull
        }[i]

        wc = wordCount(src.toPlainText())
        if i in [2, 3]:
            pages = self.tr(" (~{} pages)").format(int(wc / 25) / 10.)
        else:
            pages = ""
        lbl.setText(self.tr("Words: {}{}").format(wc, pages))

    def setupMoreUi(self):

        # Tool bar on the right. The four workspace panels are declared
        # once in the shared registry and built per window; their
        # toggles come from the panel host so that anything showing a
        # panel and anything watching it agree on one action. They are
        # built first: window styling reaches into the project tree.
        self.toolbar = collapsibleDockWidgets(Qt.RightDockWidgetArea, self)
        register_core_panels(
            self.panelRegistry,
            self.TabPlots,
            self.TabRedac,
            factories=core_panel_factories(),
        )
        for panel_id in (
            core_panels.BOOK_SUMMARY,
            core_panels.PROJECT_TREE,
            core_panels.METADATA,
            core_panels.STORYLINE,
        ):
            instance = self.panelHost.open(
                panel_id,
                PanelContext(window=self),
            )
            if instance is None:
                continue
            self.toolbar.addPanelToggle(
                instance.action,
                instance.widget,
                instance.descriptor.group,
            )

        style.styleMainWindow(self)

        self.actGitRevisions = QAction(
            QIcon.fromTheme("document-open-recent"),
            self.tr("Revision &History…"),
            self,
        )
        self.actGitRevisions.setObjectName("actGitRevisions")
        self.actGitRevisions.setToolTip(self.tr(
            "Review, tag, commit, and restore project revisions"
        ))
        self.menuFile.insertAction(
            self.actCloseProject,
            self.actGitRevisions,
        )
        self.gitRevisionDialog = None

        # Hides navigation dock title bar
        self.dckNavigation.setTitleBarWidget(QWidget(None))

        # Custom "tab" bar on the left
        self.lstTabs.setIconSize(QSize(48, 48))
        for i in range(self.tabMain.count()):

            icons = [QIcon.fromTheme("stock_view-details"), #info
                     QIcon.fromTheme("application-text-template"), #applications-publishing
                     F.themeIcon("characters"),
                     F.themeIcon("plots"),
                     F.themeIcon("world"),
                     F.themeIcon("outline"),
                     QIcon.fromTheme("gtk-edit"),
                     QIcon.fromTheme("applications-debugging")
            ]
            self.tabMain.setTabIcon(i, icons[i])

            item = QListWidgetItem(self.tabMain.tabIcon(i),
                                   self.tabMain.tabText(i))
            item.setSizeHint(QSize(item.sizeHint().width(), 64))
            item.setToolTip(self.tabMain.tabText(i))
            item.setTextAlignment(Qt.AlignCenter)
            self.lstTabs.addItem(item)
        self.tabMain.tabBar().hide()
        self.lstTabs.currentRowChanged.connect(self.tabMain.setCurrentIndex)
        self.lstTabs.item(self.TabDebug).setHidden(not self.SHOW_DEBUG_TAB)
        self.tabMain.setTabEnabled(self.TabDebug, self.SHOW_DEBUG_TAB)
        self.tabMain.currentChanged.connect(self.lstTabs.setCurrentRow)

        # Splitters
        self.splitterPersos.setStretchFactor(0, 25)
        self.splitterPersos.setStretchFactor(1, 75)

        self.splitterPlot.setStretchFactor(0, 20)
        self.splitterPlot.setStretchFactor(1, 60)
        self.splitterPlot.setStretchFactor(2, 30)

        self.splitterWorld.setStretchFactor(0, 25)
        self.splitterWorld.setStretchFactor(1, 75)

        self.splitterOutlineH.setStretchFactor(0, 25)
        self.splitterOutlineH.setStretchFactor(1, 75)
        self.splitterOutlineV.setStretchFactor(0, 75)
        self.splitterOutlineV.setStretchFactor(1, 25)

        self.splitterRedacV.setStretchFactor(0, 75)
        self.splitterRedacV.setStretchFactor(1, 25)

        self.splitterRedacH.setStretchFactor(0, 30)
        self.splitterRedacH.setStretchFactor(1, 40)
        self.splitterRedacH.setStretchFactor(2, 30)

        # QFormLayout stretch
        for w in [self.txtWorldDescription, self.txtWorldPassion, self.txtWorldConflict]:
            s = w.sizePolicy()
            s.setVerticalStretch(1)
            w.setSizePolicy(s)

        # Help box
        references = [
            (self.lytTabOverview,
             self.tr("Enter information about your book, and yourself."),
             0),
            (self.lytSituation,
             self.tr(
                     """The basic situation, in the form of a 'What if...?' question. Ex: 'What if the most dangerous
                     evil wizard wasn't able to kill a baby?' (Harry Potter)"""),
             1),
            (self.lytSummary,
             self.tr(
                     """Take time to think about a one sentence (~50 words) summary of your book. Then expand it to
                     a paragraph, then to a page, then to a full summary."""),
             1),
            (self.lytTabPersos,
             self.tr("Create your characters."),
             0),
            (self.lytTabPlot,
             self.tr("Develop plots."),
             0),
            (self.lytTabContext,
             self.tr("Build worlds.  Create hierarchy of broad categories down to specific details."),
             0),
            (self.lytTabOutline,
             self.tr("Create the outline of your masterpiece."),
             0),
            (self.lytTabRedac,
             self.tr("Write."),
             0),
            (self.lytTabDebug,
             self.tr("Debug info. Sometimes useful."),
             0)
        ]

        for widget, text, pos in references:
            label = helpLabel(text, self)
            self.actShowHelp.toggled.connect(label.setVisible, F.AUC)
            widget.layout().insertWidget(pos, label)

        self.actShowHelp.setChecked(False)

        # Spellcheck
        if Spellchecker.isInstalled():
            self.menuDict = QMenu(self.tr("Dictionary"))
            self.menuDictGroup = QActionGroup(self)
            self.updateMenuDict()
            self.menuTools.addMenu(self.menuDict)

            self.actSpellcheck.toggled.connect(self.toggleSpellcheck, F.AUC)
            # self.dictChanged.connect(self.mainEditor.setDict, F.AUC)
            # self.dictChanged.connect(self.redacMetadata.setDict, F.AUC)
            # self.dictChanged.connect(self.outlineItemEditor.setDict, F.AUC)

        else:
            # No Spell check support
            self.actSpellcheck.setVisible(False)
            for lib, requirement in Spellchecker.supportedLibraries().items():
                a = QAction(self.tr("Install {}{} to use spellcheck").format(lib, requirement or ""), self)
                a.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxWarning))
                # Need to bound the lib argument otherwise the lambda uses the same lib value across all calls
                def gen_slot_cb(l):
                    return lambda: self.openSpellcheckWebPage(l)
                a.triggered.connect(gen_slot_cb(lib), F.AUC)
                self.menuTools.addAction(a)


    ###############################################################################
    # SPELLCHECK
    ###############################################################################

    def updateMenuDict(self):

        if not Spellchecker.isInstalled():
            return

        self.menuDict.clear()
        dictionaries = Spellchecker.availableDictionaries()

        # Set first run dictionary
        if self.settingsManager.dict is None:
            self.settingsManager.dict = Spellchecker.getDefaultDictionary()

        # Check if project dict is unavailable on this machine
        dict_available = False
        for lib, dicts in dictionaries.items():
            if dict_available:
                break
            for i in dicts:
                if Spellchecker.normalizeDictName(lib, i) == self.settingsManager.dict:
                    dict_available = True
                    break
        # Reset dict to default one if it's unavailable
        if not dict_available:
            self.settingsManager.dict = Spellchecker.getDefaultDictionary()

        for lib, dicts in dictionaries.items():
            if len(dicts) > 0:
                a = QAction(lib, self)
            else:
                a = QAction(self.tr("{} has no installed dictionaries").format(lib), self)
            a.setEnabled(False)
            self.menuDict.addAction(a)
            for i in dicts:
                a = QAction(i, self)
                a.data = lib
                a.setCheckable(True)
                if Spellchecker.normalizeDictName(lib, i) == self.settingsManager.dict:
                    a.setChecked(True)
                a.triggered.connect(self.setDictionary, F.AUC)
                self.menuDictGroup.addAction(a)
                self.menuDict.addAction(a)
            self.menuDict.addSeparator()

        # If a new dictionary was chosen, apply the change and re-enable spellcheck if it was enabled.
        if not dict_available:
            self.setDictionary()
            self.toggleSpellcheck(self.settingsManager.spellcheck)

        for lib, requirement in Spellchecker.supportedLibraries().items():
            if lib not in dictionaries:
                a = QAction(self.tr("{}{} is not installed").format(lib, requirement or ""), self)
                a.setEnabled(False)
                self.menuDict.addAction(a)
                self.menuDict.addSeparator()

    def setDictionary(self):
        if not Spellchecker.isInstalled():
            return

        for i in self.menuDictGroup.actions():
            if i.isChecked():
                # self.dictChanged.emit(i.text().replace("&", ""))
                self.settingsManager.dict = Spellchecker.normalizeDictName(i.data, i.text().replace("&", ""))

                # Find all textEditView from self, and toggle spellcheck
                for w in self.findChildren(textEditView, QRegExp(".*"),
                                           Qt.FindChildrenRecursively):
                    w.setDict(self.settingsManager.dict)

    def openSpellcheckWebPage(self, lib):
        F.openURL(Spellchecker.getLibraryURL(lib))

    def toggleSpellcheck(self, val):
        self.settingsManager.spellcheck = val

        # Find all textEditView from self, and toggle spellcheck
        for w in self.findChildren(textEditView, QRegExp(".*"),
                                   Qt.FindChildrenRecursively):
            w.toggleSpellcheck(val)

    ###############################################################################
    # SETTINGS
    ###############################################################################

    def settingsLabel(self):
        self.settingsWindow(3)

    def settingsStatus(self):
        self.settingsWindow(4)

    def settingsWindow(self, tab=None):
        self.sw = settingsWindow(
            self,
            self.settingsManager,
            theme_repository=self.themeRepository,
            theme_preview_renderer=self.themePreviewRenderer,
            application_preferences=self.applicationPreferences,
            card_styles=self.cardStyles,
        )
        self.sw.hide()
        self.sw.setWindowModality(Qt.ApplicationModal)
        self.sw.setWindowFlags(Qt.Dialog)
        self.centerChildWindow(self.sw)
        if tab:
            self.sw.setTab(tab)
        self.sw.show()

    ###############################################################################
    # TOOLS
    ###############################################################################

    def frequencyAnalyzer(self):
        self.fw = frequencyAnalyzer(
            self.mdlOutline,
            self.settingsManager,
            parent=self,
        )
        self.fw.show()
        self.centerChildWindow(self.fw)

    def sessionTargets(self):
        self.td = TargetsDialog(self)
        self.td.show()
        self.centerChildWindow(self.td)

    def buildDeveloperMenu(self):
        """Tools that inspect Manuskript rather than the manuscript.

        Added here rather than in mainWindow.ui, following the Plugins menu:
        a submenu built in code needs no generated file regenerated, and
        this one exists whether or not any plugin is loaded.
        """
        self.menuTools.addSeparator()
        self.menuDeveloper = self.menuTools.addMenu(self.tr("Developer"))
        self.menuDeveloper.setObjectName("menuDeveloper")
        self.actMediaTypes = QAction(self.tr("Media types…"), self)
        self.actMediaTypes.setObjectName("actMediaTypes")
        self.actMediaTypes.setStatusTip(self.tr(
            "Inspect export formats, and declare ones Manuskript does "
            "not know"
        ))
        self.actMediaTypes.triggered.connect(self.mediaTypeInspector)
        self.menuDeveloper.addAction(self.actMediaTypes)

    def mediaTypeInspector(self):
        self.mediaTypeWindow = MediaTypeInspector(
            self.mediaTypes,
            self.mediaTypePreferences,
            parent=self,
        )
        self.mediaTypeWindow.show()
        self.centerChildWindow(self.mediaTypeWindow)

    ###############################################################################
    # VIEW MENU
    ###############################################################################

    def generateViewMenu(self):
        self.viewSettingsMenu.rebuild()

    def setViewSettings(self, item, part, element):
        self.viewConfigurationController.set_view_setting(
            item,
            part,
            element,
        )

    ###############################################################################
    # VIEW MODES
    ###############################################################################

    def setViewModeSimple(self, _checked=False):
        self.viewConfigurationController.set_simple()

    def setViewModeFiction(self, _checked=False):
        self.viewConfigurationController.set_fiction()

    ###############################################################################
    # IMPORT / EXPORT
    ###############################################################################

    def doImport(self):
        # Warn about buggy Qt versions and import crash
        #
        # (Py)Qt 5.11 and 5.12 have a bug that can cause crashes when simply
        # setting up various UI elements.
        # This has been reported and verified to happen with File -> Import.
        # See PR #611.
        if re.match("^5\\.1[12](\\.?|$)", qVersion()):
            warning1 = self.tr("PyQt / Qt versions 5.11 and 5.12 are known to cause a crash which might result in a loss of data.")
            warning2 = self.tr("PyQt {} and Qt {} are in use.").format(qVersion(), PYQT_VERSION_STR)

            # Don't translate for debug log.
            LOGGER.warning(warning1)
            LOGGER.warning(warning2)

            msg = QMessageBox(QMessageBox.Warning,
                self.tr("Proceed with import at your own risk"),
                "<p><b>" +
                    warning1 +
                "</b></p>" +
                "<p>" +
                    warning2 +
                "</p>",
                QMessageBox.Abort | QMessageBox.Ignore)
            msg.setDefaultButton(QMessageBox.Abort)

            # Return because user heeds warning
            if msg.exec() == QMessageBox.Abort:
                return

        # Proceed with Import
        self.dialog = importerDialog(
            ImportContext(
                outline_model=self.mdlOutline,
                character_model=self.mdlCharacter,
                label_model=self.mdlLabels,
                status_model=self.mdlStatus,
                settings=self.settingsManager,
                current_outline_index=lambda: (
                    self.treeRedacOutline.currentIndex()
                    if self.treeRedacOutline.selectedIndexes()
                    else QModelIndex()
                ),
                show_status=self.statusPresenter.show,
            ),
            plugin_runtime=self.pluginRuntime,
            plugin_option_store=self.pluginOptionStore,
        )
        self.dialog.show()
        self.centerChildWindow(self.dialog)


    def doCompile(self):
        self.dialog = exporterDialog(
            self.exportContext(),
            preferences=self.applicationPreferences,
            plugin_runtime=self.pluginRuntime,
            plugin_option_store=self.pluginOptionStore,
        )
        self.dialog.show()
        self.centerChildWindow(self.dialog)

    def exportContext(self):
        return ExportContext(
            project_file=self.currentProject or "",
            outline_model=self.mdlOutline,
            flat_data_model=self.mdlFlatData,
            label_model=self.mdlLabels,
            status_model=self.mdlStatus,
            parent=self,
            tool_paths=self.externalToolPaths,
            process_runner=self.externalProcessRunner,
            page_types=(
                self.pluginUi.pageTypes
                if self.pluginUi is not None
                else None
            ),
        )
