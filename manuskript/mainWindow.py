#!/usr/bin/env python
# --!-- coding: utf8 --!--
import importlib

from PyQt5.QtCore import (pyqtSignal, Qt,
                          QUrl, QSize)
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDockWidget,
    QLabel,
    QListWidgetItem,
    QMainWindow,
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
from manuskript.panels.core import register_core_panels
from manuskript.ui.panels import PanelHost
from manuskript.ui.panels.placement import (
    PanelPlacementController,
    PanelPlacementViews,
)
from manuskript.ui.panels.window_port import PanelWindow
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
from manuskript.ui.entity_workspace import (
    EntityWorkspaceController,
    panel_revealer,
)
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
from manuskript.ui.workspace_state_controller import (
    WorkspaceStateController,
    WorkspaceStateViews,
)
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
        if window_id != WORKSPACE_PRIMARY:
            # A secondary workspace has no application-lifetime owner.  If
            # close merely hides it, its large parented Qt tree is eventually
            # destroyed by Python's cyclic collector, which SIP cannot do
            # safely once C++-owned child wrappers are involved.
            self.setAttribute(Qt.WA_DeleteOnClose)
        self.setupUi(self)
        self.setDockOptions(
            QMainWindow.AnimatedDocks
            | QMainWindow.AllowNestedDocks
            | QMainWindow.AllowTabbedDocks
            | QMainWindow.GroupedDragging
        )
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
                self.corePanels.entity_editor,
                panel_revealer(self.panelHost, core_panels.ENTITY_EDITOR),
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
            restored_layout = self.windowState.restore()
            entity_panel_ids = self._entityPanelIds()
            if not any(
                panel_id in restored_layout.panels
                for panel_id in entity_panel_ids
            ):
                self._placeEntityDocks(entity_panel_ids)
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
            core_panels.ENTITY_EDITOR,
        )

    def _placeEntityDocks(self, panel_ids=None):
        """Give newly introduced entity docks a place of their own.

        Neighbours down the dock area, not tabs over one another. They
        answer different questions and get read together, so stacking
        them into a single frame put four of them behind a tab strip
        and made one dock out of five.

        This is only called when the saved layout predates entity
        panels. Once those panel identifiers have been recorded, Qt's
        restored arrangement is authoritative and this does nothing.
        """

        panel_ids = tuple(panel_ids or self._entityPanelIds())
        docks = []
        for panel_id in panel_ids:
            instance = self.panelHost.instance(panel_id)
            if instance is not None and instance.container is not None:
                docks.append(instance.container)
        if not docks:
            return
        previous = docks[0]
        for dock in docks[1:]:
            self.splitDockWidget(previous, dock, Qt.Vertical)
            previous = dock

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
            self.TabRedac,
            factories=core_panel_factories(),
        )
        for panel_id in (
            core_panels.PROJECT_TREE,
            core_panels.METADATA,
            core_panels.STORYLINE,
            core_panels.PROJECT_ENTITIES,
            core_panels.CHARACTER_ENTITIES,
            core_panels.PLOT_ENTITIES,
            core_panels.WORLD_ENTITIES,
            core_panels.ENTITY_EDITOR,
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
        for legacy_tab in (
            self.TabSummary,
            self.TabPersos,
            self.TabPlots,
            self.TabWorld,
        ):
            self.lstTabs.item(legacy_tab).setHidden(True)
            self.tabMain.setTabVisible(legacy_tab, False)
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
