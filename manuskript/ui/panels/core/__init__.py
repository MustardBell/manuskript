"""Widget factories for the panels Manuskript itself ships.

The declarations live Qt-free in :mod:`manuskript.panels.core`; this
package holds their Qt halves. A window passes these factories when it
registers the core panels, so the registry stays importable before any
QApplication exists.
"""

from manuskript.panels.core import BOOK_SUMMARY
from manuskript.ui.panels.core.book_summary import build_book_summary


def core_panel_factories():
    """Panel id -> widget factory, for every core panel that has one.

    Panels absent from this mapping are still attached from the
    Designer file; they disappear from here one migration at a time --
    in the other direction.
    """
    return {
        BOOK_SUMMARY: build_book_summary,
    }
