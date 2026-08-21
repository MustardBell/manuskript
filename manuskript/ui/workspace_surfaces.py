"""The places a writer goes, and which of them this workspace holds.

A workspace surface is not a dock. It may be *presented* in one -- the user's
rule allows that explicitly, and it is what happens today -- but being docked
is where a presentation puts it, not what it is. That distinction is why this
host exists separately from ``PanelHost``: if surfaces stayed owned by the
panel host, they would keep tool-panel visibility, floating and toggle
semantics for no better reason than their presentation being a QDockWidget,
and the split into two descriptor types would be cosmetic.

Deliberately not called a central host. Centrality is one presentation, and a
plausible one, but the requirement it was meant to serve is that a reader
sees a window like upstream's -- not that Manuskript is built the way
upstream is. Which presentation reaches that is measured rather than assumed.

**Surfaces are windows first.** The entity browser and the general form were
written narrow-safe because a dock 230 pixels wide was the space they were
given, and narrow-safe is worth keeping -- but as the degraded case, not the
target. A host that hands a surface a window's worth of room is what makes
that ordering possible.

Construction is a method and never a property. ``open`` may build; nothing
that merely reads may. A getter that constructs a QWidget is a thread
affinity hazard in a form that advertises nothing, and it makes "which
surfaces does this workspace have" a consequence of what happened to be
touched rather than something the workspace states.
"""

from dataclasses import dataclass
from typing import Any, Optional

from manuskript.panels import WorkspaceSurfaceDescriptor


@dataclass
class WorkspaceSurfaceInstance:
    """One living surface in one workspace.

    More than an id and a widget: a transfer between workspaces has to carry
    the descriptor and whatever the surface remembers, and exactly one host
    owns it at a time. Detaching hands this object over; attaching adopts it
    without rebuilding, so what the surface was showing survives the move.
    """

    descriptor: WorkspaceSurfaceDescriptor
    widget: Any
    host: Optional["WorkspaceSurfaceHost"] = None
    #: What the presentation wrapped it in, when it wrapped it in anything.
    container: Optional[Any] = None

    @property
    def id(self):
        return self.descriptor.id


class WorkspaceSurfaceError(RuntimeError):
    """A surface could not be opened, attached or found."""


class WorkspaceSurfaceHost:
    """Which surfaces this workspace holds, and which one is showing.

    ``presentation`` is how they are shown -- given rather than chosen here,
    because whether that is a central stack or docks is a question for the
    parity oracle rather than for this class. It needs ``mount(instance)``,
    ``unmount(instance)`` and ``activate(instance)``.

    An earlier port also declared ``hide``, which nothing called: a mounted
    surface is not individually shown or hidden, because one of them is
    current and the rest are simply not the current one.
    """

    def __init__(self, registry, presentation, context=None):
        self.registry = registry
        self.presentation = presentation
        self.context = context
        self._instances = {}
        self._current = None

    # -- what this workspace holds ---------------------------------------

    def contains(self, surface_id):
        return surface_id in self._instances

    def instance(self, surface_id):
        return self._instances.get(surface_id)

    def instances(self):
        return dict(self._instances)

    def current(self):
        """The surface a reader is looking at, or None."""

        return self._current

    # -- lifecycle -------------------------------------------------------

    def open(self, surface_id, context=None):
        """Build this surface here, or answer the one already here.

        The only method that may construct. Called when a workspace says it
        wants a surface -- at project open, from a navigator row, or because
        a reader asked for one -- never as a side effect of reading.
        """

        existing = self._instances.get(surface_id)
        if existing is not None:
            return existing
        descriptor = self.registry.descriptor(surface_id)
        if not isinstance(descriptor, WorkspaceSurfaceDescriptor):
            # Asked of the type. Accepting whatever had a widget_factory
            # would let a tool panel be opened here, which is kind inferred
            # from a shared field -- the habit the two descriptors exist to
            # end, reappearing inside the thing that enforces them.
            raise WorkspaceSurfaceError(
                "{} is a tool panel; the panel host owns those."
                .format(surface_id)
            )
        if descriptor.widget_factory is None:
            raise WorkspaceSurfaceError(
                "Surface {} has no factory, so this workspace cannot build "
                "one.".format(surface_id)
            )
        widget = descriptor.widget_factory(context or self.context, None)
        instance = WorkspaceSurfaceInstance(
            descriptor=descriptor, widget=widget, host=self
        )
        instance.container = self.presentation.mount(instance)
        self._instances[surface_id] = instance
        self._settle_current(surface_id)
        return instance

    def detach(self, surface_id):
        """Hand the living surface out. It is not rebuilt anywhere.

        What a surface is showing -- open documents, a selection, a scroll
        position -- travels with the widget, which is the whole reason a
        detach is not "close here and open there".
        """

        instance = self._instances.pop(surface_id, None)
        if instance is None:
            return None
        self.presentation.unmount(instance)
        instance.host = None
        instance.container = None
        if self._current == surface_id:
            # Whatever becomes current has to be shown, not merely recorded.
            # Naming a new current without telling the presentation left the
            # host's answer and the reader's view disagreeing, and the fake
            # in the tests could not see the difference.
            self._current = None
            remaining = next(iter(self._instances), None)
            if remaining is not None:
                self.activate(remaining)
        return instance

    def attach(self, instance):
        """Adopt a surface another workspace let go of. Never builds."""

        if instance is None:
            return None
        if instance.host is not None:
            # Still owned elsewhere. Adopting it would put one living
            # surface in two workspaces while it named only one owner --
            # exactly the invariant this class exists to hold, broken by
            # the class itself. Detach it from where it is first.
            raise WorkspaceSurfaceError(
                "{} still belongs to another workspace; detach it there "
                "first.".format(instance.id)
            )
        surface_id = instance.id
        if surface_id in self._instances:
            raise WorkspaceSurfaceError(
                "This workspace already holds {}.".format(surface_id)
            )
        instance.host = self
        instance.container = self.presentation.mount(instance)
        self._instances[surface_id] = instance
        self._settle_current(surface_id)
        return instance

    def activate(self, surface_id):
        """Show this one. The navigator's whole job, in one call."""

        instance = self._instances.get(surface_id)
        if instance is None:
            return None
        self.presentation.activate(instance)
        self._current = surface_id
        return instance

    def _settle_current(self, surface_id):
        """Make this one current if nothing is, showing it as well.

        One operation owns both halves. Recording a current surface without
        telling the presentation is how the host's answer and what a reader
        sees came apart, and it is not the sort of thing a fake notices.

        A fallback, not a policy: which surface a fresh workspace starts on
        is composition's to state, not an accident of which id was passed
        to ``open`` first.
        """

        if self._current is None:
            self.activate(surface_id)

    def close(self, surface_id):
        """Put a surface away and let it go."""

        instance = self.detach(surface_id)
        if instance is not None and instance.widget is not None:
            instance.widget.setParent(None)
        return instance is not None
