"""Workspace-scoped tool dialog composition and lifecycle.

Dialog classes need concrete services, while their lifecycle only needs to
create, present, replace, and close windows.  Factories keep those concerns
separate: only this composition adapter knows where a workspace stores the
services, and the controller receives no unrestricted ``MainWindow`` object.
"""

from dataclasses import dataclass
from typing import Any, Callable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget

from manuskript.settingsWindow import settingsWindow
from manuskript.ui.about import aboutDialog
from manuskript.ui.dialog_lifecycle import NamedDialogLifecycle
from manuskript.ui.git_revision_dialog import GitRevisionDialog
from manuskript.ui.settings_window_views import SettingsWindowViews
from manuskript.ui.tools.frequencyAnalyzer import frequencyAnalyzer
from manuskript.ui.tools.media_type_inspector import MediaTypeInspector
from manuskript.ui.tools.targets import TargetsContext, TargetsDialog
from manuskript.ui.project_upgrade_dialog import ProjectUpgradeDialog
from manuskript.services.project_migration import ProjectMigrationService


@dataclass(frozen=True)
class AuthoringDialogFactories:
    """Factories for tools that operate on the active manuscript."""

    settings: Callable[[], Any]
    frequency: Callable[[], Any]
    targets: Callable[[], Any]
    revisions: Callable[[Any], Any]
    upgrade: Callable[[], Any]
    project_is_open: Callable[[], bool]


@dataclass(frozen=True)
class ApplicationDialogFactories:
    """Factories for application-level inspection and information."""

    media_types: Callable[[], Any]
    about: Callable[[], Any]


@dataclass(frozen=True)
class WorkspaceDialogViews:
    """Presentation capabilities and dialog factories for one workspace."""

    dialog_parent: Any
    center: Callable[[Any], None]
    authoring: AuthoringDialogFactories
    application: ApplicationDialogFactories

    @classmethod
    def for_window(cls, window):
        runtime = window.projectRuntime
        settings = runtime.settingsManager
        manager = window.projectManager
        # Project surfaces are docks and the welcome central widget is
        # detached during authoring.  Keep dialogs owned by the workspace
        # window so modality and teardown do not depend on that hidden view.
        dialog_parent = window

        def create_settings():
            return settingsWindow(
                SettingsWindowViews.for_window(
                    window,
                    parent=dialog_parent,
                ),
                settings,
                theme_repository=window.themeRepository,
                theme_preview_renderer=window.themePreviewRenderer,
                application_preferences=window.applicationPreferences,
                card_styles=window.cardStyles,
            )

        return cls(
            dialog_parent=dialog_parent,
            center=window.windowPlacement.center,
            authoring=AuthoringDialogFactories(
                settings=create_settings,
                frequency=lambda: frequencyAnalyzer(
                    runtime.models.outline,
                    settings,
                    parent=dialog_parent,
                ),
                targets=lambda: TargetsDialog(
                    TargetsContext.for_runtime(
                        runtime,
                        window.writingSession,
                    ),
                    parent=dialog_parent,
                ),
                revisions=lambda parent: GitRevisionDialog(
                    manager,
                    settings,
                    runtime.revisionCoordinator,
                    parent,
                ),
                upgrade=lambda: ProjectUpgradeDialog(
                    manager,
                    ProjectMigrationService(),
                    parent=dialog_parent,
                ),
                project_is_open=lambda: manager.session.is_open,
            ),
            application=ApplicationDialogFactories(
                media_types=lambda: MediaTypeInspector(
                    window.mediaTypes,
                    window.mediaTypePreferences,
                    parent=dialog_parent,
                ),
                about=lambda: aboutDialog(parent=dialog_parent),
            ),
        )


class WorkspaceDialogController:
    """Own and present the tool dialogs opened by one workspace."""

    SETTINGS = "settings"
    FREQUENCY = "frequency"
    TARGETS = "targets"
    REVISIONS = "revisions"
    UPGRADE = "upgrade"
    MEDIA_TYPES = "media-types"
    ABOUT = "about"

    def __init__(self, views):
        self.views = views
        self._lifecycle = NamedDialogLifecycle(views.center)

    @property
    def settings_dialog(self):
        return self._lifecycle.current(self.SETTINGS)

    @property
    def frequency_dialog(self):
        return self._lifecycle.current(self.FREQUENCY)

    @property
    def targets_dialog(self):
        return self._lifecycle.current(self.TARGETS)

    @property
    def revision_dialog(self):
        return self._lifecycle.current(self.REVISIONS)

    @property
    def media_type_dialog(self):
        return self._lifecycle.current(self.MEDIA_TYPES)

    @property
    def about_dialog(self):
        return self._lifecycle.current(self.ABOUT)

    def show_settings(self, tab=None, _checked=False):
        # QAction.triggered supplies its checked state positionally.  It is
        # not a settings-page index.
        if isinstance(tab, bool):
            tab = None
        dialog = self._lifecycle.replace(
            self.SETTINGS,
            self.views.authoring.settings,
        )
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.setWindowFlags(Qt.Dialog)
        if tab is not None:
            dialog.setTab(tab)
        return self._lifecycle.present(dialog)

    def show_labels(self, _checked=False):
        return self.show_settings(3)

    def show_statuses(self, _checked=False):
        return self.show_settings(4)

    def show_frequency(self, _checked=False):
        return self._lifecycle.present(self._lifecycle.replace(
            self.FREQUENCY,
            self.views.authoring.frequency,
        ))

    def show_targets(self, _checked=False):
        return self._lifecycle.present(self._lifecycle.replace(
            self.TARGETS,
            self.views.authoring.targets,
        ))

    def show_revision_history(self, parent=None, _checked=False):
        if not self.views.authoring.project_is_open():
            return None
        host = (
            parent
            if isinstance(parent, QWidget)
            else self.views.dialog_parent
        )
        dialog = self.revision_dialog
        if dialog is None:
            dialog = self.views.authoring.revisions(host)
            self._lifecycle.register(self.REVISIONS, dialog)
        elif dialog.parentWidget() is not host:
            # A child of application-modal Settings stays interactive;
            # a sibling top-level dialog would be blocked by it.
            dialog.hide()
            dialog.setParent(host, Qt.Dialog)
        return self._lifecycle.present(dialog, center=False)

    def show_upgrade(self, _checked=False):
        if not self.views.authoring.project_is_open():
            return None
        return self._lifecycle.present(self._lifecycle.replace(
            self.UPGRADE,
            self.views.authoring.upgrade,
        ))

    def show_media_types(self, _checked=False):
        return self._lifecycle.present(self._lifecycle.replace(
            self.MEDIA_TYPES,
            self.views.application.media_types,
        ))

    def show_about(self, _checked=False):
        dialog = self._lifecycle.replace(
            self.ABOUT,
            self.views.application.about,
        )
        dialog.setFixedSize(dialog.size())
        return self._lifecycle.present(dialog)

    def close_all(self):
        self._lifecycle.close_all()

    def dispose(self):
        self._lifecycle.dispose()
        self.views = None
