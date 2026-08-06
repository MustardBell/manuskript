"""A panel says what it remembers; the controller that saves only asks.

The list of panels with state of their own used to live in
WorkspaceStateController, together with the widget methods to call and the
widget to call them on. So the central controller named one panel's
internals, and a new panel with an arrangement worth keeping meant editing
it -- the panel could not answer for itself.
"""

import inspect

from unittest.mock import MagicMock

from manuskript.panels import (
    DOCK,
    PROJECT,
    SPLITTER_SLOT,
    PanelDescriptor,
    PanelState,
    SplitterSlot,
)
from manuskript.panels.core import (
    METADATA,
    METADATA_REVISIONS_STATE,
    core_panel_descriptors,
)
from manuskript.services.workspace_state import WorkspaceWindowState
from manuskript.ui import workspace_state_controller
from manuskript.ui.panels.host import PanelInstance
from manuskript.ui.workspace_state_controller import (
    WorkspaceStateController,
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
NOTEBOOK_PANEL = PanelDescriptor(
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

    def instance(self, panel_id):
        return self._instances.get(panel_id)

    @property
    def instances(self):
        return dict(self._instances)

    def set_visible(self, panel_id, visible):
        self.shown[panel_id] = visible


class Registry:
    """Enough of a panel registry to say where panels sit."""

    def __init__(self, descriptors):
        self._descriptors = tuple(descriptors)

    def descriptors(self, placement=None):
        return tuple(
            descriptor
            for descriptor in self._descriptors
            if placement is None or descriptor.placement == placement
        )


def a_window(instances=(), descriptors=()):
    window = MagicMock()
    window.panelHost = Host(dict(instances))
    window.panelRegistry = Registry(descriptors)
    return window


def saved_state(controller):
    """The state a save handed to the store."""
    return controller.store.save.call_args[0][0]


def test_a_panel_the_controller_never_heard_of_keeps_its_state():
    """The whole point. Nothing in the controller mentions this panel, and
    its page survives a save and a restore.
    """
    notebook = Notebook(page=3)
    instance = PanelInstance(descriptor=NOTEBOOK_PANEL, widget=notebook)
    window = a_window(instances={NOTEBOOK: instance})
    store = MagicMock()
    controller = WorkspaceStateController(window, store=store)

    controller.save()

    assert saved_state(controller).panel_state == {NOTEBOOK: 3}

    store.load.return_value = WorkspaceWindowState(
        panel_state={NOTEBOOK: 7},
    )
    controller.restore()

    assert notebook.page == 7


def test_a_panel_that_remembers_nothing_files_nothing():
    plain = PanelDescriptor(id="plugin.notes.plain", title="Plain")
    window = a_window(
        instances={
            plain.id: PanelInstance(descriptor=plain, widget=MagicMock()),
        }
    )
    controller = WorkspaceStateController(window, store=MagicMock())

    controller.save()

    assert saved_state(controller).panel_state == {}


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
    controller = WorkspaceStateController(window, store=store)

    controller.restore()

    assert notebook.page == 2


def test_the_splitters_remembered_are_the_ones_panels_sit_in():
    """A hardcoded pair of names meant a panel in a third splitter had its
    sizes forgotten until somebody came and added it.
    """
    descriptors = (
        PanelDescriptor(
            id="core.first", title="First", placement=SPLITTER_SLOT,
            slot=SplitterSlot("splitterOne", 0),
        ),
        PanelDescriptor(
            id="core.second", title="Second", placement=SPLITTER_SLOT,
            slot=SplitterSlot("splitterTwo", 1),
        ),
        # Same splitter as the first: named once, not twice.
        PanelDescriptor(
            id="core.third", title="Third", placement=SPLITTER_SLOT,
            slot=SplitterSlot("splitterOne", 2),
        ),
        # A dock sits in no splitter.
        PanelDescriptor(id="core.docked", title="Docked"),
    )
    window = a_window(descriptors=descriptors)
    controller = WorkspaceStateController(window, store=MagicMock())

    controller.save()

    assert sorted(saved_state(controller).splitters) == [
        "splitterOne",
        "splitterTwo",
    ]


def test_the_splitter_holding_the_book_summary_is_among_them():
    """It was not, before: the two names listed by hand were the two in the
    redaction tab, and the plots tab's splitter was nobody's.
    """
    descriptors = core_panel_descriptors(
        plots_group=object(), redaction_group=object(),
    )
    window = a_window(descriptors=descriptors)
    controller = WorkspaceStateController(window, store=MagicMock())

    controller.save()

    assert sorted(saved_state(controller).splitters) == [
        "splitterPlot",
        "splitterRedacH",
        "splitterRedacV",
    ]


def test_the_metadata_panel_says_what_it_remembers():
    """Under the keys it has always been stored under: a saved layout
    outlives this refactoring.
    """
    metadata = next(
        descriptor
        for descriptor in core_panel_descriptors(object(), object())
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
