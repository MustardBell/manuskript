"""Project binding lifecycle owned by one workspace."""


class WorkspaceProjectBinding:
    """Bind one project's models and contexts to one workspace's views."""

    def __init__(self, binding, markdown_menu):
        self._binding = binding
        self._markdown_menu = markdown_menu

    @property
    def reference_service(self):
        return self._binding.reference_service

    @property
    def text_editor_context(self):
        return self._binding.text_editor_context

    def connect(self):
        self._binding.bind()

    def disconnect(self):
        self._binding.unbind()
        self._markdown_menu.attach(None)

    def dispose(self):
        self.disconnect()
        self._binding = None
        self._markdown_menu = None
