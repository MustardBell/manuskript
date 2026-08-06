"""Reading and applying an arrangement on the editor widgets.

The editor describes and restores arrangements itself; what is tested
here is the reconciling around it. What must not happen is a stored
layout being refused, or half of it silently dropped.
"""

from unittest.mock import MagicMock

from manuskript.domain.document_area import (
    HORIZONTAL,
    VERTICAL,
    Split,
    TabGroup,
    to_data,
)
from manuskript.ui.editors.document_area_layout import (
    describe_area,
    read_area,
    restore_area,
)


def modelled_widget():
    """A widget that describes and restores arrangements itself."""
    return MagicMock(spec=["describe", "restore"])



def test_nothing_to_describe_is_not_an_empty_arrangement():
    """The caller falls back to what the project remembers, rather than
    recording that nothing was open.
    """
    splitter = modelled_widget()
    splitter.describe.return_value = None

    assert read_area(splitter) is None
    assert describe_area(splitter) is None




def test_an_unreadable_arrangement_is_ignored_not_raised():
    splitter = modelled_widget()

    assert restore_area(splitter, {"nonsense": True}) is False

    splitter.restore.assert_not_called()


def test_an_arrangement_saved_by_an_older_manuskript_still_applies():
    """Old stored data is real where old widgets are not: a layout saved
    before arrangements were a model is still somebody's layout.
    """
    splitter = modelled_widget()

    assert restore_area(splitter, [2, ["a"], [0, ["b"], None]]) is True

    splitter.restore.assert_called_once_with(
        Split(VERTICAL, TabGroup(["a"]), TabGroup(["b"]))
    )





def test_a_widget_that_speaks_the_model_is_asked_directly():
    """It is the only thing that knows whether a side has been divided,
    so it describes itself rather than being read through a shape that
    cannot express that.
    """
    area = Split(
        VERTICAL,
        Split(HORIZONTAL, TabGroup(["a"]), TabGroup(["b"])),
        TabGroup(["c"]),
    )
    splitter = modelled_widget()
    splitter.describe.return_value = area

    assert read_area(splitter) == area
    assert describe_area(splitter) == to_data(area)


def test_a_widget_that_speaks_the_model_restores_the_tree_itself():
    """No flattening: the arrangement is handed over as it was stored."""
    area = Split(
        VERTICAL,
        Split(HORIZONTAL, TabGroup(["a"]), TabGroup(["b"])),
        TabGroup(["c"]),
    )
    splitter = modelled_widget()

    assert restore_area(splitter, to_data(area)) is True

    splitter.restore.assert_called_once_with(area)
