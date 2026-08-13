"""The structural outline surface, built independently for each workspace."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from manuskript.ui.views.basicItemView import basicItemView
from manuskript.ui.views.outlineView import outlineView
from manuskript.ui.views.plotTreeView import plotTreeView


def _flat_icon_button(parent, theme_name, object_name, label):
    button = QPushButton(parent)
    button.setText("")
    button.setIcon(QIcon.fromTheme(theme_name))
    button.setFlat(True)
    button.setObjectName(object_name)
    button.setToolTip(label)
    button.setAccessibleName(label)
    return button


class OutlinePanel(QWidget):
    """Plots, outline structure, and the selected item's compact editor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("outlinePanel")

        self.splitterOutlineH = QSplitter(Qt.Horizontal, self)
        self.splitterOutlineH.setObjectName("splitterOutlineH")

        self.lstOutlinePlots = plotTreeView(self.splitterOutlineH)
        self.lstOutlinePlots.setObjectName("lstOutlinePlots")
        self.lstOutlinePlots.setDragEnabled(True)
        self.lstOutlinePlots.setDragDropMode(QAbstractItemView.DragOnly)
        self.lstOutlinePlots.header().setVisible(False)

        right = QWidget(self.splitterOutlineH)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.splitterOutlineV = QSplitter(Qt.Vertical, right)
        self.splitterOutlineV.setObjectName("splitterOutlineV")
        self.treeOutlineOutline = outlineView(self.splitterOutlineV)
        self.treeOutlineOutline.setObjectName("treeOutlineOutline")
        self.treeOutlineOutline.setDragEnabled(True)
        self.treeOutlineOutline.setDragDropMode(QAbstractItemView.DragDrop)
        self.treeOutlineOutline.setDefaultDropAction(Qt.MoveAction)
        self.treeOutlineOutline.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )
        self.treeOutlineOutline.header().setStretchLastSection(False)

        self.detailsFrame = QFrame(self.splitterOutlineV)
        self.detailsFrame.setObjectName("outlineDetailsFrame")
        self.detailsFrame.setFrameShape(QFrame.StyledPanel)
        self.detailsFrame.setFrameShadow(QFrame.Raised)
        details_layout = QVBoxLayout(self.detailsFrame)
        self.outlineItemEditor = basicItemView(self.detailsFrame)
        self.outlineItemEditor.setObjectName("outlineItemEditor")
        details_layout.addWidget(self.outlineItemEditor)
        right_layout.addWidget(self.splitterOutlineV, 1)

        buttons = QHBoxLayout()
        self.btnOutlineAddFolder = _flat_icon_button(
            right,
            "folder-new",
            "btnOutlineAddFolder",
            self.tr("Add folder"),
        )
        self.btnOutlineAddText = _flat_icon_button(
            right,
            "document-new",
            "btnOutlineAddText",
            self.tr("Add text"),
        )
        self.btnOutlineRemoveItem = _flat_icon_button(
            right,
            "list-remove",
            "btnOutlineRemoveItem",
            self.tr("Remove selected items"),
        )
        self.btnPlanShowDetails = _flat_icon_button(
            right,
            "text-x-generic",
            "btnPlanShowDetails",
            self.tr("Show item details"),
        )
        self.btnPlanShowDetails.setCheckable(True)
        self.btnPlanShowDetails.setChecked(True)
        buttons.addWidget(self.btnOutlineAddFolder)
        buttons.addWidget(self.btnOutlineAddText)
        buttons.addWidget(self.btnOutlineRemoveItem)
        buttons.addStretch(1)
        buttons.addWidget(self.btnPlanShowDetails)
        right_layout.addLayout(buttons)

        self.btnPlanShowDetails.toggled.connect(
            self.detailsFrame.setVisible
        )
        self.splitterOutlineH.setStretchFactor(0, 25)
        self.splitterOutlineH.setStretchFactor(1, 75)
        self.splitterOutlineV.setStretchFactor(0, 75)
        self.splitterOutlineV.setStretchFactor(1, 25)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitterOutlineH)


def build_outline(context, parent):
    return OutlinePanel(parent)
