"""Widget factories for the panels Manuskript itself ships.

The declarations live Qt-free in :mod:`manuskript.panels.core`; this
package holds their Qt halves. A window passes these factories when it
registers the core panels, so the registry stays importable before any
QApplication exists.
"""

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
