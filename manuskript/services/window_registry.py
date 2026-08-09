"""Which windows are workspaces, and what closing one of them means.

Closing used to mean closing everything: the window walked every
top-level widget and shut it, because there was only ever one real
window and everything else was a dialog of it. With several workspace
windows that is wrong twice over -- it would take the other workspaces
down, and it decided "auxiliary" by elimination rather than by anything
a window actually declared.

Only workspace windows register here. Tool windows, floating panels and
dialogs never do, and that absence is exactly how the last workspace
window is recognised: closing it closes the project, closing any other
does not.
"""

import logging


LOGGER = logging.getLogger(__name__)


class WindowRegistry:
    """The application's workspace windows, in the order they opened."""

    def __init__(self, focus_source=None):
        """``focus_source`` is whatever publishes focus changes.

        Injected rather than reached for so that watching focus can be
        exercised without standing in for the running application: a
        test that replaces ``qApp`` leaves the real one unconnected and
        every later binding wrong.
        """
        self._windows = []
        self._focus_handlers = {}
        self._active = None
        self._focus_source = focus_source
        self._watching_focus = False
        #: True while close_all is working through the windows, so the
        #: last one to go does not record a session of just itself.
        self.quitting = False

    def register(self, window, focus_handler=None):
        if window not in self._windows:
            self._windows.append(window)
        if focus_handler is not None:
            self._focus_handlers[window] = focus_handler
        if self._active is None:
            self._active = window
        return window

    def unregister(self, window):
        if window in self._windows:
            self._windows.remove(window)
        self._focus_handlers.pop(window, None)
        if self._active is window:
            self._active = self._windows[0] if self._windows else None

    @property
    def workspace_windows(self):
        return tuple(self._windows)

    def is_last(self, window):
        """Whether this window is the only workspace left.

        A window that never registered answers True: it is not part of a
        set, so closing it is the whole of whatever it belongs to.
        """
        if window not in self._windows:
            return True
        return len(self._windows) == 1

    @property
    def active(self):
        """The workspace window commands are routed to."""
        return self._active

    def get_active(self):
        """Return the active workspace when a callable port is required."""
        return self._active

    def activate(self, window):
        if window in self._windows:
            self._active = window

    def watch_focus(self):
        """Follow application-wide focus, once for the application.

        Idempotent, because every window asks: connecting per window
        would have each of them react to every other window's focus
        changes.
        """
        if self._watching_focus:
            return
        source = self._focus_source
        if source is None:
            from PyQt5.QtWidgets import qApp

            source = qApp
        source.focusChanged.connect(self.focus_changed)
        self._watching_focus = True

    def focus_changed(self, old, new):
        """Route a focus change to the workspace window that gained it."""
        if new is None:
            return
        window = new.window() if hasattr(new, "window") else None
        if window not in self._windows:
            return
        self._active = window
        forward = self._focus_handlers.get(window)
        if forward is not None:
            forward(old, new)

    def close_all(self):
        """Quit: settle the project first, then close every workspace.

        Two phases, and the order is the whole point. Asking about unsaved
        changes used to fall to whichever window turned out to be the last
        one standing -- so by the time the person saw the prompt the other
        windows had already gone, and pressing Cancel left them shut with
        the application still running. Cancelling a quit has to leave
        everything exactly as it was.

        So the question is asked once, up front, while every window is
        still open. Only once it is settled does anything close, and the
        closes that follow do not ask again.
        """
        self.quitting = True
        try:
            windows = self.workspace_windows
            primary = windows[0] if windows else None
            if primary is not None and not self._settle(primary):
                return False
            for window in reversed(windows[1:]):
                if not self._close(window):
                    return False
            if primary is not None and not self._close(primary):
                return False
            return True
        finally:
            self.quitting = False

    @staticmethod
    def _settle(window):
        """Ask the project about unsaved changes, closing nothing.

        Through the window because the project is reached that way, not
        because it belongs to the window -- one project, so asking any
        one of its windows asks the project.
        """
        manager = getattr(window, "projectManager", None)
        settle = getattr(manager, "settleBeforeClosing", None)
        if settle is None:
            return True
        return bool(settle())

    @staticmethod
    def _close(window):
        """Close one window, reporting whether it agreed to go."""
        return bool(window.close())
