"""Typed access to the core panel widgets owned by one panel host.

Qt ``objectName`` values remain useful for saved layouts and UI inspection,
but they are not an application interface.  This module resolves those names
once, immediately after the core panels are built, and gives the rest of the
application a small, explicit view set instead of copying Designer-era widget
names onto :class:`MainWindow`.
"""

from dataclasses import dataclass

from PyQt5.QtWidgets import (
    QComboBox,
    QGroupBox,
    QPushButton,
    QStackedWidget,
    QWidget,
)

from manuskript.panels.core import (
    BOOK_SUMMARY,
    METADATA,
    PROJECT_TREE,
    STORYLINE,
)
from manuskript.ui.views.MDEditCompleter import MDEditCompleter
from manuskript.ui.views.metadataView import metadataView
from manuskript.ui.views.storylineView import storylineView
from manuskript.ui.views.treeView import treeView


def _panel_widget(host, panel_id, widget_type):
    instance = host.instance(panel_id)
    if instance is None:
        raise LookupError("Required core panel {} is not open.".format(panel_id))
    widget = instance.widget
    if not isinstance(widget, widget_type):
        raise TypeError(
            "Core panel {} built {}, expected {}.".format(
                panel_id,
                type(widget).__name__,
                widget_type.__name__,
            )
        )
    return widget


def _required_child(parent, widget_type, object_name):
    child = parent.findChild(widget_type, object_name)
    if child is None:
        raise LookupError(
            "Core panel {} has no {} named {!r}.".format(
                parent.objectName(),
                widget_type.__name__,
                object_name,
            )
        )
    return child


@dataclass(frozen=True)
class BookSummaryPanelViews:
    """The book-summary panel and the controls its bindings use."""

    panel: QGroupBox
    selector: QComboBox
    pages: QStackedWidget
    paragraph_editor: MDEditCompleter
    page_editor: MDEditCompleter
    full_editor: MDEditCompleter

    @classmethod
    def from_panel(cls, panel):
        return cls(
            panel=panel,
            selector=_required_child(panel, QComboBox, "comboBox_2"),
            pages=_required_child(panel, QStackedWidget, "stkPlotSummary"),
            paragraph_editor=_required_child(
                panel, MDEditCompleter, "txtPlotSummaryPara",
            ),
            page_editor=_required_child(
                panel, MDEditCompleter, "txtPlotSummaryPage",
            ),
            full_editor=_required_child(
                panel, MDEditCompleter, "txtPlotSummaryFull",
            ),
        )


@dataclass(frozen=True)
class ProjectTreePanelViews:
    """The project tree panel and its editing controls."""

    panel: QWidget
    tree: treeView
    add_folder: QPushButton
    add_text: QPushButton
    remove_item: QPushButton

    @classmethod
    def from_panel(cls, panel):
        return cls(
            panel=panel,
            tree=_required_child(panel, treeView, "treeRedacOutline"),
            add_folder=_required_child(
                panel, QPushButton, "btnRedacAddFolder",
            ),
            add_text=_required_child(panel, QPushButton, "btnRedacAddText"),
            remove_item=_required_child(
                panel, QPushButton, "btnRedacRemoveItem",
            ),
        )


@dataclass(frozen=True)
class CorePanelViewSet:
    """The core panel views belonging to one workspace window."""

    book_summary: BookSummaryPanelViews
    project_tree: ProjectTreePanelViews
    metadata: metadataView
    storyline: storylineView

    @classmethod
    def from_host(cls, host):
        book_summary = _panel_widget(host, BOOK_SUMMARY, QGroupBox)
        project_tree = _panel_widget(host, PROJECT_TREE, QWidget)
        return cls(
            book_summary=BookSummaryPanelViews.from_panel(book_summary),
            project_tree=ProjectTreePanelViews.from_panel(project_tree),
            metadata=_panel_widget(host, METADATA, metadataView),
            storyline=_panel_widget(host, STORYLINE, storylineView),
        )
