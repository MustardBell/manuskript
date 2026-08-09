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
        self._callbacks = {}

    def current(self, name):
        return self._dialogs.get(name)

    def replace(self, name, factory):
        previous = self._dialogs.pop(name, None)
        self._tokens.pop(name, None)
        callback = self._callbacks.pop(name, None)
        if previous is not None:
            if callback is not None:
                try:
                    previous.destroyed.disconnect(callback)
                except (RuntimeError, TypeError):
                    pass
            previous.close()
        dialog = factory()
        self.register(name, dialog)
        return dialog

    def register(self, name, dialog):
        token = object()
        callback = partial(self._discard, name, token)
        self._dialogs[name] = dialog
        self._tokens[name] = token
        self._callbacks[name] = callback
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.destroyed.connect(callback)
        return dialog

    def present(self, dialog, center=True):
        if center:
            self._center(dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def close_all(self):
        dialogs = tuple(
            (name, dialog, self._callbacks.get(name))
            for name, dialog in self._dialogs.items()
        )
        self._dialogs.clear()
        self._tokens.clear()
        self._callbacks.clear()
        for _name, dialog, callback in dialogs:
            if callback is not None:
                try:
                    dialog.destroyed.disconnect(callback)
                except (RuntimeError, TypeError):
                    pass
            dialog.close()

    def dispose(self):
        self.close_all()
        self._center = None

    def _discard(self, name, token, _object=None):
        tokens = getattr(self, "_tokens", None)
        if tokens is None or tokens.get(name) is not token:
            return
        tokens.pop(name, None)
        self._dialogs.pop(name, None)
        self._callbacks.pop(name, None)
