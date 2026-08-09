class ViewConfigurationController:
    """Apply persisted view choices through a narrow UI adapter."""

    SIMPLE = "simple"
    FICTION = "fiction"

    def __init__(self, view, settings):
        self.view = view
        self.settings = settings

    def set_simple(self):
        self.settings.viewMode = self.SIMPLE
        self.view.select_editor_tab()
        self.view.set_fiction_features_visible(False)
        self.view.set_mode_checked(self.SIMPLE)

    def set_fiction(self):
        self.settings.viewMode = self.FICTION
        self.view.set_fiction_features_visible(True)
        self.view.set_mode_checked(self.FICTION)

    def set_view_setting(self, category, part, value, _checked=False):
        self.settings.viewSettings[category][part] = value
        self.view.refresh_category(category)

    def dispose(self):
        self.view = None
        self.settings = None
