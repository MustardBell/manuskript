"""Ten core widgets, two owners, and which of them comes from which.

A window used to build its view set from one host because one host owned
everything. Seven of the ten are places the writer goes and are moving to
the workspace's surface host; three are tools and stay with the panel
host. The table that says which is which is the thing the cutover edits,
so it is what these tests are about.
"""

import pytest

from unittest.mock import MagicMock

from PyQt5.QtWidgets import QWidget

from manuskript.panels import (
    ToolPanelDescriptor,
    WorkspaceSurfaceDescriptor,
)
from manuskript.panels.core import core_panel_descriptors
from manuskript.ui.panels.core.views import (
    CORE_MEMBERS,
    SURFACE,
    TOOL_PANEL,
    CorePanelViewSet,
)


#: Written out rather than derived from CORE_MEMBERS: a test that read the
#: table would agree with whatever the table said, including after somebody
#: moved a member to the wrong owner.
TOOL_PANEL_IDS = {
    "core.project-tree",
    "core.metadata",
    "core.storyline",
}

SURFACE_IDS = {
    "core.general",
    "core.entities.project",
    "core.entities.characters",
    "core.entities.plots",
    "core.entities.world",
    "core.outline",
    "core.editor",
}


class Host:
    """A host that hands back whatever it was built holding.

    Records what it was asked for, because the point of two hosts is that
    each is asked only for what it owns -- and a host that is asked for a
    stranger and answers is how one owner quietly kept everything.
    """

    def __init__(self, members):
        self.instances = {
            member.panel_id: MagicMock(
                widget=MagicMock(spec=member.widget_type)
            )
            for member in members
        }
        self.asked = []

    def instance(self, panel_id):
        self.asked.append(panel_id)
        return self.instances.get(panel_id)


def hosts():
    tools = Host([m for m in CORE_MEMBERS if m.owner == TOOL_PANEL])
    surfaces = Host([m for m in CORE_MEMBERS if m.owner == SURFACE])
    return tools, surfaces


def test_the_table_covers_the_core_panels_and_invents_none():
    """Every core panel, once, and nothing that is not one."""

    declared = {descriptor.id for descriptor in core_panel_descriptors()}
    tabled = [member.panel_id for member in CORE_MEMBERS]

    assert set(tabled) == declared
    assert len(tabled) == len(declared)


def test_each_member_is_owned_by_the_host_that_holds_its_kind():
    """The one assertion the cutover cannot make quietly wrong.

    A surface resolved from the panel host raises at window construction
    once the surfaces move -- after the window is half built, from a
    lookup that reads like the panel merely failed to open. Asked of the
    descriptors instead, so the table has to keep agreeing with what each
    panel says it is.
    """

    kinds = {
        descriptor.id: descriptor
        for descriptor in core_panel_descriptors()
    }
    expected = {
        ToolPanelDescriptor: TOOL_PANEL,
        WorkspaceSurfaceDescriptor: SURFACE,
    }

    for member in CORE_MEMBERS:
        descriptor = kinds[member.panel_id]
        assert member.owner == expected[type(descriptor)], member.panel_id


def test_the_written_out_ownership_matches_the_declarations():
    """Guards the lists above, which every other test here leans on."""

    declared_tools = {
        descriptor.id
        for descriptor in core_panel_descriptors()
        if isinstance(descriptor, ToolPanelDescriptor)
    }
    declared_surfaces = {
        descriptor.id
        for descriptor in core_panel_descriptors()
        if isinstance(descriptor, WorkspaceSurfaceDescriptor)
    }

    assert declared_tools == TOOL_PANEL_IDS
    assert declared_surfaces == SURFACE_IDS


def test_each_owner_is_asked_only_for_what_it_owns():
    tools, surfaces = hosts()

    views = CorePanelViewSet.from_hosts(tools=tools, surfaces=surfaces)

    assert tools.asked == []
    assert surfaces.asked == []

    # Reading existing structure is allowed; constructing it is not.
    for member in CORE_MEMBERS:
        getattr(views, member.attribute)
    assert set(tools.asked) == TOOL_PANEL_IDS
    assert set(surfaces.asked) == SURFACE_IDS


def test_the_view_set_holds_the_widgets_its_owners_built():
    tools, surfaces = hosts()

    views = CorePanelViewSet.from_hosts(tools=tools, surfaces=surfaces)

    assert views.editor is surfaces.instances["core.editor"].widget
    assert views.metadata is tools.instances["core.metadata"].widget
    # The project tree is the one member that is more than its widget.
    assert (
        views.project_tree.panel
        is tools.instances["core.project-tree"].widget
    )


def test_one_host_that_owns_everything_still_works():
    """What the window does today, and until the cutover.

    Both arguments are the panel host while it still owns all ten. If this
    stopped working the seam would have become the migration.
    """

    everything = Host(CORE_MEMBERS)

    views = CorePanelViewSet.from_hosts(
        tools=everything, surfaces=everything,
    )

    assert views.editor is everything.instances["core.editor"].widget


def test_a_missing_member_says_which_owner_was_asked():
    """With one host a miss meant "not open yet".

    With two it may equally mean "asked of the wrong one", and the two
    have different fixes, so the message has to distinguish them.
    """

    tools, surfaces = hosts()
    del surfaces.instances["core.editor"]

    views = CorePanelViewSet.from_hosts(tools=tools, surfaces=surfaces)
    with pytest.raises(LookupError) as raised:
        _ = views.editor

    message = str(raised.value)
    assert "core.editor" in message
    assert "surface host" in message


def test_a_missing_tool_is_allowed_until_a_consumer_actually_needs_it():
    tools, surfaces = hosts()
    del tools.instances["core.project-tree"]

    views = CorePanelViewSet.from_hosts(tools=tools, surfaces=surfaces)

    assert views.editor is surfaces.instances["core.editor"].widget
    with pytest.raises(LookupError) as raised:
        _ = views.project_tree

    message = str(raised.value)
    assert "core.project-tree" in message
    assert "panel host" in message


def test_a_member_built_as_the_wrong_widget_is_refused():
    """A host answering with something else is a defect, not a view."""

    tools, surfaces = hosts()
    surfaces.instances["core.editor"] = MagicMock(
        widget=MagicMock(spec=QWidget)
    )

    views = CorePanelViewSet.from_hosts(tools=tools, surfaces=surfaces)
    with pytest.raises(TypeError, match="core.editor"):
        _ = views.editor
