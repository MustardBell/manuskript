#!/usr/bin/env python
# --!-- coding: utf8 --!--
import importlib

from PyQt5.QtCore import (pyqtSignal, QSignalBlocker, Qt,
                          QUrl, QSize)
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDockWidget,
    QLabel,
    QListWidgetItem,
    QMainWindow,
    QTabWidget,
    QWidget,
)

from manuskript.commands import DocumentCommandRouter, MarkupCommandRouter
from manuskript.domain.writing_session import WritingSessionProgress
from manuskript.controllers.navigation_controller import NavigationController
from manuskript.controllers.view_configuration_controller import (
    ViewConfigurationController,
)
from manuskript.panels import PanelContext
from manuskript.panels import core as core_panels
from manuskript.panels import group_of as _group_of
from manuskript.panels.core import register_core_panels
from manuskript.ui.panels import PanelHost
from manuskript.ui.panels.placement import (
    PanelPlacementController,
    PanelPlacementViews,
)
from manuskript.ui.panels.window_port import PanelWindow
from manuskript.ui.surface_presentation import CentralSurfacePresentation
from manuskript.ui.workspace_surfaces import WorkspaceSurfaceHost
from manuskript.ui.panels.core import (
    CorePanelViewSet,
    core_panel_factories,
)
from manuskript import timing
import manuskript.functions as F
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
from manuskript.ui.markdown_menu_controller import (
    MarkdownMenuController,
    MarkdownMenuViews,
)
from manuskript.ui.menu_tooltips import MenuTooltipController
from manuskript.ui.navigation_view import MainNavigationView, NavigationViews
from manuskript.ui.project_binding import ProjectBinding
from manuskript.ui.project_binding_views import ProjectBindingViews
from manuskript.ui.project_context_binding import ProjectContextBinding
from manuskript.ui.project_feature_binding import ProjectFeatureBinding
from manuskript.ui.entity_workspace import EntityWorkspaceController
from manuskript.ui.project_lifecycle import ProjectLifecycleView
from manuskript.ui.project_lifecycle_views import ProjectLifecycleViews
from manuskript.ui.project_view_set import ProjectViewSet
from manuskript.ui.editors.themes import ThemePreviewRenderer
from manuskript.ui.statusLabel import statusLabel
from manuskript.ui.status_presenter import (
    StatusPresenter,
    StatusPresenterViews,
)
from manuskript.ui.spellcheck_controller import (
    SpellcheckController,
    SpellcheckViews,
)
from manuskript.ui.workspace_dialogs import (
    WorkspaceDialogController,
    WorkspaceDialogViews,
)
from manuskript.ui.workspace_transfers import (
    WorkspaceTransferController,
    WorkspaceTransferViews,
)
from manuskript.ui.workspace_windows import (
    WorkspaceWindowController,
    WorkspaceWindowViews,
)
from manuskript.ui.workspace_lifetime import WorkspaceLifetime
from manuskript.ui.workspace_focus import (
    WorkspaceFocusController,
    WorkspaceFocusViews,
)
from manuskript.ui.workspace_selection import (
    WorkspaceSelectionController,
    WorkspaceSelectionHistory,
    WorkspaceSelectionViews,
)
from manuskript.ui.workspace_search import (
    WorkspaceSearchController,
    WorkspaceSearchViews,
)
from manuskript.ui.workspace_project_binding import (
    WorkspaceProjectBinding,
)
from manuskript.ui.window_placement import (
    WindowPlacementController,
    WindowPlacementViews,
)
from manuskript.ui.workspace_support import (
    WorkspaceSupportController,
    WorkspaceSupportViews,
)
from manuskript.ui.plugins.controller import PluginUiController
from manuskript.ui.plugins.plugin_ui_views import PluginUiViews
from manuskript.ui.plugins.index_card_styles import (
    IndexCardStyleService,
)
from manuskript.ui.welcome_context import welcome_context_for

from manuskript.ui.view_configuration import (
    MainViewConfiguration,
    ViewConfigurationViews,
    ViewSettingsMenuBuilder,
    ViewSettingsMenuViews,
)
from manuskript.services.workspace_state import (
    PRIMARY as WORKSPACE_PRIMARY,
)
from manuskript.ui.workspace_navigator import (
    NavigatorTarget,
    WorkspaceNavigator,
)
from manuskript.ui.workspace_state_controller import (
    WorkspaceStateController,
    WorkspaceStateViews,
)
import logging
LOGGER = logging.getLogger(__name__)

class MainWindow(QMainWindow, Ui_MainWindow):
    # dictChanged = pyqtSignal(str)

    DebugPage = 0

    #: The only central page left is the opt-in developer view. Every
    #: project surface contributes its own row through its panel descriptor.
    NAVIGATOR_PAGES = (
        NavigatorTarget(
            "Debug", "applications-debugging", 800, page=DebugPage,
        ),
    )

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
        if window_id != WORKSPACE_PRIMARY:
            # A secondary workspace has no application-lifetime owner.  If
            # close merely hides it, its large parented Qt tree is eventually
            # destroyed by Python's cyclic collector, which SIP cannot do
            # safely once C++-owned child wrappers are involved.
            self.setAttribute(Qt.WA_DeleteOnClose)
        self.setupUi(self)
        # The welcome screen, and the pages the project is shown in. The
        # central widget used to be taken out of the window entirely while
        # a project was open, so that docked surfaces could have its space;
        # surfaces live in it now, and the tool panels are what orbits.
        self._centralSurface = self.centralWidget()
        self._projectSurfaceActive = False
        # Where a workspace that has never been told otherwise starts.
        # General, because that is what a reader opening Manuskript for
        # the first time has always been shown.
        self._activePanelId = core_panels.GENERAL
        # Without GroupedDragging: it is the only thing that builds a
        # QDockWidgetGroupWindow, and closing every dock inside one
        # leaves the frame behind -- an empty window wearing this
        # window's own title, which nothing in the application owns or
        # can put away.
        self.setDockOptions(
            QMainWindow.AnimatedDocks
            | QMainWindow.AllowNestedDocks
            | QMainWindow.AllowTabbedDocks
        )
        # Tabs above what they switch, not below it. Qt puts a dock area's
        # tab bar at the bottom by default, which reads as belonging to
        # the panel underneath rather than choosing between the panels
        # above -- and every other tab bar in this window is on top.
        self.setTabPosition(Qt.AllDockWidgetAreas, QTabWidget.North)
        self.actUpgradeProjectFormat = QAction(
            self.tr("Upgrade Project Format…"), self
        )
        self.actUpgradeProjectFormat.setObjectName(
            "actUpgradeProjectFormat"
        )
        self.actUpgradeProjectFormat.setStatusTip(self.tr(
            "Create and validate a separate Project Format 2 copy"
        ))
        self.menuFile.insertAction(
            self.actImport, self.actUpgradeProjectFormat
        )
        #: Kept whole so another window can be opened from this one
        #: without naming the services one at a time.
        self.services = services
        self.workspaceLifetime = WorkspaceLifetime()

        # Var
        self._autoLoadProject = None  # Used to load a command line project
        self.writingSession = WritingSessionProgress()
        # The project layer. A window is one view of it and never its
        # owner, so this is always something it was handed.
        self.projectRuntime = services.project_runtime
        # Which windows are workspaces. Registering makes this one count
        # towards "the last window", and towards where commands go.
        self.windowRegistry = services.window_registry
        self.applicationPreferences = services.application_preferences
        # This window's layout, filed under this window. Two windows
        # sharing one set of keys meant the second saved over the first.
        self.windowId = window_id

        # Application scope: every window reads the same panel list.
        self.panelRegistry = services.panel_registry
        # Window scope: this window's own copies of whatever the shared
        # registry describes, findable from the other windows through the
        # application's one directory.
        self.panelDirectory = services.panel_directory
        self.panelHost = self.workspaceLifetime.own(
            PanelHost(
                PanelWindow.for_window(self),
                self.panelRegistry,
                self.panelDirectory,
            )
        )
        # The places the writer goes have their own owner. They are not
        # tool panels and they are not docks: they are shown as pages of
        # the window's central container, which is the one the navigator
        # has always driven, so a surface gets a window's worth of room
        # rather than the 230 pixels a dock beside the editor gave it.
        self.surfaceHost = self.workspaceLifetime.own(
            WorkspaceSurfaceHost(
                self.panelRegistry,
                CentralSurfacePresentation(self.tabMain),
            )
        )

        # UI. Panels are built before saved state is applied: a splitter
        # can only take back its saved sizes once every widget it is
        # meant to split exists.
        with timing.span("window.panels"):
            self.setupMoreUi()
        self.workspaceFocus = self.workspaceLifetime.own(
            WorkspaceFocusController(
                WorkspaceFocusViews.for_window(self)
            )
        )
        self.mainEditor.set_focus_source(self.workspaceFocus)
        self.workspaceSearch = self.workspaceLifetime.own(
            WorkspaceSearchController(
                WorkspaceSearchViews.for_window(self)
            )
        )
        self.windowPlacement = self.workspaceLifetime.own(
            WindowPlacementController(
                WindowPlacementViews.for_window(self)
            )
        )
        self.documentCommands = DocumentCommandRouter(
            self.workspaceFocus.current_document_target
        )
        self.markupCommands = MarkupCommandRouter(
            self.workspaceFocus.current_markup_target
        )
        self.markdownMenu = self.workspaceLifetime.own(
            MarkdownMenuController(
                MarkdownMenuViews.for_window(self)
            )
        )
        self.spellcheck = self.workspaceLifetime.own(
            SpellcheckController(
                SpellcheckViews.for_window(self),
                self.projectRuntime.settingsManager,
            )
        )
        self.windowState = self.workspaceLifetime.own(
            WorkspaceStateController(
                WorkspaceStateViews.for_window(self),
                window_id=window_id,
            )
        )
        # Now every core panel exists, compose the controllers from their
        # explicit view contracts. Navigation used to be built before the
        # project tree and kept the whole window so it could find it later.
        self.navigationController = self.workspaceLifetime.own(
            NavigationController(
                MainNavigationView(
                    NavigationViews.for_window(self),
                    self.projectRuntime,
                )
            )
        )
        self.selectionHistory = self.workspaceLifetime.own(
            WorkspaceSelectionHistory(self.navigationController)
        )
        self.entityWorkspace = self.workspaceLifetime.own(
            EntityWorkspaceController(
                self,
                self.projectRuntime,
                (
                    self.corePanels.project_entities,
                    self.corePanels.character_entities,
                    self.corePanels.plot_entities,
                    self.corePanels.world_entities,
                ),
            )
        )
        self.workspaceSelection = self.workspaceLifetime.own(
            WorkspaceSelectionController(
                WorkspaceSelectionViews.for_window(self),
                self.projectRuntime,
                self.selectionHistory,
                {},
            )
        )
        self.workspaceFocus.subscribe(self.workspaceSelection.focus_changed)
        self.viewConfigurationController = self.workspaceLifetime.own(
            ViewConfigurationController(
                MainViewConfiguration(
                    ViewConfigurationViews.for_window(self)
                ),
                self.projectRuntime.settingsManager,
            )
        )
        self.viewSettingsMenu = self.workspaceLifetime.own(
            ViewSettingsMenuBuilder(
                ViewSettingsMenuViews.for_window(self),
                self.viewConfigurationController,
            )
        )
        # After the panels exist: a splitter can only take back its
        # saved sizes once every widget it splits is there, and panel
        # visibility is restored by panel id through the host.
        with timing.span("window.layout"):
            self.windowState.restore()
            if not self.windowState.restoredLayout:
                self._placeDefaultCoreDocks()
        self.statusLabel = statusLabel(parent=self)
        self.statusLabel.setAutoFillBackground(True)
        self.statusLabel.hide()
        self.statusPresenter = self.workspaceLifetime.own(
            StatusPresenter(
                StatusPresenterViews.for_window(self, self.statusLabel)
            )
        )
        self.pluginRuntime = services.plugin_runtime
        self.pluginOptionStore = services.plugin_option_store
        self.mediaTypes = services.media_types
        self.mediaTypePreferences = services.media_type_preferences
        self.externalProcessRunner = ExternalProcessRunner()
        self.externalToolPaths = ExternalToolPaths()
        self.workspaceTransfers = self.workspaceLifetime.own(
            WorkspaceTransferController(
                WorkspaceTransferViews.for_window(self)
            )
        )
        self.workspaceSupport = self.workspaceLifetime.own(
            WorkspaceSupportController(
                WorkspaceSupportViews.for_window(self)
            )
        )
        self.cardStyles = self.workspaceLifetime.own(
            IndexCardStyleService(
                self.pluginRuntime.registry
                if self.pluginRuntime is not None
                else None,
                report_error=self.statusPresenter.show,
                parent=self,
            )
        )
        # Application scope: what plugins contribute, and the one
        # announcement that it changed. None where plugins are not
        # running, which is an application with no plugin interface --
        # not a reason for this window to invent one.
        self.pluginContributions = services.plugin_contributions
        self.pluginUi = (
            self.workspaceLifetime.own(
                PluginUiController(
                    PluginUiViews.for_window(self),
                    self.pluginContributions,
                    option_store=self.pluginOptionStore,
                    media_types=self.mediaTypes,
                )
            )
            if self.pluginContributions is not None
            else None
        )
        # Project bindings receive stable, grouped widget contracts. Models
        # remain runtime-owned and are resolved only when a project binds,
        # because opening another project replaces the entire model set.
        self.projectBinding = self.workspaceLifetime.own(
            ProjectBinding(
                ProjectBindingViews.for_window(self),
                self.projectRuntime,
                ProjectFeatureBinding(
                    self.entityWorkspace,
                ),
                contexts_factory=lambda: ProjectContextBinding(
                    ProjectViewSet.for_window(self)
                ),
            )
        )
        self.workspaceProject = self.workspaceLifetime.own(
            WorkspaceProjectBinding(
                self.projectBinding,
                self.markdownMenu,
            )
        )
        self.projectLifecycleView = self.workspaceLifetime.own(
            ProjectLifecycleView(
                self.projectRuntime,
                ProjectLifecycleViews.for_window(self),
            )
        )
        self.workspaceWindows = self.workspaceLifetime.own(
            WorkspaceWindowController(
                WorkspaceWindowViews.for_window(self)
            )
        )
        self.buildWorkspaceMenu()
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
        self.projectHistory = self.projectManager.last_project_store
        self.workspaceDialogs = self.workspaceLifetime.own(
            WorkspaceDialogController(
                WorkspaceDialogViews.for_window(self)
            )
        )
        self.buildDeveloperMenu()
        self.welcome.set_context(
            self.workspaceLifetime.own(
                welcome_context_for(
                    self,
                    self.projectRuntime.settingsManager,
                    self.projectHistory,
                    self.projectRuntime,
                )
            )
        )

        # Welcome
        self.welcome.updateValues()
        self.switchToWelcome()

        self.actionBinding = self.workspaceLifetime.own(
            MainWindowActionBinding(self)
        )
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

        # Register only after successful composition.  A constructor that
        # fails halfway must not leave a phantom workspace in the application
        # registry, and focus routing now has an explicit destination.
        self.windowRegistry.register(
            self,
            self.workspaceFocus.focus_changed,
        )

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
        self._projectSurfaceActive = False
        # Hides the toolbar
        self.toolbar.setVisible(False)
        # Switch to welcome screen
        if self.centralWidget() is None:
            self.setCentralWidget(self._centralSurface)
        self.stack.show()
        self.stack.setCurrentIndex(0)

    def switchToProject(self):
        """Restores docks and toolbar visibility, and switch to project."""
        self._projectSurfaceActive = True
        self.windowState.restore_project_docks()
        # Show the toolbar
        self.toolbar.setVisible(True)
        # The project is shown in the central pages, with the tool panels
        # around them. Taking the central widget out was what gave docked
        # surfaces the window's whole area; a surface has that area now
        # because it is what is in the middle.
        self._showCentralPages()
        if not self._activePanelId:
            self._activePanelId = core_panels.GENERAL
        self.activatePanel(self._activePanelId)

    def closeEvent(self, event):
        """Close this window, and the project only with the last one.

        A workspace window is one view of a project. Closing it puts
        that view away; the project goes when its last window does, and
        that is the only close that may ask about unsaved changes.
        """
        is_last = self.windowRegistry.is_last(self)
        if is_last:
            if not self.projectManager.closeProject():
                event.ignore()
                return
            if not self.windowRegistry.quitting:
                # Closed one at a time rather than quit: the windows
                # still open are the session to come back to.
                self.windowState.store.set_open_windows(
                    self.workspaceWindows.open_ids()
                )
        else:
            # These editors are private to this view and disappear when its
            # bindings are disconnected.  Shared document buffers outlive a
            # workspace, but character notes and other panel editors do not.
            self.projectLifecycleView.flush_pending_edits()
        # Before the tool windows go, because closing them takes the
        # plugin docks out of the layout and QMainWindow.saveState can
        # only record docks that are still there. The last window comes
        # through here having already captured during the project close,
        # and captures again to no effect: it is showing the welcome
        # screen by now, which is the condition capture_layout declines
        # on, so the good capture stands.
        self.windowState.capture_layout()
        self.closeToolWindows()
        # A non-last workspace does not close the shared project, so the
        # project manager will not broadcast disconnect_project for it.  Its
        # own runtime-model signals must still be released before the Qt tree
        # goes away.  On the last workspace this is an idempotent second call.
        self.workspaceProject.disconnect()
        self.windowState.save()
        self.projectRuntime.detach(self.projectLifecycleView)
        self.windowRegistry.unregister(self)
        self.workspaceLifetime.dispose()
        super().closeEvent(event)

    @staticmethod
    def _entityPanelIds():
        return (
            core_panels.PROJECT_ENTITIES,
            core_panels.CHARACTER_ENTITIES,
            core_panels.PLOT_ENTITIES,
            core_panels.WORLD_ENTITIES,
        )

    def _offerPanelToggle(self, instance):
        """Give a newly mounted panel its button in the toolbar."""
        self.toolbar.addPanelToggle(
            instance.action,
            instance.widget,
            _group_of(instance.descriptor),
            panel_id=instance.descriptor.id,
        )
        placement = getattr(self, "panelPlacement", None)
        if placement is not None:
            placement.watch_dock(instance.container)

    def navigateTo(self, row):
        """Open what a navigator row stands for: a page, or a surface."""
        target = self.navigator.target(row)
        if target is None:
            return False
        if target.opens_panel:
            return self.activatePanel(target.panel_id)
        self._activePanelId = ""
        self._showCentralPages()
        # The developer page is instrumentation rather than a place the
        # writer goes, so it is not a surface and is still addressed by
        # number, from NAVIGATOR_PAGES. Saying so out loud is what keeps
        # the host's answer worth anything: it would otherwise go on
        # naming the last surface while a reader looks at this.
        self.surfaceHost.deactivate()
        self.tabMain.setCurrentIndex(target.page)
        return False

    def _showCentralPages(self):
        """Put the central pages back in view, whatever was over them."""
        if self.centralWidget() is None:
            self.setCentralWidget(self._centralSurface)
        self.stack.show()
        self.stack.setCurrentIndex(1)

    def goToSurface(self, surface_id):
        """Show one of the places this workspace holds. Never builds one.

        Going somewhere is activation. Building was the other half of
        this until the navigator listed the whole registry: a row for a
        surface the workspace did not hold turned selecting it into an
        acquisition, so a window made to hold one surface filled up with
        seven, a click at a time, and nothing said so.

        Which surfaces a workspace holds changes by composition, by
        restoring, or by a surface arriving from another window -- all of
        them explicit, and none of them a selection in a list.

        Answers False for a surface this workspace has not got, and for
        anything that is not a surface, so the caller can ask the panel
        host instead.
        """
        if not self.surfaceHost.contains(surface_id):
            return False
        self._showCentralPages()
        return self.surfaceHost.activate(surface_id) is not None

    def activatePanel(self, panel_id):
        """Go to a surface, or reveal a tool panel, by stable identity."""
        if not panel_id:
            return False
        if not self.goToSurface(panel_id) and not self.panelHost.reveal(
            panel_id
        ):
            return False
        self._activePanelId = panel_id
        row = self.navigator.row_for_panel(panel_id)
        if row is not None and self.lstTabs.currentRow() != row:
            blocker = QSignalBlocker(self.lstTabs)
            self.lstTabs.setCurrentRow(row)
            del blocker
        selection = getattr(self, "workspaceSelection", None)
        if selection is not None:
            selection.surface_changed(panel_id)
        return True

    def notePanelFocus(self, panel_id):
        """Follow direct focus into a panel without showing it again.

        This records where the reader is working, which may be a tool
        panel. It is deliberately not what the window remembers as its
        surface: focusing the project tree would otherwise be filed as
        the workspace's current work surface, and the next launch would
        try to go to a place the navigator does not list.
        """
        self._activePanelId = str(panel_id or "")
        row = self.navigator.row_for_panel(self._activePanelId)
        if row is not None and self.lstTabs.currentRow() != row:
            blocker = QSignalBlocker(self.lstTabs)
            self.lstTabs.setCurrentRow(row)
            del blocker

    @staticmethod
    def panelIdForLegacyTab(tab):
        """Translate old saved tab positions without perpetuating them."""
        try:
            tab = int(tab)
        except (TypeError, ValueError):
            return ""
        return {
            0: core_panels.GENERAL,
            1: core_panels.PROJECT_ENTITIES,
            2: core_panels.CHARACTER_ENTITIES,
            3: core_panels.PLOT_ENTITIES,
            4: core_panels.WORLD_ENTITIES,
            5: core_panels.OUTLINE,
            6: core_panels.EDITOR,
        }.get(tab, "")

    def rebuildNavigator(self):
        """List the pages this window keeps and the surfaces it holds.

        Membership, not availability. The rows used to come from every
        surface in the registry, which is the application's list rather
        than this workspace's -- so a window that held one surface still
        offered all seven, and selecting one quietly built it here.

        Called again whenever this workspace gains or loses a surface, so
        a surface that leaves for another window takes its row with it and
        one that arrives brings its own.
        """
        held = [
            instance.descriptor
            for instance in self.surfaceHost.instances.values()
        ]
        self.navigator = WorkspaceNavigator.compose(
            pages=self.NAVIGATOR_PAGES, surfaces=held,
        )
        # Blocked while the list is refilled: clearing it moves the
        # current row through every position on the way to none, and each
        # of those is a navigation this window would otherwise perform.
        blocker = QSignalBlocker(self.lstTabs)
        self.lstTabs.clear()
        for target in self.navigator.targets:
            label = self.tr(target.label)
            item = QListWidgetItem(F.themeIcon(target.icon), label)
            item.setSizeHint(QSize(item.sizeHint().width(), 64))
            item.setToolTip(label)
            item.setTextAlignment(Qt.AlignCenter)
            self.lstTabs.addItem(item)
            if target.page is not None:
                self.tabMain.setTabIcon(target.page, item.icon())
        debug_row = self.navigator.row_for_page(self.DebugPage)
        if debug_row is not None:
            self.lstTabs.item(debug_row).setHidden(not self.SHOW_DEBUG_TAB)
        # The row that stands for what is showing, if it still has one.
        showing = self.surfaceHost.current()
        row = (
            self.navigator.row_for_panel(showing)
            if showing is not None
            else None
        )
        if row is not None:
            self.lstTabs.setCurrentRow(row)
        del blocker

    def _selectNavigatorPage(self, page):
        """Follow a page change back to the row that stands for it."""
        row = self.navigator.row_for_page(page)
        if row is not None:
            self.lstTabs.setCurrentRow(row)

    def _placeDefaultCoreDocks(self):
        """Put the tool panels around the surfaces, for a window with no
        arrangement of its own.

        Which is every window until one is saved, and every window whose
        saved one was written while the work surfaces were docks: such a
        layout names seven docks this build does not make, and applying it
        would leave Qt holding those names for the life of the profile.

        What is left to place is the navigator, the project tree and the
        two companions that share its column. Everything the navigator
        lists is in the middle now, so nothing here decides how much room
        a work surface gets -- it gets what the tool panels do not take.
        """

        def dock(panel_id):
            instance = self.panelHost.instance(panel_id)
            return instance.container if instance is not None else None

        project_tree = dock(core_panels.PROJECT_TREE)
        if project_tree is None:
            return

        self.addDockWidget(Qt.LeftDockWidgetArea, self.dckNavigation)
        self.addDockWidget(Qt.LeftDockWidgetArea, project_tree)
        self.splitDockWidget(
            self.dckNavigation, project_tree, Qt.Horizontal
        )

        for panel_id in (core_panels.METADATA, core_panels.STORYLINE):
            companion = dock(panel_id)
            if companion is not None:
                self.tabifyDockWidget(project_tree, companion)

        self.resizeDocks(
            (self.dckNavigation, project_tree),
            (160, 340),
            Qt.Horizontal,
        )
        project_tree.raise_()

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
        before = self.menuView.actions()
        anchor = before[0] if before else None
        self.menuView.insertAction(anchor, self.actNewWindow)
        self.panelPlacement = self.workspaceLifetime.own(
            PanelPlacementController(
                PanelPlacementViews.for_window(self, anchor=anchor)
            )
        )

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
    # GENERAL AKA UNSORTED
    ###############################################################################

    def setupMoreUi(self):

        # Tool bar on the right. The four workspace panels are declared
        # once in the shared registry and built per window; their
        # toggles come from the panel host so that anything showing a
        # panel and anything watching it agree on one action. They are
        # built first: window styling reaches into the project tree.
        self.toolbar = collapsibleDockWidgets(Qt.RightDockWidgetArea, self)
        register_core_panels(
            self.panelRegistry,
            factories=core_panel_factories(),
        )
        # Every panel this window mounts is offered in the toolbar, not
        # only the ones listed here: a plugin's panel is opened by the
        # plugin controller and would otherwise have no way into the
        # list every other panel appears in.
        self.panelHost.on_open = self._offerPanelToggle
        context = PanelContext(translate=self.tr)
        for panel_id in (
            core_panels.PROJECT_TREE,
            core_panels.METADATA,
            core_panels.STORYLINE,
        ):
            self.panelHost.open(panel_id, context)
        # Every core surface, in every new project's window. Which ones a
        # workspace holds is the workspace's own state -- a second window
        # built for one surface is not obliged to build the other six --
        # but a person opening a project gets all of them, which is what
        # the navigator has always listed.
        for surface_id in (
            core_panels.GENERAL,
            core_panels.PROJECT_ENTITIES,
            core_panels.CHARACTER_ENTITIES,
            core_panels.PLOT_ENTITIES,
            core_panels.WORLD_ENTITIES,
            core_panels.OUTLINE,
            core_panels.EDITOR,
        ):
            self.surfaceHost.open(surface_id, context)
        # Said here rather than left to whichever surface was opened first.
        # Which surface a fresh workspace starts on is composition's to
        # state, and upstream's answer -- the one a new reader gets -- is
        # General. A saved layout replaces this when there is one.
        self.surfaceHost.activate(core_panels.GENERAL)

        self.corePanels = CorePanelViewSet.from_hosts(
            tools=self.panelHost, surfaces=self.surfaceHost,
        )
        self._installCorePanelAliases()

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
        self.lstTabs.setIconSize(QSize(48, 48))
        self.rebuildNavigator()
        # Rebuilt again whenever this workspace gains or loses one, which
        # is how a row leaves with the surface it stood for.
        self.surfaceHost.on_membership_changed = self.rebuildNavigator
        self.tabMain.tabBar().hide()
        self.lstTabs.currentRowChanged.connect(self.navigateTo)
        self.tabMain.setTabEnabled(self.DebugPage, self.SHOW_DEBUG_TAB)
        self.tabMain.currentChanged.connect(self._selectNavigatorPage)

        # Help box
        references = [
            (self.corePanels.general,
             self.tr("Enter information about your book, and yourself."),
             0),
            (self.corePanels.outline,
             self.tr("Create the outline of your masterpiece."),
             0),
            (self.corePanels.editor,
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

    def _installCorePanelAliases(self):
        """Bridge old widget names while ports migrate to typed panels.

        The objects are the factory-built panel widgets, not reparented
        Designer pages. Keeping aliases for one migration window lets small
        adapters move independently without there being two live surfaces.

        These resolve structure that already exists and must never make any:
        the moment an alias can construct a surface, "which surfaces does
        this workspace have" stops being something a workspace states and
        becomes a consequence of whatever happened to be read first.
        """
        # The eight General aliases are gone: nothing read them. Checked for
        # dynamic access as well as literal, because a name reached by
        # getattr or from a .ui file would not show up in a search for the
        # attribute -- and reporting something absent because a search for
        # its name found nothing is a mistake this session has already made
        # twice.
        outline = self.corePanels.outline
        for name in (
            "splitterOutlineH", "splitterOutlineV", "lstOutlinePlots",
            "treeOutlineOutline", "outlineItemEditor",
            "btnOutlineAddFolder", "btnOutlineAddText",
            "btnOutlineRemoveItem", "btnPlanShowDetails",
        ):
            setattr(self, name, getattr(outline, name))
        self.mainEditor = self.corePanels.editor.editor

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
