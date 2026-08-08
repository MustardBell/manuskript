"""Widget factories for the panels Manuskript itself ships.

The declarations live Qt-free in :mod:`manuskript.panels.core`; this
package holds their Qt halves. A window passes these factories when it
registers the core panels, so the registry stays importable before any
QApplication exists.
"""

from PyQt5.QtWidgets import QWidget

from manuskript.panels.core import (
    BOOK_SUMMARY,
    METADATA,
    PROJECT_TREE,
    STORYLINE,
)
from manuskript.ui.panels.core.book_summary import build_book_summary
from manuskript.ui.panels.core.metadata import build_metadata
from manuskript.ui.panels.core.project_tree import build_project_tree
from manuskript.ui.panels.core.storyline import build_storyline


def core_panel_factories():
    """Panel id -> widget factory, one per core panel.

    All four workspace panels are factory-built now; the Designer file
    no longer declares any of them.
    """
    return {
        BOOK_SUMMARY: build_book_summary,
        METADATA: build_metadata,
        PROJECT_TREE: build_project_tree,
        STORYLINE: build_storyline,
    }


# The old interface still names these widgets directly on MainWindow.  Keep
# that compatibility in one explicit adapter after the panel has been built;
# the factories themselves receive no window and cannot acquire unrelated
# application services through it.  As callers move to PanelHost, entries can
# disappear from this table without changing the construction contract.
_LEGACY_ALIASES = {
    BOOK_SUMMARY: {
        "grpPlotSummary": None,
        "comboBox_2": "comboBox_2",
        "stkPlotSummary": "stkPlotSummary",
        "txtPlotSummaryPara": "txtPlotSummaryPara",
        "txtPlotSummaryPage": "txtPlotSummaryPage",
        "txtPlotSummaryFull": "txtPlotSummaryFull",
    },
    PROJECT_TREE: {
        "treeRedacWidget": None,
        "treeRedacOutline": "treeRedacOutline",
        "btnRedacAddFolder": "btnRedacAddFolder",
        "btnRedacAddText": "btnRedacAddText",
        "btnRedacRemoveItem": "btnRedacRemoveItem",
    },
    METADATA: {"redacMetadata": None},
    STORYLINE: {"storylineView": None},
}


def install_legacy_panel_aliases(window, panel_id, widget):
    """Expose a core panel under the names old UI callers still use.

    This is an anti-corruption adapter, not part of panel construction.  It is
    intentionally the only core-panel module allowed to write those aliases.
    """
    for attribute, object_name in _LEGACY_ALIASES.get(panel_id, {}).items():
        value = (
            widget
            if object_name is None
            else widget.findChild(QWidget, object_name)
        )
        if value is None:
            raise LookupError(
                "Panel {} did not build required view {!r}.".format(
                    panel_id, object_name,
                )
            )
        setattr(window, attribute, value)
