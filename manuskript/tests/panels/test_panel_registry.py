"""One list of panels, whoever contributed them.

The registry is what lets a second window build the same panels as the
first without either window knowing where a panel came from. It stays
Qt-free because it is built in main.prepare, before a QApplication
exists.
"""

import pytest

from manuskript.panels import (
    DOCK,
    SPLITTER_SLOT,
    ToolPanelDescriptor,
    PanelRegistry,
    PanelRegistryError,
    SplitterSlot,
)


def dock_panel(panel_id="vendor.notes", title="Notes"):
    return ToolPanelDescriptor(id=panel_id, title=title)


def test_descriptors_come_back_in_registration_order():
    registry = PanelRegistry()
    registry.register(dock_panel("core.metadata", "Metadata"))
    registry.register(dock_panel("vendor.notes", "Notes"))

    assert [entry.id for entry in registry.descriptors()] == [
        "core.metadata", "vendor.notes",
    ]
    assert registry.descriptor("vendor.notes").title == "Notes"


def test_descriptors_can_be_filtered_by_placement():
    registry = PanelRegistry()
    registry.register(dock_panel("vendor.notes"))
    registry.register(ToolPanelDescriptor(
        id="core.metadata",
        title="Metadata",
        placement=SPLITTER_SLOT,
        slot=SplitterSlot("splitterRedacH", 2),
    ))

    assert [
        entry.id for entry in registry.descriptors(placement=DOCK)
    ] == ["vendor.notes"]
    assert [
        entry.id
        for entry in registry.descriptors(placement=SPLITTER_SLOT)
    ] == ["core.metadata"]


def test_a_second_claim_on_a_panel_id_is_refused():
    registry = PanelRegistry()
    registry.register(dock_panel("vendor.notes"))

    with pytest.raises(PanelRegistryError, match="vendor.notes"):
        registry.register(dock_panel("vendor.notes", "Impostor"))

    assert registry.descriptor("vendor.notes").title == "Notes"


def test_asking_for_an_unknown_panel_names_it():
    registry = PanelRegistry()

    with pytest.raises(PanelRegistryError, match="core.ghost"):
        registry.descriptor("core.ghost")
    with pytest.raises(PanelRegistryError, match="core.ghost"):
        registry.deregister("core.ghost")


def test_listeners_hear_about_arrivals_and_departures():
    """Hosts refresh their menus from this: a plugin enabling mid-session
    must surface its panel without the window being rebuilt.
    """
    registry = PanelRegistry()
    changes = []

    def listener():
        changes.append(len(registry.descriptors()))

    registry.subscribe(listener)
    registry.register(dock_panel())
    registry.deregister("vendor.notes")

    assert changes == [1, 0]

    registry.unsubscribe(listener)
    registry.register(dock_panel())
    assert changes == [1, 0]


def test_a_failing_listener_stops_neither_the_change_nor_the_rest():
    registry = PanelRegistry()
    heard = []

    def broken():
        raise RuntimeError("host exploded")

    registry.subscribe(broken)
    registry.subscribe(lambda: heard.append(True))

    registry.register(dock_panel())

    assert heard == [True]
    assert [entry.id for entry in registry.descriptors()] == [
        "vendor.notes",
    ]


def test_a_splitter_panel_must_say_which_slot():
    """A splitter panel without a slot could only be placed by guessing,
    and a dotless id could never carry its owner's namespace.
    """
    with pytest.raises(ValueError, match="which slot"):
        ToolPanelDescriptor(
            id="core.metadata",
            title="Metadata",
            placement=SPLITTER_SLOT,
        )
    with pytest.raises(ValueError, match="dotted"):
        ToolPanelDescriptor(id="metadata", title="Metadata")
    with pytest.raises(ValueError, match="placement"):
        ToolPanelDescriptor(
            id="core.metadata",
            title="Metadata",
            placement="floating",
        )


# ------------------------------------------------ scope and multiplicity

def test_a_panel_says_what_it_belongs_to_and_how_many_there_may_be():
    """Stated rather than inferred, because the alternative was every
    host deciding for itself -- and two hosts deciding differently is
    what made opening a second window fail outright.
    """
    from manuskript.panels import (
        APPLICATION,
        PER_WINDOW,
        PROJECT,
        SINGLETON,
    )

    default = ToolPanelDescriptor(id="vendor.notes", title="Notes")
    assert default.scope == APPLICATION
    assert default.multiplicity == PER_WINDOW
    assert default.requires_project is False
    assert default.per_window is True

    scoped = ToolPanelDescriptor(
        id="vendor.scoped",
        title="Scoped",
        scope=PROJECT,
        multiplicity=SINGLETON,
    )
    assert scoped.requires_project is True
    assert scoped.per_window is False


def test_an_unknown_scope_or_multiplicity_is_refused():
    with pytest.raises(ValueError, match="scope"):
        ToolPanelDescriptor(id="v.x", title="X", scope="document")
    with pytest.raises(ValueError, match="multiplicity"):
        ToolPanelDescriptor(id="v.x", title="X", multiplicity="many")


def test_a_tool_panel_can_declare_which_surfaces_it_accompanies():
    routed = ToolPanelDescriptor(
        id="vendor.structure",
        title="Structure",
        visible_with_surfaces=("core.editor", "vendor.board"),
        preferred_extent=280,
    )

    assert routed.visible_with_surfaces == (
        "core.editor", "vendor.board",
    )
    assert routed.preferred_extent == 280
    assert ToolPanelDescriptor(
        id="vendor.notes", title="Notes",
    ).visible_with_surfaces is None

    with pytest.raises(ValueError, match="dotted surface ids"):
        ToolPanelDescriptor(
            id="vendor.bad",
            title="Bad",
            visible_with_surfaces=("editor",),
        )
    with pytest.raises(ValueError, match="twice"):
        ToolPanelDescriptor(
            id="vendor.duplicate",
            title="Duplicate",
            visible_with_surfaces=("core.editor", "core.editor"),
        )
    with pytest.raises(ValueError, match="non-negative integer"):
        ToolPanelDescriptor(
            id="vendor.negative",
            title="Negative",
            preferred_extent=-1,
        )
