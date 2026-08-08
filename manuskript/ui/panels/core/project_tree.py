"""The Project tree panel: the outline tree and its add/remove buttons.

The most referenced widget of the four -- action bindings, navigation,
search and a dozen controllers reach ``treeRedacOutline`` by attribute.
The factory rebuilds exactly what the Designer file declared, aliases
included, and must run before the window's actions are bound.
"""

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from manuskript.ui.views.treeView import treeView


def _flat_icon_button(parent, theme_name, object_name):
    button = QPushButton(parent)
    button.setText("")
    button.setIcon(QIcon.fromTheme(theme_name))
    button.setFlat(True)
    button.setObjectName(object_name)
    return button


def build_project_tree(context, parent):
    panel = QWidget(parent)
    panel.setObjectName("treeRedacWidget")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)

    tree = treeView(panel)
    tree.setAutoFillBackground(True)
    tree.setFrameShape(QFrame.NoFrame)
    tree.setEditTriggers(QAbstractItemView.EditKeyPressed)
    tree.setObjectName("treeRedacOutline")
    tree.header().setVisible(False)
    layout.addWidget(tree)

    buttons = QHBoxLayout()
    add_folder = _flat_icon_button(panel, "folder-new", "btnRedacAddFolder")
    add_text = _flat_icon_button(panel, "document-new", "btnRedacAddText")
    remove = _flat_icon_button(panel, "list-remove", "btnRedacRemoveItem")
    buttons.addWidget(add_folder)
    buttons.addWidget(add_text)
    buttons.addWidget(remove)
    buttons.addItem(QSpacerItem(
        40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum,
    ))
    layout.addLayout(buttons)

    return panel
