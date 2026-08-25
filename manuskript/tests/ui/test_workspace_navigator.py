"""The navigator lists places, and a panel asks to be one of them.

Rows used to come from the main tab widget, one per page, so a row could
only ever stand for a page. Anything that stopped being a page lost its
row -- which is exactly what happened to Characters.
"""

from types import SimpleNamespace

import pytest

from manuskript.panels import (
    NavigatorEntry,
    ToolPanelDescriptor,
    WorkspaceSurfaceDescriptor,
)
from manuskript.ui.workspace_navigator import (
    NavigatorTarget,
    WorkspaceNavigator,
)


def test_a_row_stands_for_a_page_or_a_panel_but_not_both():
    with pytest.raises(ValueError):
        NavigatorTarget("Both", page=1, panel_id="plugin.notes")
    with pytest.raises(ValueError):
        NavigatorTarget("Neither")


def test_panels_contribute_rows_and_the_order_declares_the_reading():
    navigator = WorkspaceNavigator.compose(
        pages=(
            NavigatorTarget("General", order=100, page=0),
            NavigatorTarget("Editor", order=700, page=6),
        ),
        surfaces=(
            WorkspaceSurfaceDescriptor(
                id="core.entities.characters",
                title="Characters",
                navigator=NavigatorEntry("Characters", "characters", 300),
            ),
            # A surface may exist without being listed. A tool panel cannot
            # be here at all -- that is the type's job now, not a field
            # this has to check.
            WorkspaceSurfaceDescriptor(id="core.drafts", title="Drafts"),
        ),
    )

    assert [target.label for target in navigator.targets] == [
        "General", "Characters", "Editor",
    ]
    assert navigator.row_for_panel("core.drafts") is None


def test_a_plugin_panel_takes_a_row_on_the_same_terms_as_core():
    """Nothing here knows which panels the application ships."""
    navigator = WorkspaceNavigator.compose(
        pages=(NavigatorTarget("General", order=100, page=0),),
        surfaces=(
            WorkspaceSurfaceDescriptor(
                id="plugin.research.sources",
                title="Sources",
                navigator=NavigatorEntry("Sources", "folder", 150),
            ),
        ),
    )

    assert navigator.row_for_panel("plugin.research.sources") == 1
    target = navigator.target(1)
    assert target.opens_panel
    assert target.panel_id == "plugin.research.sources"


def test_an_explicit_launcher_survives_without_changing_other_membership():
    launcher = NavigatorTarget(
        "Editor", "editor", 700,
        panel_id="core.editor",
        creates_surface=True,
    )
    navigator = WorkspaceNavigator.compose(
        surfaces=(), launchers=(launcher,),
    )

    target = navigator.target(navigator.row_for_panel("core.editor"))

    assert target.creates_surface


def test_an_owned_surface_replaces_its_construction_launcher():
    descriptor = SimpleNamespace(
        id="core.editor",
        navigator=SimpleNamespace(label="Editor", icon="editor", order=700),
    )
    launcher = NavigatorTarget(
        "Editor", "editor", 700,
        panel_id="core.editor",
        creates_surface=True,
    )

    navigator = WorkspaceNavigator.compose(
        surfaces=(descriptor,), launchers=(launcher,),
    )

    assert len(navigator.targets) == 1
    assert not navigator.targets[0].creates_surface


def test_a_page_row_is_found_again_when_the_page_changes():
    navigator = WorkspaceNavigator.compose(
        pages=(
            NavigatorTarget("General", order=100, page=0),
            NavigatorTarget("Editor", order=700, page=6),
        ),
        surfaces=(),
    )

    assert navigator.row_for_page(6) == 1
    assert navigator.row_for_page(4) is None
    assert navigator.target(99) is None
