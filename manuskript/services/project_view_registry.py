"""Every window viewing one project, behind one view-shaped object.

The project manager talks to a view. With several windows on one project
there is no single view, so this stands in for all of them and keeps the
shape the manager already expects.

Two kinds of call, and the difference is what makes this correct rather
than merely convenient:

* **Announcements** -- project opened, project closed, model bindings
  changing -- go to every window, because each has its own widgets to
  update.
* **Questions** -- save before closing? which project name? -- go to the
  primary view alone. Asking four windows whether to save would ask the
  person four times, and state shared by all of them would be captured
  four times over.

With one window registered this behaves exactly as that window did.

What is *not* here: anything the project owns. The settings, the parent
its models hang off and the models themselves were answerable here once,
which let the project manager reach its own facts through whichever
window happened to be first. Those now go from the runtime straight to
the manager, and this stays what its name says -- a way to talk to
windows.
"""


class ProjectViewRegistry:
    """The project's views, addressable as one."""

    def __init__(self, views=(), active_window_source=None):
        self._views = []
        self._workspaces = {}
        for view in views:
            self.register(view)
        # A callable, not a window registry: this is project scope and
        # has no business knowing the type of thing that tracks windows.
        # Absent one, the primary view answers, which is what a single
        # window has always meant.
        self._active_window_source = active_window_source

    def register(self, view, workspace=None):
        if view not in self._views:
            self._views.append(view)
        if workspace is not None:
            self._workspaces[view] = workspace
        return view

    def unregister(self, view):
        if view in self._views:
            self._views.remove(view)
        self._workspaces.pop(view, None)

    @property
    def views(self):
        return tuple(self._views)

    @property
    def primary(self):
        """The view that answers questions.

        The first registered -- the window the project was opened from --
        until it goes away and the next one inherits the role.
        """
        return self._views[0] if self._views else None

    @property
    def speaking(self):
        """The view that a remark about the project should appear in.

        Resolved per call, never captured. Whichever window the person
        is working in if that can be known, the primary otherwise -- a
        save started with Ctrl+S in the second window has no business
        reporting itself into the first one's status bar, and a bound
        method taken at attach time would report into a window that has
        since closed.
        """
        source = self._active_window_source
        window = source() if source is not None else None
        if window is not None:
            for view in self._views:
                if self._workspaces.get(view) is window:
                    return view
        return self.primary

    def show_status(self, message, duration=5000, importance=1):
        """Say something about the project where it is being worked on."""
        view = self.speaking
        if view is not None:
            view.show_status(message, duration, importance)

    # ------------------------------------------------- announcements

    def sync_to_state(self, project_open):
        for view in self.views:
            view.sync_to_state(project_open)

    def connect_project(self):
        for view in self.views:
            view.connect_project()

    def apply_loaded_settings(self):
        for view in self.views:
            view.apply_loaded_settings()

    def project_opened(self):
        for view in self.views:
            view.project_opened()

    def prepare_close(self):
        for view in self.views:
            view.prepare_close()

    def prepare_model_replacement(self):
        for view in self.views:
            view.prepare_model_replacement()

    def flush_pending_edits(self):
        for view in self.views:
            view.flush_pending_edits()

    def disconnect_project(self):
        for view in self.views:
            view.disconnect_project()

    def project_closed(self):
        for view in self.views:
            view.project_closed()

    # ------------------------------------------------------ questions

    def translate(self, text):
        view = self.primary
        return view.translate(text) if view is not None else text

    def project_name(self):
        view = self.primary
        return view.project_name() if view is not None else ""

    def confirm_unsaved_changes(self):
        view = self.primary
        return view.confirm_unsaved_changes() if view is not None else None

    def show_save_failures(self, files):
        view = self.primary
        if view is not None:
            view.show_save_failures(files)

    def show_load_failures(self, files):
        view = self.primary
        if view is not None:
            view.show_load_failures(files)

    def capture_project_state(self):
        """Copy view state into the project's settings, once.

        The settings hold one last tab and one set of open documents, so
        the primary window's are the ones recorded.
        """
        view = self.primary
        if view is not None:
            view.capture_project_state()
