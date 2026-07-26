from manuskript.services.window_state import (
    ApplicationWindowState,
    ApplicationWindowStateStore,
)


class MainWindowStateController:
    """Own restoration and capture of application-scoped window state."""

    def __init__(self, window, store=None):
        self.window = window
        self.store = (
            store if store is not None else ApplicationWindowStateStore()
        )
        self._dock_visibility = {}
        self._dock_visibility_locked = True
        self._toolbar_state = None

    @property
    def project_docks(self):
        return (
            self.window.dckNavigation,
            self.window.dckCheatSheet,
            self.window.dckSearch,
        )

    def restore(self):
        state = self.store.load()
        window = self.window
        if state.geometry is not None:
            window.restoreGeometry(state.geometry)
        if state.window_state is not None:
            window.restoreState(state.window_state)

        if state.docks is None:
            self._dock_visibility = {
                window.dckNavigation.objectName(): True,
                window.dckCheatSheet.objectName(): False,
                window.dckSearch.objectName(): False,
            }
        else:
            self._dock_visibility = dict(state.docks)
        self._dock_visibility_locked = True

        if state.metadata is not None:
            window.redacMetadata.restoreState(
                self._bool_state(state.metadata)
            )
        if state.revisions is not None:
            window.redacMetadata.revisions.restoreState(
                self._bool_state(state.revisions)
            )
        if state.redaction_horizontal is not None:
            window.splitterRedacH.restoreState(
                state.redaction_horizontal
            )
        if state.redaction_vertical is not None:
            window.splitterRedacV.restoreState(
                state.redaction_vertical
            )
        self._toolbar_state = state.toolbar

    def restore_toolbar(self, toolbar):
        if self._toolbar_state is not None:
            toolbar.restoreState(self._toolbar_state)

    def hide_project_docks(self):
        if not self._dock_visibility_locked:
            self._remember_project_docks()
        for dock in self.project_docks:
            dock.setVisible(False)
        self._dock_visibility_locked = False

    def restore_project_docks(self):
        for dock in self.project_docks:
            dock.setVisible(
                self._dock_visibility.get(dock.objectName(), False)
            )
        self._dock_visibility_locked = False

    def save(self):
        window = self.window
        if window.stack.currentIndex() == 1:
            self._remember_project_docks()

        self.store.save(
            ApplicationWindowState(
                geometry=window.saveGeometry(),
                window_state=window.saveState(),
                docks=dict(self._dock_visibility),
                metadata=window.redacMetadata.saveState(),
                revisions=window.redacMetadata.revisions.saveState(),
                redaction_horizontal=window.splitterRedacH.saveState(),
                redaction_vertical=window.splitterRedacV.saveState(),
                toolbar=window.toolbar.saveState(),
            )
        )

    def _remember_project_docks(self):
        for dock in self.project_docks:
            self._dock_visibility[dock.objectName()] = dock.isVisible()

    @staticmethod
    def _bool_state(values):
        def as_bool(value):
            if isinstance(value, str):
                return value.lower() not in ("", "0", "false")
            return bool(value)

        return [as_bool(value) for value in values]
