"""Reusable ownership for named, non-modal workspace dialogs."""

from functools import partial

from PyQt5.QtCore import Qt


class NamedDialogLifecycle:
    """Own dialogs by role and retire stale instances safely.

    Qt may deliver an old dialog's ``destroyed`` signal after its replacement
    has already been registered.  Per-registration tokens make that delayed
    signal harmless instead of letting it forget the new dialog.
    """

    def __init__(self, center):
        self._center = center
        self._dialogs = {}
        self._tokens = {}

    def current(self, name):
        return self._dialogs.get(name)

    def replace(self, name, factory):
        previous = self._dialogs.pop(name, None)
        self._tokens.pop(name, None)
        if previous is not None:
            previous.close()
        dialog = factory()
        self.register(name, dialog)
        return dialog

    def register(self, name, dialog):
        token = object()
        self._dialogs[name] = dialog
        self._tokens[name] = token
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.destroyed.connect(partial(self._discard, name, token))
        return dialog

    def present(self, dialog, center=True):
        if center:
            self._center(dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def close_all(self):
        dialogs = tuple(self._dialogs.values())
        self._dialogs.clear()
        self._tokens.clear()
        for dialog in dialogs:
            dialog.close()

    def dispose(self):
        self.close_all()
        self._center = None

    def _discard(self, name, token, _object=None):
        if self._tokens.get(name) is not token:
            return
        self._tokens.pop(name, None)
        self._dialogs.pop(name, None)
