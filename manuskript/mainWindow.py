#!/usr/bin/env python
# --!-- coding: utf8 --!--
import importlib
import os

from functools import partial

from PyQt5.QtCore import (pyqtSignal, QSignalMapper, Qt, QPoint,
                          QRegExp, QUrl, QSize)
from PyQt5.QtGui import QIcon, QColor
from PyQt5.QtWidgets import QApplication, QMainWindow, QMenu, QActionGroup, QAction, QStyle, QListWidgetItem, \
    QLabel, QDockWidget, QWidget, QMessageBox, QLineEdit, QTextEdit, QTreeView, QTableView

from manuskript.commands import (
    DocumentCommandRouter,
    MarkupCommandRouter,
)
from manuskript.domain.writing_session import WritingSessionProgress
from manuskript.controllers.character_controller import CharacterController
from manuskript.controllers.navigation_controller import NavigationController
from manuskript.controllers.plot_controller import PlotController
from manuskript.controllers.view_configuration_controller import (
    ViewConfigurationController,
)
from manuskript.controllers.world_controller import WorldController
from manuskript.ui.panel_services import PanelDialogs, PanelNavigation
from manuskript.ui.views.character_panel import (
    CharacterModels,
    CharacterPanelView,
)
from manuskript.ui.views.plot_panel import PlotModels, PlotPanelView
from manuskript.ui.views.world_panel import WorldModels, WorldPanelView
from manuskript.panels import PanelContext
from manuskript.panels import core as core_panels
from manuskript.panels.core import register_core_panels
from manuskript.ui.panels import PanelHost
from manuskript.ui.panels.window_port import PanelWindow
from manuskript.ui.panels.core import (
    CorePanelViewSet,
    core_panel_factories,
)
from manuskript.functions import wordCount, appPath, openURL, showInFolder
from manuskript import timing
import manuskript.functions as F
from manuskript.logging import getLogFilePath
from manuskript.models.characterModel import characterModel
from manuskript.models import outlineModel
from manuskript.models.plotModel import plotModel
from manuskript.models.worldModel import worldModel
from manuskript.services.external_process import ExternalProcessRunner
from manuskript.services.external_tools import ExternalToolPaths
from manuskript.services.theme_repository import ThemeRepository
from manuskript.ui import style
from manuskript.ui.collapsibleDockWidgets import collapsibleDockWidgets
from manuskript.ui.helpLabel import helpLabel
from manuskript.ui.mainWindow import Ui_MainWindow
from manuskript.ui.main_window_action_binding import (
    MainWindowActionBinding,
)
from manuskript.ui.menu_tooltips import MenuTooltipController
from manuskript.ui.navigation_view import MainNavigationView, NavigationViews
from manuskript.ui.project_binding import ProjectBinding
from manuskript.ui.project_binding_views import ProjectBindingViews
from manuskript.ui.project_context_binding import ProjectContextBinding
from manuskript.ui.project_feature_binding import ProjectFeatureBinding
from manuskript.ui.project_lifecycle import ProjectLifecycleView
from manuskript.ui.project_lifecycle_views import ProjectLifecycleViews
from manuskript.ui.project_view_set import ProjectViewSet
from manuskript.ui.editors.themes import ThemePreviewRenderer
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)
from manuskript.ui.views.MDEditView import MDEditView
from manuskript.ui.statusLabel import statusLabel
from manuskript.ui.status_presenter import (
    StatusPresenter,
    StatusPresenterViews,
)
from manuskript.ui.workspace_dialogs import (
    WorkspaceDialogController,
    WorkspaceDialogViews,
)
from manuskript.ui.workspace_transfers import (
    WorkspaceTransferController,
    WorkspaceTransferViews,
)
from manuskript.ui.plugins.controller import PluginUiController
from manuskript.ui.plugins.plugin_ui_views import PluginUiViews
from manuskript.ui.plugins.index_card_styles import (
    IndexCardStyleService,
)
from manuskript.ui.welcome_context import welcome_context_for

# Spellcheck support
from manuskript.ui.views.textEditView import textEditView
from manuskript.ui.view_configuration import (
    MainViewConfiguration,
    ViewConfigurationViews,
    ViewSettingsMenuBuilder,
    ViewSettingsMenuViews,
)
from manuskript.services.workspace_state import (
    PRIMARY as WORKSPACE_PRIMARY,
)
from manuskript.ui.workspace_state_controller import (
    WorkspaceStateController,
    WorkspaceStateViews,
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

    def __init__(self, services, window_id=WORKSPACE_PRIMARY):
        """One view of an application composed elsewhere.

        Everything application- or project-scope arrives in ``services``,
        whole. A window builds none of it and cannot: it used to take the
        same things as ten optional arguments and compose a fallback for
        each one it was not given, so a window handed nothing quietly
        became a second application -- its own panel registry, its own
        preferences, its own project -- while looking like a view of the
        first. Opening a second window meant re-listing all ten at the
        other call site, which is where such a thing would actually
        happen.

        ``window_id`` stays a separate argument because it is the one
        thing that is this window's own: it names where this window's
        layout is filed.
        """
        QMainWindow.__init__(self)
        self.setupUi(self)
        #: Kept whole so another window can be opened from this one
        #: without naming the services one at a time.
        self.services = services

        # Var
        self._lastFocus = None
        self._lastMDEditView = None
        self._markdownPresentationState = None
        self._defaultCursorFlashTime = 1000 # Overridden at startup with system
                                            # value. In manuskript.main.
        self._autoLoadProject = None  # Used to load a command line project
        self._restoredWorkspaceWindows = False
        self.writingSession = WritingSessionProgress()
        self._previousSelectionEmpty = True
        self.documentCommands = DocumentCommandRouter(
            lambda: self._lastFocus
        )
        self.markupCommands = MarkupCommandRouter(
            lambda: self._lastMDEditView
        )
        # The project layer. A window is one view of it and never its
        # owner, so this is always something it was handed.
        self.projectRuntime = services.project_runtime
        # Which windows are workspaces. Registering makes this one count
        # towards "the last window", and towards where commands go.
        self.windowRegistry = services.window_registry
        self.windowRegistry.register(self)
        self.applicationPreferences = services.application_preferences
        self.projectRuntime.settingsManager.configure_cursor_flash_time(
            lambda: self._defaultCursorFlashTime
        )
        self.referenceService = None
        self.textEditorContext = None
        # This window's layout, filed under this window. Two windows
        # sharing one set of keys meant the second saved over the first.
        self.windowId = window_id

        # Application scope: every window reads the same panel list.
        self.panelRegistry = services.panel_registry
        # Window scope: this window's own copies of whatever the shared
        # registry describes, findable from the other windows through the
        # application's one directory.
        self.panelDirectory = services.panel_directory
        self.panelHost = PanelHost(
            PanelWindow.for_window(self),
            self.panelRegistry,
            self.panelDirectory,
        )

        # UI. Panels are built before saved state is applied: a splitter
        # can only take back its saved sizes once every widget it is
        # meant to split exists.
        with timing.span("window.panels"):
            self.setupMoreUi()
        self.windowState = WorkspaceStateController(
            WorkspaceStateViews.for_window(self),
            window_id=window_id,
        )
        # Now every core panel exists, compose the controllers from their
        # explicit view contracts. Navigation used to be built before the
        # project tree and kept the whole window so it could find it later.
        self.navigationController = NavigationController(
            MainNavigationView(
                NavigationViews.for_window(self),
                self.projectRuntime,
            )
        )
        self.history = self.navigationController.history
        self.panelNavigation = PanelNavigation(self.navigationController)
        self.panelDialogs = PanelDialogs(self.centralWidget(), self.tr)
        self.characterController = CharacterController(
            CharacterModels(self.projectRuntime),
            CharacterPanelView.for_window(self),
            self.panelNavigation,
            self.panelDialogs,
        )
        self.plotController = PlotController(
            PlotModels(self.projectRuntime),
            PlotPanelView.for_window(self),
            self.panelNavigation,
            self.panelDialogs,
        )
        self.worldController = WorldController(
            WorldModels(self.projectRuntime),
            WorldPanelView.for_window(self),
            self.panelNavigation,
            self.panelDialogs,
        )
        self.viewConfigurationController = (
            ViewConfigurationController(
                MainViewConfiguration(
                    ViewConfigurationViews.for_window(self)
                ),
                self.projectRuntime.settingsManager,
            )
        )
        self.viewSettingsMenu = ViewSettingsMenuBuilder(
            ViewSettingsMenuViews.for_window(self),
            self.viewConfigurationController,
        )
        # After the panels exist: a splitter can only take back its
        # saved sizes once every widget it splits is there, and panel
        # visibility is restored by panel id through the host.
        with timing.span("window.layout"):
            self.windowState.restore()
        self.statusLabel = statusLabel(parent=self)
        self.statusLabel.setAutoFillBackground(True)
        self.statusLabel.hide()
        self.statusPresenter = StatusPresenter(
            StatusPresenterViews.for_window(self, self.statusLabel)
        )
        self.pluginRuntime = services.plugin_runtime
        self.pluginOptionStore = services.plugin_option_store
        self.mediaTypes = services.media_types
        self.mediaTypePreferences = services.media_type_preferences
        self.externalProcessRunner = ExternalProcessRunner()
        self.externalToolPaths = ExternalToolPaths()
        self.workspaceTransfers = WorkspaceTransferController(
            WorkspaceTransferViews.for_window(self)
        )
        self.cardStyles = IndexCardStyleService(
            self.pluginRuntime.registry
            if self.pluginRuntime is not None
            else None,
            report_error=self.statusPresenter.show,
            parent=self,
        )
        # Application scope: what plugins contribute, and the one
        # announcement that it changed. None where plugins are not
        # running, which is an application with no plugin interface --
        # not a reason for this window to invent one.
        self.pluginContributions = services.plugin_contributions
        self.pluginUi = (
            PluginUiController(
                PluginUiViews.for_window(self),
                self.pluginContributions,
                option_store=self.pluginOptionStore,
                media_types=self.mediaTypes,
            )
            if self.pluginContributions is not None
            else None
        )
        self.buildWorkspaceMenu()
        self.projectLifecycleView = ProjectLifecycleView(
            self.projectRuntime,
            ProjectLifecycleViews.for_window(self),
        )
        self.themeRepository = ThemeRepository()
        self.themePreviewRenderer = ThemePreviewRenderer()
        # The runtime builds the manager around the view side this
        # window supplies, rather than the window building one for
        # itself: the project is the runtime's, the view is the
        # window's.
        self.projectManager = self.projectRuntime.attach(
            self.projectLifecycleView,
            workspace=self,
        )
        # Project bindings receive stable, grouped widget contracts. Models
        # remain runtime-owned and are resolved only when a project binds,
        # because opening another project replaces the entire model set.
        self.projectBinding = ProjectBinding(
            ProjectBindingViews.for_window(self),
            self.projectRuntime,
            ProjectFeatureBinding(
                self.characterController,
                self.plotController,
                self.worldController,
                self.projectRuntime.settingsManager,
            ),
            contexts_factory=lambda: ProjectContextBinding(
                ProjectViewSet.for_window(self)
            ),
        )
        self.projectHistory = self.projectManager.last_project_store
        self.workspaceDialogs = WorkspaceDialogController(
            WorkspaceDialogViews.for_window(self)
        )
        self.buildDeveloperMenu()
        self.welcome.set_context(
            welcome_context_for(
                self,
                self.projectRuntime.settingsManager,
                self.projectHistory,
                self.projectRuntime,
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
        # Before the tool windows go, because closing them takes the
        # plugin docks out of the layout and QMainWindow.saveState can
        # only record docks that are still there. The last window comes
        # through here having already captured during the project close,
        # and captures again to no effect: it is showing the welcome
        # screen by now, which is the condition capture_layout declines
        # on, so the good capture stands.
        self.windowState.capture_layout()
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
        anchor = before[0] if before else None
        self.menuView.insertAction(anchor, self.actNewWindow)

        self.menuFloatPanel = QMenu(self.tr("&Float Panel"), self)
        self.menuFloatPanel.setObjectName("menuFloatPanel")
        self.menuFloatPanel.aboutToShow.connect(self.buildPanelFloatMenu)
        self.menuView.insertMenu(anchor, self.menuFloatPanel)

        self.menuMovePanel = QMenu(self.tr("Move &Panel To"), self)
        self.menuMovePanel.setObjectName("menuMovePanel")
        self.menuMovePanel.aboutToShow.connect(self.buildPanelMoveMenu)
        self.menuView.insertMenu(anchor, self.menuMovePanel)
        self.menuView.insertSeparator(anchor)

    def movePanelTo(self, panel_id, target):
        """Hand one of this window's panels to another window.

        The panel changes owner: the same widget, still bound to the
        same project models, mounted in the target and toggled from
        there. Nothing is rebuilt, so nothing it was showing is lost.
        """
        if target is self:
            return self.panelHost.instance(panel_id)
        if target.panelHost.instance(panel_id) is not None:
            # Checked before releasing: a refused adoption after a
            # release would leave the panel belonging to nobody.
            return None
        instance = self.panelHost.release(panel_id)
        if instance is None:
            return None
        adopted = target.panelHost.adopt(instance)
        self.toolbar.removePanelToggle(panel_id)
        target.toolbar.addPanelToggle(
            adopted.action,
            adopted.widget,
            adopted.descriptor.group,
            panel_id=panel_id,
        )
        return adopted

    def togglePanelFloating(self, panel_id):
        """Float a docked panel, or put a floating one back."""
        instance = self.panelHost.instance(panel_id)
        if instance is None:
            return None
        if panel_id in self.panelHost.floating():
            moved = self.panelHost.redock(panel_id)
        else:
            moved = self.panelHost.tear_off(panel_id)
        if moved is not None:
            self.toolbar.removePanelToggle(panel_id)
            self.toolbar.addPanelToggle(
                moved.action,
                moved.widget,
                moved.descriptor.group,
                panel_id=panel_id,
            )
        return moved

    def buildPanelFloatMenu(self):
        """Offer each panel of this window a float or a re-dock."""
        self.menuFloatPanel.clear()
        floating = set(self.panelHost.floating())
        for panel_id, instance in sorted(
            self.panelHost.instances.items()
        ):
            action = self.menuFloatPanel.addAction(
                self.tr(instance.descriptor.title)
            )
            # Carries which panel it acts on, so nothing has to read it
            # back off a translated label.
            action.setData(panel_id)
            action.setCheckable(True)
            action.setChecked(panel_id in floating)
            action.triggered.connect(
                partial(self.togglePanelFloating, panel_id)
            )
        if not self.panelHost.instances:
            action = self.menuFloatPanel.addAction(
                self.tr("No panel in this window")
            )
            action.setEnabled(False)

    def buildPanelMoveMenu(self):
        """Offer each of this window's panels to each other window.

        Rebuilt when shown rather than kept current: which windows exist
        changes underneath it, and a stale entry would move a panel into
        a window that has gone.
        """
        self.menuMovePanel.clear()
        others = [
            window
            for window in self.windowRegistry.workspace_windows
            if window is not self
        ]
        offered = 0
        for panel_id, instance in sorted(
            self.panelHost.instances.items()
        ):
            # Only windows that do not already show this panel can take
            # it. Every window builds its own core panels, so those have
            # nowhere to go -- tearing one off is the move that makes
            # sense for them.
            targets = [
                window
                for window in others
                if window.panelHost.instance(panel_id) is None
            ]
            if not targets:
                continue
            submenu = self.menuMovePanel.addMenu(
                self.tr(instance.descriptor.title)
            )
            submenu.menuAction().setData(panel_id)
            offered += 1
            for window in targets:
                action = submenu.addAction(window.windowTitle())
                action.setData(panel_id)
                action.triggered.connect(
                    partial(self.movePanelTo, panel_id, window)
                )
        if not offered:
            action = self.menuMovePanel.addAction(
                self.tr("No panel can move to another window")
                if others
                else self.tr("No other window open")
            )
            action.setEnabled(False)

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

        The same services object, passed on whole rather than unpacked and
        re-listed. Every application-scope thing the new window sees is
        therefore the same instance this one sees -- one project, one panel
        list, one set of plugins -- and a service added later cannot arrive
        in the first window and be forgotten here.

        It joins a project already open instead of going through the
        welcome screen.
        """
        window = MainWindow(
            self.services,
            window_id=window_id or self.nextWorkspaceId(),
        )
        window.adoptOpenProject()
        window.show()
        return window

    def adoptOpenProject(self):
        """Show the project this window's runtime already has open.

        A first window reaches a project by loading one; a later window
        finds it already loaded and only has to catch its own widgets
        up -- signals connected and saved view settings applied. Models
        stay in the shared runtime; a window never owns or installs them.
        """
        runtime = self.projectRuntime
        if not runtime.isOpen:
            return False
        view = self.projectLifecycleView
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
        self.workspaceDialogs.close_all()
        self.workspaceTransfers.close_all()
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
                id = self.projectRuntime.models.outline.ID(index)
                self.pushHistory(("outline", id))
                self._previousSelectionEmpty = id is not None
            else:
                self.pushHistory(("outline", None))
                self._previousSelectionEmpty = False
        elif tabIndex == self.TabRedac:
            tree = self.corePanels.project_tree.tree
            index = tree.selectionModel().currentIndex()
            if index.isValid():
                id = self.projectRuntime.models.outline.ID(index)
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
            self.corePanels.project_tree.tree,
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
        
        self.pushHistory((
            "outline", self.projectRuntime.models.outline.ID(index),
        ))
        self._previousSelectionEmpty = False


    def outlineRemoveItemsRedac(self):
        self.corePanels.project_tree.tree.delete()

    def outlineRemoveItemsOutline(self):
        self.treeOutlineOutline.delete()

    ###############################################################################
    # EDITOR
    ###############################################################################

    def redacOutlineChanged(self):
        index = (
            self.corePanels.project_tree.tree
            .selectionModel().currentIndex()
        )
        if not index.isValid():
            self.pushHistory(("redac", None))
            self._previousSelectionEmpty = True
            return
        
        self.pushHistory((
            "redac", self.projectRuntime.models.outline.ID(index),
        ))
        self._previousSelectionEmpty = False

    def openIndex(self, index):
        self.corePanels.project_tree.tree.setCurrentIndex(index)

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
                PanelContext(translate=self.tr),
            )
            if instance is None:
                continue
            self.toolbar.addPanelToggle(
                instance.action,
                instance.widget,
                instance.descriptor.group,
                panel_id=panel_id,
            )

        self.corePanels = CorePanelViewSet.from_host(self.panelHost)

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
        settings = self.projectRuntime.settingsManager
        if settings.dict is None:
            settings.dict = Spellchecker.getDefaultDictionary()

        # Check if project dict is unavailable on this machine
        dict_available = False
        for lib, dicts in dictionaries.items():
            if dict_available:
                break
            for i in dicts:
                if Spellchecker.normalizeDictName(lib, i) == settings.dict:
                    dict_available = True
                    break
        # Reset dict to default one if it's unavailable
        if not dict_available:
            settings.dict = Spellchecker.getDefaultDictionary()

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
                if Spellchecker.normalizeDictName(lib, i) == settings.dict:
                    a.setChecked(True)
                a.triggered.connect(self.setDictionary, F.AUC)
                self.menuDictGroup.addAction(a)
                self.menuDict.addAction(a)
            self.menuDict.addSeparator()

        # If a new dictionary was chosen, apply the change and re-enable spellcheck if it was enabled.
        if not dict_available:
            self.setDictionary()
            self.toggleSpellcheck(settings.spellcheck)

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
                settings = self.projectRuntime.settingsManager
                settings.dict = Spellchecker.normalizeDictName(
                    i.data,
                    i.text().replace("&", ""),
                )

                # Find all textEditView from self, and toggle spellcheck
                for w in self.findChildren(textEditView, QRegExp(".*"),
                                           Qt.FindChildrenRecursively):
                    w.setDict(settings.dict)

    def openSpellcheckWebPage(self, lib):
        F.openURL(Spellchecker.getLibraryURL(lib))

    def toggleSpellcheck(self, val):
        self.projectRuntime.settingsManager.spellcheck = val

        # Find all textEditView from self, and toggle spellcheck
        for w in self.findChildren(textEditView, QRegExp(".*"),
                                   Qt.FindChildrenRecursively):
            w.toggleSpellcheck(val)

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
        self.actMediaTypes.triggered.connect(
            self.workspaceDialogs.show_media_types
        )
        self.menuDeveloper.addAction(self.actMediaTypes)

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
