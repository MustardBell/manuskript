"""The manuscript document area as an independently dockable surface."""

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from manuskript.ui.editors.mainEditor import mainEditor


class EditorPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("editorPanel")
        self.editor = mainEditor(self)
        self.editor.setObjectName("mainEditor")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.editor)


def build_editor(context, parent):
    return EditorPanel(parent)
