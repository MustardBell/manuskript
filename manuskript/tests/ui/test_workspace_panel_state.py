"""A panel says what it remembers; the controller that saves only asks.

The list of panels with state of their own used to live in
WorkspaceStateController, together with the widget methods to call and the
widget to call them on. So the central controller named one panel's
internals, and a new panel with an arrangement worth keeping meant editing
it -- the panel could not answer for itself.
"""

import inspect
from dataclasses import replace

from unittest.mock import MagicMock

from manuskript.panels import (
    PanelRegistryError,
    DOCK,
    PROJECT,
    SPLITTER_SLOT,
    ToolPanelDescriptor,
    PanelState,
    SplitterSlot,
)
from manuskript.panels.core import (
    METADATA,
    METADATA_REVISIONS_STATE,
    core_panel_descriptors,
)
from manuskript.services.workspace_state import (
    WORKSPACE_STATE_VERSION,
    WorkspaceWindowState,
)
from manuskript.ui import workspace_state_controller
from manuskript.ui.panels.host import PanelInstance
from manuskript.ui.workspace_state_controller import (
    WorkspaceStateController,
    WorkspaceStateViews,
)


class Notebook:
    """A panel widget whose state is which page it was left open at.

    ``isHidden`` because a window's layout also records whether each panel
    was showing; that is the part every panel has, and it is not what
    these tests are about.
    """

    def __init__(self, page=0):
        self.page = page

    @staticmethod
    def isHidden():
        return False


NOTEBOOK = "plugin.notes.notebook"

#: A panel the controller has never heard of, that remembers something.
NOTEBOOK_PANEL = ToolPanelDescriptor(
    id=NOTEBOOK,
    title="Notebook",
    placement=DOCK,
    scope=PROJECT,
    state=(
        PanelState(
            key=NOTEBOOK,
            capture=lambda widget: widget.page,
            restore=lambda widget, value: setattr(
                widget, "page", int(value),
            ),
        ),
    ),
)


class Host:
    """Enough of a panel host to answer what this window is showing."""

    def __init__(self, instances):
        self._instances = instances
        self.shown = {}
        self.synced = 0

    def instance(self, panel_id):
        return self._instances.get(panel_id)

    @property
    def instances(self):
        return dict(self._instances)

    def set_visible(self, panel_id, visible):
        self.shown[panel_id] = visible

    def sync_visibility(self):
        self.synced += 1


class Registry:
    """Enough of a panel registry to say where panels sit, and what."""

    def __init__(self, descriptors):
        self._descriptors = tuple(descriptors)

    def descriptor(self, panel_id):
        for descriptor in self._descriptors:
            if descriptor.id == panel_id:
                return descriptor
        raise PanelRegistryError("Unknown panel {!r}.".format(panel_id))

    def descriptors(self, placement=None):
        # Mirrors the real registry: filtering by placement is a tool
        # panel's question, so a surface is never a candidate for it.
        if placement is None:
            return self._descriptors
        return tuple(
            descriptor
            for descriptor in self._descriptors
            if isinstance(descriptor, ToolPanelDescriptor)
            and descriptor.placement == placement
        )


#: Enough of the real core list for the controller to ask what a saved
#: id names. Taken from the panels themselves rather than restated, so a
#: descriptor changing kind cannot leave these tests agreeing with a
#: rule nobody follows any more.
CORE_DESCRIPTORS = core_panel_descriptors()


def surface_instance(surface_id):
    descriptor = next(
        candidate
        for candidate in CORE_DESCRIPTORS
        if candidate.id == surface_id
    )
    return PanelInstance(descriptor=descriptor, widget=MagicMock())


def a_window(instances=(), descriptors=(), surfaces=()):
    window = MagicMock()
    # WorkspaceStateViews reads this as a boolean, and a save with a
    # project active describes the document area.
    window._projectSurfaceActive = False
    # Which must not be an unconstrained mock. describe_area walks what
    # the splitter describes, and a MagicMock answers every question with
    # another MagicMock -- so the walk never ends and the allocation
    # never stops. It took a laptop down. Answering None here is what a
    # splitter with nothing open says, and it makes the project-active
    # path safe for every test in this file rather than for the ones
    # whose author remembered.
    window.corePanels.editor.editor.tabSplitter.describe.return_value = None
    window._activePanelId = None
    window.panelHost = Host(dict(instances))
    # The other owner, spelled out for the same reason: an unconstrained
    # MagicMock iterates as empty, so a window whose surfaces were left
    # to the mock would pass every test about them by holding none.
    window.surfaceHost = Host(dict(surfaces))
    window.panelRegistry = Registry(descriptors)
    return window


def saved_state(controller):
    """The state a save handed to the store."""
    return controller.store.save.call_args[0][0]


def state_controller(window, store=None):
    return WorkspaceStateController(
        WorkspaceStateViews.for_window(window),
        store=store,
    )


def test_a_panel_the_controller_never_heard_of_keeps_its_state():
    """The whole point. Nothing in the controller mentions this panel, and
    its page survives a save and a restore.
    """
    notebook = Notebook(page=3)
    instance = PanelInstance(descriptor=NOTEBOOK_PANEL, widget=notebook)
    window = a_window(instances={NOTEBOOK: instance})
    store = MagicMock()
    controller = state_controller(window, store)

    controller.save()

    assert saved_state(controller).panel_state == {NOTEBOOK: 3}

    store.load.return_value = WorkspaceWindowState(
        panel_state={NOTEBOOK: 7},
    )
    restored = controller.restore()

    assert notebook.page == 7
    assert restored is store.load.return_value


def test_a_panel_that_remembers_nothing_files_nothing():
    plain = ToolPanelDescriptor(id="plugin.notes.plain", title="Plain")
    window = a_window(
        instances={
            plain.id: PanelInstance(descriptor=plain, widget=MagicMock()),
        }
    )
    controller = state_controller(window, MagicMock())

    controller.save()

    assert saved_state(controller).panel_state == {}


def test_a_window_saves_the_surface_subset_its_host_owns():
    editor = next(
        descriptor
        for descriptor in CORE_DESCRIPTORS
        if descriptor.id == "core.editor"
    )
    instance = PanelInstance(descriptor=editor, widget=MagicMock())
    window = a_window(
        descriptors=CORE_DESCRIPTORS,
        surfaces={editor.id: instance},
    )
    controller = state_controller(window, MagicMock())

    controller.save()

    assert saved_state(controller).surfaces == ("core.editor",)


def test_nothing_recorded_leaves_a_panel_as_it_opened():
    """A first launch, or a panel added since the last one."""
    notebook = Notebook(page=2)
    window = a_window(
        instances={
            NOTEBOOK: PanelInstance(
                descriptor=NOTEBOOK_PANEL, widget=notebook,
            ),
        }
    )
    store = MagicMock()
    store.load.return_value = WorkspaceWindowState()
    controller = state_controller(window, store)

    controller.restore()

    assert notebook.page == 2


def test_the_splitters_remembered_are_the_ones_panels_sit_in():
    """A hardcoded pair of names meant a panel in a third splitter had its
    sizes forgotten until somebody came and added it.
    """
    descriptors = (
        ToolPanelDescriptor(
            id="core.first", title="First", placement=SPLITTER_SLOT,
            slot=SplitterSlot("splitterOne", 0),
        ),
        ToolPanelDescriptor(
            id="core.second", title="Second", placement=SPLITTER_SLOT,
            slot=SplitterSlot("splitterTwo", 1),
        ),
        # Same splitter as the first: named once, not twice.
        ToolPanelDescriptor(
            id="core.third", title="Third", placement=SPLITTER_SLOT,
            slot=SplitterSlot("splitterOne", 2),
        ),
        # A dock sits in no splitter.
        ToolPanelDescriptor(id="core.docked", title="Docked"),
    )
    window = a_window(descriptors=descriptors)
    controller = state_controller(window, MagicMock())

    controller.save()

    assert sorted(saved_state(controller).splitters) == [
        "splitterOne",
        "splitterTwo",
    ]


def test_core_docks_do_not_create_fixed_splitter_state():
    """Qt saveState owns native dock geometry; core declares no slots."""
    descriptors = core_panel_descriptors(redaction_group=object())
    window = a_window(descriptors=descriptors)
    controller = state_controller(window, MagicMock())

    controller.save()

    assert saved_state(controller).splitters == {}


def test_the_metadata_panel_says_what_it_remembers():
    """Under the keys it has always been stored under: a saved layout
    outlives this refactoring.
    """
    metadata = next(
        descriptor
        for descriptor in core_panel_descriptors(object())
        if descriptor.id == METADATA
    )

    assert [remembered.key for remembered in metadata.state] == [
        METADATA,
        METADATA_REVISIONS_STATE,
    ]

    panel = MagicMock()
    own, revisions = metadata.state

    assert own.capture(panel) is panel.saveState.return_value
    own.restore(panel, [True, False])
    panel.restoreState.assert_called_once_with([True, False])

    assert (
        revisions.capture(panel)
        is panel.revisions.saveState.return_value
    )
    revisions.restore(panel, [False])
    panel.revisions.restoreState.assert_called_once_with([False])


def test_the_controller_names_no_panel_and_no_panel_widget():
    """It knew one panel by attribute and two of its state keys by name.
    That is what made it the file to edit for every stateful panel.
    """
    source = inspect.getsource(workspace_state_controller)

    for named in ("redacMetadata", "core.metadata", "revisions"):
        assert named not in source, named


def test_workspace_state_controller_has_no_main_window_escape_hatch():
    controller = WorkspaceStateController(MagicMock(), store=MagicMock())

    assert not hasattr(controller, "window")


# ------------------------------------------------- an older arrangement


def a_saved_layout(version=WORKSPACE_STATE_VERSION,
                   window_state=b"arrangement"):
    """A store holding one window's layout, written by ``version``."""

    store = MagicMock()
    store.stored_version.return_value = version
    store.load.return_value = WorkspaceWindowState(
        geometry=b"where the window was",
        window_state=window_state,
    )
    return store


def state_controller_reading(window, store, legacy=()):
    """A controller whose layout says it knows ``legacy`` dead docks."""

    from manuskript.ui.legacy_layouts import LegacySurfaceLayout

    views = WorkspaceStateViews.for_window(window)
    controller = WorkspaceStateController(
        replace(
            views,
            legacy_surface_layouts_in=lambda blob: tuple(
                LegacySurfaceLayout(
                    surface_id=name.removeprefix("panel."),
                    floating=False,
                )
                for name in legacy
            ),
        ),
        store=store,
    )
    return controller


def test_an_arrangement_that_names_docks_we_no_longer_make_is_refused():
    """It cannot be cleaned, so it cannot be taken.

    Qt keeps the entry for a dock it restored but never found, and hands
    it back on every later save -- deliberately, so a panel whose plugin
    is temporarily away keeps its place. Applied once, those dead names
    would ride along for the life of the profile, and removing them
    afterwards does not work.
    """

    window = a_window()
    controller = state_controller_reading(
        window, a_saved_layout(), legacy=("panel.core.editor",),
    )

    controller.restore()

    assert not window.restoreState.called
    assert not controller.restoredLayout
    # The window's size and place are still true, and are not what this
    # refuses: only the arrangement of docks inside it.
    window.restoreGeometry.assert_called_once_with(b"where the window was")


def test_a_pre_membership_floating_surface_is_exposed_for_migration():
    from manuskript.ui.legacy_layouts import LegacySurfaceLayout

    window = a_window()
    views = WorkspaceStateViews.for_window(window)
    floating = LegacySurfaceLayout(
        surface_id="core.editor",
        floating=True,
        geometry=(120, 90, 640, 480),
    )
    controller = WorkspaceStateController(
        replace(
            views,
            legacy_surface_layouts_in=lambda _blob: (floating,),
        ),
        store=a_saved_layout(),
    )

    controller.restore()

    assert controller.legacy_floating_surfaces() == (floating,)


def test_explicit_surface_membership_wins_over_a_stale_legacy_blob():
    from manuskript.ui.legacy_layouts import LegacySurfaceLayout

    window = a_window()
    views = WorkspaceStateViews.for_window(window)
    floating = LegacySurfaceLayout("core.editor", True, (1, 2, 3, 4))
    store = a_saved_layout()
    store.load.return_value = WorkspaceWindowState(
        window_state=b"arrangement",
        surfaces=("core.editor",),
    )
    controller = WorkspaceStateController(
        replace(
            views,
            legacy_surface_layouts_in=lambda _blob: (floating,),
        ),
        store=store,
    )

    controller.restore()

    assert controller.legacy_floating_surfaces() == ()
    assert not controller.restoredLayout


def test_only_surface_aware_state_supplies_a_routed_panel_choice():
    window = a_window()
    current = a_saved_layout()
    current.load.return_value = WorkspaceWindowState(
        panels={"core.project-tree": False},
    )
    controller = state_controller_reading(window, current)
    controller.restore()
    assert controller.remembered_panel_visibility(
        "core.project-tree"
    ) is False

    old = a_saved_layout(version=WORKSPACE_STATE_VERSION - 1)
    old.load.return_value = WorkspaceWindowState(
        panels={"core.project-tree": True},
    )
    controller = state_controller_reading(window, old)
    controller.restore()
    assert controller.remembered_panel_visibility(
        "core.project-tree"
    ) is None


def test_an_arrangement_naming_only_docks_we_make_is_applied():
    """Whoever wrote it, and whatever version stamped it.

    Including version 1, which is what an installation upgrading from
    upstream arrives as. Refusing by version threw exactly those away,
    and they are the arrangements somebody actually made.
    """

    for version in (1, 3, WORKSPACE_STATE_VERSION):
        window = a_window()
        controller = state_controller_reading(
            window, a_saved_layout(version), legacy=(),
        )

        controller.restore()

        window.restoreState.assert_called_once_with(b"arrangement")
        assert controller.restoredLayout, version


def test_a_window_with_nothing_saved_places_its_own():
    """First launch, or a window id that has never been written."""

    window = a_window()
    controller = state_controller_reading(
        window, a_saved_layout(window_state=None),
    )

    controller.restore()

    assert not window.restoreState.called
    assert not controller.restoredLayout


def test_a_surface_that_remembers_something_is_asked_too():
    """Both owners. Asking only the panel host would drop it silently.

    Which is the one failure a reader cannot report: nothing is wrong
    until the next launch, and then only a setting they chose is gone.
    """

    from manuskript.panels import PanelState, WorkspaceSurfaceDescriptor
    from manuskript.ui.workspace_surfaces import WorkspaceSurfaceInstance

    remembered = WorkspaceSurfaceDescriptor(
        id="core.outline",
        title="Outline",
        state=(
            PanelState(
                key="core.outline",
                capture=lambda widget: widget.page,
                restore=lambda widget, value: setattr(
                    widget, "page", int(value),
                ),
            ),
        ),
    )
    outline = Notebook(page=4)
    window = a_window(surfaces={
        "core.outline": WorkspaceSurfaceInstance(
            descriptor=remembered, widget=outline,
        ),
    })
    store = MagicMock()
    controller = state_controller(window, store)

    controller.save()

    assert saved_state(controller).panel_state == {"core.outline": 4}

    store.load.return_value = WorkspaceWindowState(
        panel_state={"core.outline": 9},
    )
    controller.restore()

    assert outline.page == 9


# ------------------------------------- which surface, and which is focus


def a_surface_window(current="core.outline", descriptors=()):
    """A window whose surface host answers, as the real one does."""

    window = a_window(descriptors=descriptors)
    window.surfaceHost.current = lambda: current
    return window


def test_what_is_saved_is_what_the_surface_host_is_showing():
    """Not what last had focus.

    The window's record of semantic focus may name a tool panel; the
    surface host names the one thing this field is supposed to mean.
    """

    window = a_surface_window(descriptors=CORE_DESCRIPTORS)
    window._projectSurfaceActive = True
    window._activePanelId = "core.project-tree"
    controller = state_controller(window, MagicMock())

    controller.save()

    assert saved_state(controller).active_surface == "core.outline"


def test_a_layout_that_recorded_a_tool_panel_is_read_as_nothing():
    """Version 3 filed focus under this name, so it can say "project tree".

    Going there would mean nothing -- no navigator row stands for it --
    and the alternative to refusing it is a launch that tries.
    """

    window = a_window(descriptors=CORE_DESCRIPTORS)
    store = MagicMock()
    store.load.return_value = WorkspaceWindowState(
        active_panel="core.project-tree",
    )
    controller = state_controller(window, store)

    controller.restore()

    assert controller._activeSurface is None


def test_a_layout_that_recorded_a_surface_under_the_old_name_is_kept():
    """The migration this leaves room for: most of them did name one."""

    window = a_window(
        descriptors=CORE_DESCRIPTORS,
        surfaces={"core.editor": surface_instance("core.editor")},
    )
    store = MagicMock()
    store.load.return_value = WorkspaceWindowState(
        active_panel="core.editor",
    )
    controller = state_controller(window, store)

    controller.restore()

    assert controller._activeSurface == "core.editor"


def test_the_new_field_wins_over_the_one_it_replaced():
    window = a_window(
        descriptors=CORE_DESCRIPTORS,
        surfaces={"core.outline": surface_instance("core.outline")},
    )
    store = MagicMock()
    store.load.return_value = WorkspaceWindowState(
        active_surface="core.outline",
        active_panel="core.editor",
    )
    controller = state_controller(window, store)

    controller.restore()

    assert controller._activeSurface == "core.outline"


def test_a_surface_this_build_has_never_heard_of_is_read_as_nothing():
    """A plugin's surface, from a session where that plugin was there."""

    window = a_window(descriptors=CORE_DESCRIPTORS)
    store = MagicMock()
    store.load.return_value = WorkspaceWindowState(
        active_surface="plugin.gone.surface",
    )
    controller = state_controller(window, store)

    controller.restore()

    assert controller._activeSurface is None
