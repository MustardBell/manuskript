"""Workspace-scoped import/export composition and dialog ownership."""

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

from PyQt5.Qt import PYQT_VERSION_STR, qVersion
from PyQt5.QtCore import QModelIndex, Qt
from PyQt5.QtWidgets import QMessageBox

from manuskript.exporter.context import ExportContextProvider
from manuskript.plugins.conversion_augmentations import augmentations_for
from manuskript.ui.dialog_lifecycle import NamedDialogLifecycle
from manuskript.ui.exporters.exporter import exporterDialog
from manuskript.ui.importers.import_context import ImportContextProvider
from manuskript.ui.importers.importer import importerDialog


LOGGER = logging.getLogger(__name__)
UNSAFE_IMPORT_QT = re.compile(r"^5\.1[12](\.?|$)")


def installed_pyqt_version():
    return PYQT_VERSION_STR


@dataclass(frozen=True)
class WorkspaceTransferViews:
    """Capabilities used to create and present one workspace's transfers."""

    center: Callable[[Any], None]
    translate: Callable[[str], str]
    create_import: Callable[[], Any]
    create_export: Callable[[], Any]
    export_context: Callable[[], Any]
    confirm_unsafe_import: Callable[[str, str, str], bool]
    qt_version: Callable[[], str] = qVersion
    pyqt_version: Callable[[], str] = installed_pyqt_version

    @classmethod
    def for_window(cls, window):
        runtime = window.projectRuntime
        # The central welcome widget is not present while a project is open.
        # Import/export dialogs belong to the workspace for their lifetime.
        dialog_parent = window
        project_tree = window.corePanels.optional_tool("project_tree")
        tree = project_tree.tree if project_tree is not None else None

        def current_outline_index():
            return (
                tree.currentIndex()
                if tree is not None and tree.selectedIndexes()
                else QModelIndex()
            )

        def conversion_augmentations(request):
            registry = (
                window.pluginRuntime.registry
                if window.pluginRuntime is not None
                else None
            )
            return augmentations_for(
                registry,
                request,
                report_error=lambda message: window.statusPresenter.show(
                    message, 8000, 2,
                ),
            )

        import_contexts = ImportContextProvider(
            models=lambda: runtime.models,
            settings=runtime.settingsManager,
            current_outline_index=current_outline_index,
            show_status=window.statusPresenter.show,
        )
        export_contexts = ExportContextProvider(
            project_file=lambda: runtime.currentProject,
            models=lambda: runtime.models,
            parent=dialog_parent,
            tool_paths=window.externalToolPaths,
            process_runner=window.externalProcessRunner,
            page_types=lambda: (
                getattr(window, "pluginUi", None).pageTypes
                if getattr(window, "pluginUi", None) is not None
                else None
            ),
            conversion_augmentations=conversion_augmentations,
        )

        def create_import():
            return importerDialog(
                import_contexts.create(),
                parent=dialog_parent,
                plugin_runtime=window.pluginRuntime,
                plugin_option_store=window.pluginOptionStore,
            )

        def create_export():
            return exporterDialog(
                export_contexts.create(),
                parent=dialog_parent,
                preferences=window.applicationPreferences,
                plugin_runtime=window.pluginRuntime,
                plugin_option_store=window.pluginOptionStore,
            )

        def confirm_unsafe_import(title, warning, version_warning):
            message = QMessageBox(
                QMessageBox.Warning,
                title,
                "<p><b>{}</b></p><p>{}</p>".format(
                    warning,
                    version_warning,
                ),
                QMessageBox.Abort | QMessageBox.Ignore,
                dialog_parent,
            )
            message.setDefaultButton(QMessageBox.Abort)
            return message.exec() != QMessageBox.Abort

        return cls(
            center=window.windowPlacement.center,
            translate=window.tr,
            create_import=create_import,
            create_export=create_export,
            export_context=export_contexts.create,
            confirm_unsafe_import=confirm_unsafe_import,
        )


class WorkspaceTransferController:
    """Own import and export independently for one workspace."""

    IMPORT = "import"
    EXPORT = "export"

    def __init__(self, views):
        self.views = views
        self._lifecycle = NamedDialogLifecycle(views.center)

    @property
    def import_dialog(self):
        return self._lifecycle.current(self.IMPORT)

    @property
    def export_dialog(self):
        return self._lifecycle.current(self.EXPORT)

    def export_context(self):
        return self.views.export_context()

    def show_import(self, _checked=False):
        qt_version = self.views.qt_version()
        if UNSAFE_IMPORT_QT.match(qt_version):
            warning = self.views.translate(
                "PyQt / Qt versions 5.11 and 5.12 are known to cause a "
                "crash which might result in a loss of data."
            )
            version_warning = self.views.translate(
                "PyQt {} and Qt {} are in use."
            ).format(qt_version, self.views.pyqt_version())
            LOGGER.warning(warning)
            LOGGER.warning(version_warning)
            if not self.views.confirm_unsafe_import(
                self.views.translate("Proceed with import at your own risk"),
                warning,
                version_warning,
            ):
                return None
        dialog = self._lifecycle.replace(
            self.IMPORT,
            self.views.create_import,
        )
        # Keep workspace ownership without embedding the dialog as an
        # ordinary child widget in the central editor area.
        dialog.setWindowFlags(Qt.Dialog)
        return self._lifecycle.present(dialog)

    def show_export(self, _checked=False):
        dialog = self._lifecycle.replace(
            self.EXPORT,
            self.views.create_export,
        )
        dialog.setWindowFlags(Qt.Dialog)
        return self._lifecycle.present(dialog)

    def close_all(self):
        self._lifecycle.close_all()

    def dispose(self):
        self._lifecycle.dispose()
        self.views = None
