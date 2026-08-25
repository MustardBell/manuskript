#!/usr/bin/env python
# --!-- coding: utf8 --!--
import importlib

from PyQt5.QtCore import (pyqtSignal, QSignalBlocker, QTimer, Qt,
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
from manuskript.ui.surface_presentation import DockSurfacePresentation
from manuskript.ui.surface_transfer import (
    FloatingSurfaceTransferController,
    FloatingSurfaceTransferViews,
    SurfaceTransferController,
    SurfaceTransferViews,
)
from manuskript.ui.workspace_surfaces import (
    WorkspaceBuildIntent,
    WorkspaceSurfaceError,
    WorkspaceSurfaceHost,
)
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
    SurfaceActionBinding,
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
from manuskript.ui.workspace_layout_reset import (
    WorkspaceLayoutResetController,
    WorkspaceLayoutResetViews,
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
from manuskript.ui.surface_panel_routing import (
    SurfacePanelRoutingController,
    SurfacePanelRoutingViews,
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
from manuskript.ui.workspace_retirement import (
    WorkspaceRetirementController,
    WorkspaceRetirementViews,
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

    def __init__(
        self,
        services,
        window_id=WORKSPACE_PRIMARY,
        build_intent=None,
    ):
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
        # The Designer string doubles as a menu mnemonic in old code, but a
        # dock title has no mnemonic rendering and displayed the ampersand as
        # a literal character once the title bar became visible.
        self.dckNavigation.setWindowTitle(
            self.dckNavigation.windowTitle().replace("&", "")
        )
        # This is an icon-and-label navigator, not an icon strip.  Letting
        # Qt compress it below the labels also made its nested-dock divider
        # appear stuck until a neighbouring split was moved first.
        self.dckNavigation.setMinimumWidth(200)
        # Relationships that only become expressible once a hidden default
        # companion is first revealed. Qt drops an all-hidden tab group, so
        # Reset records the intended peer and the visibility signal consumes
        # it exactly once instead of snapping a panel back forever after the
        # reader has arranged it elsewhere.
        self._pendingDefaultTabPeers = {}
        self._defaultPeerVisibilitySlots = {}
        # The welcome screen and opt-in Debug page are the only central
        # content. Project surfaces are independently owned native docks, so
        # this container leaves the window while a project is being shown.
        self._centralSurface = self.centralWidget()
        self._projectSurfaceActive = False
        # A peer workspace may adopt the already-open project while its
        # constructor is still composing the rest of the window.  Keep the
        # deferred-layout latch valid from the first possible lifecycle call;
        # the default-layout builder turns it on once there is work to settle.
        self._defaultDockLayoutPending = False
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
        self.buildIntent = build_intent or WorkspaceBuildIntent()
        self._standaloneSurfacePresentation = bool(
            self.buildIntent.standalone_surface
        )

        # Application scope: every window reads the same panel list.
        self.panelRegistry = services.panel_registry
        # Window scope: this window's own copies of whatever the shared
        # registry describes, findable from the other windows through the
        # application's one directory.
        self.panelDirectory = services.panel_directory
        self.panelWindow = PanelWindow.for_window(self)
        self.panelHost = self.workspaceLifetime.own(
            PanelHost(
                self.panelWindow,
                self.panelRegistry,
                self.panelDirectory,
            )
        )
        # The places the writer goes keep their own owner and bindings, but
        # each is presented in an independent native dock.  This is the
        # distinction the earlier central-page cutover erased: a surface is
        # not a tool-panel contribution, yet it must remain independently
        # visible, movable and floatable beside the Editor.
        self.surfacePresentation = self.workspaceLifetime.own(
            DockSurfacePresentation(self.panelWindow)
        )
        self.surfaceHost = self.workspaceLifetime.own(
            WorkspaceSurfaceHost(
                self.panelRegistry,
                self.surfacePresentation,
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
        self.surfaceHost.add_binding(self.workspaceFocus)
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
        self.surfaceActions = self.workspaceLifetime.own(
            SurfaceActionBinding(self.markdownMenu.attach)
        )
        self.surfaceHost.add_binding(self.surfaceActions)
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
                (),
            )
        )
        self.surfaceHost.add_binding(self.entityWorkspace)
        self.workspaceSelection = self.workspaceLifetime.own(
            WorkspaceSelectionController(
                WorkspaceSelectionViews.for_window(self),
                self.projectRuntime,
                self.selectionHistory,
                {},
            )
        )
        self.surfacePanelRouting = self.workspaceLifetime.own(
            SurfacePanelRoutingController(
                SurfacePanelRoutingViews.for_window(self)
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
            self._applyBuildIntentPresentation()
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
        if self.pluginUi is not None:
            self.surfaceHost.add_binding(self.pluginUi)
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
        self.surfaceHost.add_binding(self.projectBinding)
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
        self.workspaceRetirement = self.workspaceLifetime.own(
            WorkspaceRetirementController(
                WorkspaceRetirementViews.for_window(self)
            )
        )
        self.workspaceWindows = self.workspaceLifetime.own(
            WorkspaceWindowController(
                WorkspaceWindowViews.for_window(self)
            )
        )
        self.workspaceLayoutReset = self.workspaceLifetime.own(
            WorkspaceLayoutResetController(
                WorkspaceLayoutResetViews(
                    current_workspace=self,
                    workspaces=lambda: self.windowRegistry.workspace_windows,
                    identify=lambda workspace: workspace.windowId,
                    surface_host=lambda workspace: workspace.surfaceHost,
                    flush_pending_edits=lambda workspace: (
                        workspace.projectLifecycleView.flush_pending_edits()
                    ),
                    close_contributed_ui=lambda workspace: (
                        workspace._closeContributedWorkspaceUi()
                    ),
                    open_surface=lambda workspace, surface_id: (
                        workspace.surfaceHost.open(
                            surface_id,
                            PanelContext(translate=workspace.tr),
                        )
                    ),
                    activate_surface=lambda workspace, surface_id: (
                        workspace.activatePanel(surface_id)
                    ),
                    reconstruct_layout=lambda workspace: (
                        workspace._resetLocalWorkspaceLayout()
                    ),
                    close_workspace=lambda workspace: bool(
                        workspace.close()
                    ),
                    remember_session=lambda window_ids: (
                        self.windowState.store.set_open_windows(window_ids)
                    ),
                    show_status=lambda workspace, message, duration, level: (
                        workspace.statusPresenter.show(
                            workspace.tr(message), duration, level,
                        )
                    ),
                    core_surface_ids=core_panels.CORE_SURFACE_IDS,
                    default_surface=core_panels.GENERAL,
                )
            )
        )
        self.buildWorkspaceMenu()
        self.floatingSurfaceTransfer = self.workspaceLifetime.own(
            FloatingSurfaceTransferController(
                FloatingSurfaceTransferViews.for_window(self)
            )
        )
        self.surfaceHost.add_binding(self.floatingSurfaceTransfer)
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
        # Project surfaces are docks. Remove the welcome/debug container so
        # the dock layout owns the whole workspace instead of orbiting an
        # empty central placeholder.
        self._hideCentralPages()
        if not self._activePanelId:
            self._activePanelId = core_panels.GENERAL
        self.activatePanel(self._activePanelId)
        self._applyBuildIntentPresentation()
        if self._defaultDockLayoutPending:
            QTimer.singleShot(0, self._settleDefaultCoreDocks)

    def showEvent(self, event):
        """Settle routed dock extents once native window geometry exists."""

        super().showEvent(event)
        if getattr(self, "_defaultDockLayoutPending", False):
            self._settleDefaultCoreDocks()
        routing = getattr(self, "surfacePanelRouting", None)
        if routing is not None:
            routing.settle_layout()

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
            # A view may be the sole owner of a living Editor or contributed
            # surface. Closing the view must move that instance to a survivor
            # before its bindings and Qt tree disappear. The transfer also
            # flushes window-private editors while their bindings still live.
            self.projectLifecycleView.flush_pending_edits()
            if (
                not self.windowRegistry.quitting
                and not self.workspaceRetirement.preserve_unique_surfaces()
            ):
                event.ignore()
                return
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
        dock = instance.container
        if (
            dock is not None
            and dock not in self._defaultPeerVisibilitySlots
        ):
            panel_id = instance.descriptor.id

            def place_default_peer(visible, owned_id=panel_id):
                self._placePendingDefaultTab(owned_id, visible)
                self._placePendingTabsForPeer(owned_id, visible)

            dock.visibilityChanged.connect(place_default_peer)
            self._defaultPeerVisibilitySlots[dock] = place_default_peer
        routing = getattr(self, "surfacePanelRouting", None)
        if routing is not None:
            routing.panel_opened(instance.descriptor.id)

    def _offerSurfaceToggle(self, instance, dock):
        """Expose a mounted writing surface without changing its owner."""
        self.toolbar.addPanelToggle(
            dock.toggleViewAction(),
            instance.widget,
            None,
            panel_id=instance.id,
        )
        placement = getattr(self, "panelPlacement", None)
        if placement is not None:
            placement.watch_dock(dock)

    def _removeSurfaceToggle(self, instance, _dock):
        """Remove this window's control when a surface moves elsewhere."""
        self.toolbar.removePanelToggle(instance.id)

    def _placePendingDefaultTab(self, panel_id, visible):
        """Consume one first-open tab relationship on first reveal."""
        if not visible:
            return False
        peer_id = self._pendingDefaultTabPeers.get(panel_id)
        instance = self.panelHost.instance(panel_id)
        peer = self.panelHost.instance(peer_id) if peer_id else None
        dock = instance.container if instance is not None else None
        peer_dock = peer.container if peer is not None else None
        if (
            dock is None
            or peer_dock is None
            or dock.isFloating()
            or peer_dock.isFloating()
        ):
            return False
        if not peer_dock.isVisible():
            area = self.dockWidgetArea(peer_dock)
            if area != Qt.NoDockWidgetArea:
                self.addDockWidget(area, dock)
            return False
        self.tabifyDockWidget(peer_dock, dock)
        dock.raise_()
        self._pendingDefaultTabPeers.pop(panel_id, None)
        return True

    def _placePendingTabsForPeer(self, peer_id, visible):
        """Finish companion tabs when their previously hidden peer appears."""
        if not visible:
            return False
        placed = False
        for panel_id, expected_peer in tuple(
            self._pendingDefaultTabPeers.items()
        ):
            if expected_peer != peer_id:
                continue
            instance = self.panelHost.instance(panel_id)
            dock = instance.container if instance is not None else None
            if dock is not None and dock.isVisible():
                placed = self._placePendingDefaultTab(
                    panel_id, True,
                ) or placed
        return placed

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
        """Show the non-surface developer container."""
        if self.centralWidget() is None:
            self.setCentralWidget(self._centralSurface)
        self.stack.show()
        self.stack.setCurrentIndex(1)

    def _hideCentralPages(self):
        """Give the whole frame back to independently docked surfaces."""
        self.stack.hide()
        if self.centralWidget() is self._centralSurface:
            self.takeCentralWidget()

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
        self._hideCentralPages()
        return self.surfaceHost.activate(surface_id) is not None

    def activatePanel(self, panel_id):
        """Go to a surface, or reveal a tool panel, by stable identity."""
        if not panel_id:
            return False
        surface_activated = self.goToSurface(panel_id)
        if not surface_activated and not self.panelHost.reveal(panel_id):
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
        routing = getattr(self, "surfacePanelRouting", None)
        if surface_activated and routing is not None:
            routing.surface_changed(panel_id)
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
            tooltip = label
            if target.opens_panel and len(held) > 1:
                tooltip = self.tr(
                    "{}\nDrag this row to move the surface to a new "
                    "workspace window."
                ).format(label)
            item.setToolTip(tooltip)
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
        """Build the upstream-shaped first-open frame out of real docks.

        Upstream opens on General with a 200-pixel navigator and no project
        tree beside it.  The hidden surfaces still receive deterministic,
        independent places. Revealing Editor or Outline therefore adds a
        dock instead of replacing General in a central page stack.
        """

        def dock(panel_id):
            instance = self.panelHost.instance(panel_id)
            if instance is None:
                instance = self.surfaceHost.instance(panel_id)
            return instance.container if instance is not None else None

        project_tree = dock(core_panels.PROJECT_TREE)
        general = dock(core_panels.GENERAL)
        editor = dock(core_panels.EDITOR)
        if any(
            candidate is None
            for candidate in (project_tree, general, editor)
        ):
            return

        # Remove every core container from whatever partial/central-era
        # arrangement Qt restored. The widgets remain alive and are added
        # back below; plugin panels are deliberately not part of this method.
        core_docks = [self.dckNavigation]
        core_docks.extend(
            instance.container
            for instance in self.panelHost.instances.values()
            if instance.descriptor.id in core_panels.CORE_TOOL_PANEL_IDS
            and instance.container is not None
        )
        core_docks.extend(
            instance.container
            for instance in self.surfaceHost.instances.values()
            if instance.container is not None
        )
        for candidate in core_docks:
            if candidate.isFloating():
                candidate.setFloating(False)
            self.removeDockWidget(candidate)

        self.addDockWidget(Qt.LeftDockWidgetArea, self.dckNavigation)
        self.addDockWidget(Qt.LeftDockWidgetArea, project_tree)
        self.splitDockWidget(
            self.dckNavigation, project_tree, Qt.Horizontal
        )

        # The large writing surfaces share the main work area as native dock
        # tabs. They remain independently detachable QDockWidgets, but one
        # never squeezes the others into unusable slivers merely because the
        # navigator revealed it. This was the working pre-regression layout;
        # the central-page cutover copied only its single-visible appearance
        # and discarded the independent containers behind it.
        self.addDockWidget(Qt.RightDockWidgetArea, general)
        self.addDockWidget(Qt.RightDockWidgetArea, editor)
        self.tabifyDockWidget(editor, general)

        # Every destination is designed for the generous work area first.
        # The entity browsers were previously split into four 153-pixel-high
        # slivers under Project Tree; merely navigating through them left the
        # column behind and permanently squeezed Outline. Native dock tabs
        # preserve independent containers and tear-off while giving each
        # surface the same usable default canvas.
        for panel_id in (
            core_panels.PROJECT_ENTITIES,
            core_panels.CHARACTER_ENTITIES,
            core_panels.PLOT_ENTITIES,
            core_panels.WORLD_ENTITIES,
            core_panels.OUTLINE,
        ):
            surface = dock(panel_id)
            if surface is not None:
                self.tabifyDockWidget(editor, surface)

        # Tool companions share the project-tree slot as native dock tabs.
        # They can still be pulled out or placed elsewhere, while their first
        # reveal does not become a full-width strip with no neighbour.
        for panel_id in (core_panels.STORYLINE, core_panels.METADATA):
            companion = dock(panel_id)
            if companion is not None:
                self.tabifyDockWidget(project_tree, companion)
        self._pendingDefaultTabPeers = {
            core_panels.METADATA: core_panels.PROJECT_TREE,
            core_panels.STORYLINE: core_panels.PROJECT_TREE,
        }

        # Moving hidden docks exposes them in Qt. Reassert the canonical
        # first-open visibility after the whole structure exists.
        for instance in self.surfaceHost.instances.values():
            instance.container.setVisible(
                bool(instance.descriptor.default_visible)
            )
        for panel_id in (
            core_panels.PROJECT_TREE,
            core_panels.METADATA,
            core_panels.STORYLINE,
        ):
            instance = self.panelHost.instance(panel_id)
            routed = instance.descriptor.visible_with_surfaces
            visible = (
                core_panels.GENERAL in routed
                if routed is not None
                else bool(instance.descriptor.default_visible)
            )
            self.panelHost.set_visible(
                panel_id, visible,
            )

        self.dckCheatSheet.hide()
        self.dckSearch.hide()
        self.dckNavigation.show()
        general.show()
        general.raise_()
        self._defaultDockLayoutPending = True
        if self.isVisible():
            # Hiding a routed neighbour changes QMainWindow's native dock
            # grid on the next event turn. Resizing synchronously here is
            # immediately overwritten by that relayout, which is how Reset
            # Layout returned a 302px navigator despite requesting 200px.
            QTimer.singleShot(0, self._settleDefaultCoreDocks)

    def _applyBuildIntentPresentation(self):
        """Keep a transfer wrapper about the surface it was built for.

        A peer ``MainWindow`` supplies real window-manager behaviour and a
        dock host, but that does not make every piece of the ordinary
        Manuskript shell part of the transfer.  The navigator and routed core
        tools remain available to composition; they simply do not appear as
        accidental passengers beside a detached surface.
        """

        if not self._standaloneSurfacePresentation:
            return
        self.dckNavigation.hide()
        self.dckCheatSheet.hide()
        self.dckSearch.hide()
        for panel_id in core_panels.CORE_TOOL_PANEL_IDS:
            if self.panelHost.instance(panel_id) is not None:
                self.panelHost.set_visible(panel_id, False)
        for instance in self.surfaceHost.instances.values():
            dock = instance.container
            dock.setFeatures(
                dock.features() & ~QDockWidget.DockWidgetClosable
            )

    def _workspaceSurfaceMembershipChanged(self):
        """Keep navigator chrome aligned with workspace composition."""

        if (
            self._standaloneSurfacePresentation
            and len(self.surfaceHost.instances) > 1
        ):
            # A one-surface wrapper has become a real multi-surface
            # workspace. It now needs ordinary navigation and routing; this
            # is an explicit membership transition, not a navigation side
            # effect.
            self._standaloneSurfacePresentation = False
            self.dckNavigation.show()
            for instance in self.surfaceHost.instances.values():
                dock = instance.container
                dock.setFeatures(
                    dock.features() | QDockWidget.DockWidgetClosable
                )
            routing = getattr(self, "surfacePanelRouting", None)
            if routing is not None:
                routing.reset()
                routing.surface_changed(self.surfaceHost.current())
        self.rebuildNavigator()

    def _settleDefaultCoreDocks(self):
        """Apply pixel extents after the native window has real geometry."""
        # The first showEvent belongs to the welcome screen. Reasserting the
        # default surface visibility there paints General over the open/create
        # invitation and makes Manuskript look as though it started in a
        # broken project. Keep the pending work until a project owns the
        # frame; switchToProject schedules this method again.
        if not self._projectSurfaceActive:
            return
        general = self.surfaceHost.instance(core_panels.GENERAL)
        general_dock = general.container if general is not None else None
        if general_dock is None:
            return
        # Native tab groups may select one member on the event turn after
        # they are rebuilt, even when composition hid every member. Reassert
        # the canonical visibility at the same deferred boundary used for
        # sizing so Reset from an already-General workspace cannot revive
        # Project Tree merely because Metadata and Story line share its slot.
        for instance in self.surfaceHost.instances.values():
            instance.container.setVisible(
                bool(instance.descriptor.default_visible)
            )
        for panel_id in core_panels.CORE_TOOL_PANEL_IDS:
            instance = self.panelHost.instance(panel_id)
            if instance is not None:
                routed = instance.descriptor.visible_with_surfaces
                visible = (
                    core_panels.GENERAL in routed
                    if routed is not None
                    else bool(instance.descriptor.default_visible)
                )
                self.panelHost.set_visible(
                    panel_id, visible,
                )
        general_dock.show()
        general_dock.raise_()
        self.resizeDocks(
            (self.dckNavigation, general_dock),
            (200, max(1, self.width() - 200)),
            Qt.Horizontal,
        )
        self._defaultDockLayoutPending = False

    def _closeContributedWorkspaceUi(self):
        """Remove UI which is not part of the canonical core workspace."""
        if self.pluginUi is not None:
            self.pluginUi.projectPanels.close_all()
            self.pluginUi.editorWorkspaces.close_workspace()
        for panel_id in tuple(self.panelHost.instances):
            if panel_id not in core_panels.CORE_PANEL_IDS:
                self.panelHost.close(panel_id)
                self.toolbar.removePanelToggle(panel_id)
        for surface_id in tuple(self.surfaceHost.instances):
            if surface_id not in core_panels.CORE_SURFACE_IDS:
                self.surfaceHost.close(surface_id)

    def _resetLocalWorkspaceLayout(self):
        """Rebuild this complete workspace's canonical dock presentation."""
        self._placeDefaultCoreDocks()
        self._activePanelId = core_panels.GENERAL
        routing = getattr(self, "surfacePanelRouting", None)
        if routing is not None:
            routing.reset()
        self.activatePanel(core_panels.GENERAL)
        self.windowState.forget_captured_layout()
        self.windowState.capture_layout()
        placement = getattr(self, "panelPlacement", None)
        if placement is not None:
            placement.refresh_docks()

    def resetWorkspaceLayout(self, _checked=False):
        """Restore the one first-open application workspace explicitly."""
        return self.workspaceLayoutReset.reset(_checked)

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
        self.actResetWorkspaceLayout = QAction(
            self.tr("&Reset Workspace Layout"), self
        )
        self.actResetWorkspaceLayout.setObjectName(
            "actResetWorkspaceLayout"
        )
        self.actResetWorkspaceLayout.setStatusTip(self.tr(
            "Close contributed UI, reunite core surfaces in the main "
            "workspace, and restore the first-open layout"
        ))
        self.actResetWorkspaceLayout.triggered.connect(
            self.resetWorkspaceLayout
        )
        self.menuView.insertAction(anchor, self.actResetWorkspaceLayout)
        self.menuView.insertSeparator(anchor)
        self.surfaceTransfer = self.workspaceLifetime.own(
            SurfaceTransferController(
                SurfaceTransferViews.for_window(self, anchor=anchor)
            )
        )
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
        self.surfacePresentation.on_mounted = self._offerSurfaceToggle
        self.surfacePresentation.on_unmounted = self._removeSurfaceToggle
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
        for surface_id in self.buildIntent.surface_ids:
            self.surfaceHost.open(surface_id, context)
        for instance in self.buildIntent.incoming:
            self.surfaceHost.attach(instance)
        if not self.surfaceHost.instances:
            raise WorkspaceSurfaceError(
                "A visible workspace must contain at least one surface."
            )
        # Said here rather than left to whichever surface was opened first.
        # Which surface a fresh workspace starts on is composition's to
        # state, and upstream's answer -- the one a new reader gets -- is
        # General. A saved layout replaces this when there is one.
        active_surface = self.buildIntent.active_surface
        if not self.surfaceHost.contains(active_surface):
            active_surface = next(iter(self.surfaceHost.instances))
        self.surfaceHost.activate(active_surface)
        self._activePanelId = active_surface

        self.corePanels = CorePanelViewSet.from_hosts(
            tools=self.panelHost, surfaces=self.surfaceHost,
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
        self.lstTabs.setIconSize(QSize(48, 48))
        self.rebuildNavigator()
        # Rebuilt again whenever this workspace gains or loses one, which
        # is how a row leaves with the surface it stood for.
        self.surfaceHost.on_membership_changed = (
            self._workspaceSurfaceMembershipChanged
        )
        self.tabMain.tabBar().hide()
        self.lstTabs.currentRowChanged.connect(self.navigateTo)
        self.tabMain.setTabEnabled(self.DebugPage, self.SHOW_DEBUG_TAB)
        self.tabMain.currentChanged.connect(self._selectNavigatorPage)

        # Help box
        help_text = {
            core_panels.GENERAL: self.tr(
                "Enter information about your book, and yourself."
            ),
            core_panels.OUTLINE: self.tr(
                "Create the outline of your masterpiece."
            ),
            core_panels.EDITOR: self.tr("Write."),
        }
        references = [
            (instance.widget, help_text[instance.id], 0)
            for instance in self.surfaceHost.instances.values()
            if instance.id in help_text
        ] + [(
            self.lytTabDebug,
            self.tr("Debug info. Sometimes useful."),
            0,
        )]

        for widget, text, pos in references:
            label = helpLabel(text, self)
            self.actShowHelp.toggled.connect(label.setVisible, F.AUC)
            widget.layout().insertWidget(pos, label)

        self.actShowHelp.setChecked(False)

    @property
    def mainEditor(self):
        """Compatibility view of an Editor this workspace already owns."""

        instance = self.surfaceHost.instance(core_panels.EDITOR)
        if instance is None:
            raise AttributeError("This workspace does not contain an Editor.")
        return instance.widget.editor

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
