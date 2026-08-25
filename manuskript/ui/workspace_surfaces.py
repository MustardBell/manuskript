"""The places a writer goes, and which of them this workspace holds.

A workspace surface is not *defined* by being a dock. It is presented in one
today because independent, floatable panes are the required interaction, but
being docked remains where a presentation puts it rather than what it is.
That distinction is why this host remains separate from ``PanelHost``.

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

import logging

from dataclasses import dataclass
from typing import Any, Optional, Tuple

from manuskript.panels import PanelRegistryError, WorkspaceSurfaceDescriptor
from manuskript.panels.core import CORE_SURFACE_IDS, GENERAL


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkspaceBuildIntent:
    """Which surfaces a new workspace must contain before it is composed."""

    surface_ids: Tuple[str, ...] = CORE_SURFACE_IDS
    incoming: Tuple["WorkspaceSurfaceInstance", ...] = ()
    active_surface: Optional[str] = GENERAL
    #: A transfer wrapper presents the moved surface as the window, not as a
    #: full second copy of Manuskript's navigation shell.  Tool panels still
    #: exist as attachable window-local views, but none is routed into view
    #: until the reader explicitly asks for it.
    standalone_surface: bool = False

    def __post_init__(self):
        ids = tuple(self.surface_ids)
        incoming = tuple(self.incoming)
        incoming_ids = tuple(instance.id for instance in incoming)
        all_ids = ids + incoming_ids
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("A workspace build intent names a surface twice.")
        object.__setattr__(self, "surface_ids", ids)
        object.__setattr__(self, "incoming", incoming)

    @classmethod
    def for_transfer(cls, instance):
        return cls(
            surface_ids=(),
            incoming=(instance,),
            active_surface=instance.id,
            standalone_surface=True,
        )

    @classmethod
    def from_saved(cls, surface_ids, active_surface, registry):
        """Turn persisted membership into a safe construction intent.

        No ``surfaces`` key is a pre-membership workspace, whose migration
        is the canonical core set. Unknown ids are contributions no longer
        installed, not a reason to prevent Manuskript starting. If none of
        a recorded set remain available, the same canonical fallback keeps
        the window usable.
        """

        if surface_ids is None:
            return cls()
        valid = []
        for surface_id in surface_ids:
            surface_id = str(surface_id or "").strip()
            if not surface_id or surface_id in valid:
                continue
            # The primary intent is resolved before the first MainWindow
            # registers core factories. The current core vocabulary is still
            # authoritative at that point; contributed surfaces, by contrast,
            # have to be present in the shared registry to be restorable.
            if surface_id in CORE_SURFACE_IDS:
                valid.append(surface_id)
                continue
            try:
                descriptor = registry.descriptor(surface_id)
            except PanelRegistryError:
                LOGGER.warning(
                    "Ignoring unavailable workspace surface %s.",
                    surface_id,
                )
                continue
            if not isinstance(descriptor, WorkspaceSurfaceDescriptor):
                LOGGER.warning(
                    "Ignoring tool panel %s in surface membership.",
                    surface_id,
                )
                continue
            valid.append(surface_id)
        if not valid:
            return cls()
        active_surface = str(active_surface or "")
        if active_surface not in valid:
            active_surface = valid[0]
        return cls(
            surface_ids=tuple(valid),
            active_surface=active_surface,
            # A persisted one-surface peer is the transfer wrapper restored,
            # not a request to grow a new full navigation shell around it.
            standalone_surface=(len(valid) == 1),
        )


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

    ``presentation`` is how they are shown -- given rather than chosen here.
    It needs ``mount(instance)``,
    ``unmount(instance)`` and ``activate(instance)``.

    ``current`` records the last surface explicitly activated by navigation
    or focus.  A dock presentation may keep other surfaces visible beside it.
    """

    def __init__(self, registry, presentation, context=None):
        self.registry = registry
        self.presentation = presentation
        self.context = context
        self._instances = {}
        self._current = None
        # Window-local behaviour that follows a living surface between
        # workspaces.  A binding receives ``attach_surface(instance)`` after
        # the surface belongs to this host and ``detach_surface(instance)``
        # before it stops belonging here.  This is deliberately separate
        # from ``on_membership_changed``: rebuilding a navigator is an
        # after-the-fact notification, while a binding is part of the
        # ownership transaction and must be unwound if it cannot attach.
        self._bindings = []
        #: Told when this workspace gains or loses a surface, so whatever
        #: lists them can list them again. A callback rather than anything
        #: this host understands: which surfaces a workspace holds is its
        #: own business, and drawing a list of them is not.
        self.on_membership_changed = None

    # -- what this workspace holds ---------------------------------------

    def contains(self, surface_id):
        return surface_id in self._instances

    def instance(self, surface_id):
        return self._instances.get(surface_id)

    @property
    def instances(self):
        """Every surface this workspace holds, by id.

        A property, spelled as the panel host spells it: the two owners
        answer the same question and code that asks both should not have
        to know which one needs parentheses. Copied rather than handed
        out, so nobody rearranges a workspace by editing a dictionary.
        """

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
        try:
            self._attach_bindings(instance)
        except Exception:
            self._instances.pop(surface_id, None)
            self.presentation.unmount(instance)
            instance.host = None
            instance.container = None
            raise
        self._settle_current(surface_id)
        self._membership_changed()
        return instance

    def detach(self, surface_id):
        """Hand the living surface out. It is not rebuilt anywhere.

        What a surface is showing -- open documents, a selection, a scroll
        position -- travels with the widget, which is the whole reason a
        detach is not "close here and open there".
        """

        instance = self._instances.get(surface_id)
        if instance is None:
            return None
        self._detach_bindings(instance)
        self._instances.pop(surface_id, None)
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
        self._membership_changed()
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
        try:
            self._attach_bindings(instance)
        except Exception:
            self._instances.pop(surface_id, None)
            self.presentation.unmount(instance)
            instance.host = None
            instance.container = None
            raise
        self._settle_current(surface_id)
        self._membership_changed()
        return instance

    # -- bindings -------------------------------------------------------

    def add_binding(self, binding):
        """Attach one window-local behaviour to present and future surfaces.

        Replaying present membership is what lets composition install a
        binding after the canonical surfaces have been built.  Conversely, a
        sparse workspace can install the same binding before accepting a
        transferred surface.  Either order produces the same result.

        Registration is atomic.  If the binding cannot accept one of the
        surfaces already here, every earlier replay is undone and the binding
        is not retained.
        """

        if binding in self._bindings:
            return
        attached = []
        try:
            for instance in self._instances.values():
                binding.attach_surface(instance)
                attached.append(instance)
        except Exception:
            for instance in reversed(attached):
                binding.detach_surface(instance)
            raise
        self._bindings.append(binding)

    def remove_binding(self, binding):
        """Release a binding without changing workspace membership."""

        if binding not in self._bindings:
            return
        detached = []
        try:
            for instance in reversed(tuple(self._instances.values())):
                binding.detach_surface(instance)
                detached.append(instance)
        except Exception:
            for instance in reversed(detached):
                binding.attach_surface(instance)
            raise
        self._bindings.remove(binding)

    def _attach_bindings(self, instance):
        attached = []
        try:
            for binding in self._bindings:
                binding.attach_surface(instance)
                attached.append(binding)
        except Exception:
            for binding in reversed(attached):
                binding.detach_surface(instance)
            raise

    def _detach_bindings(self, instance):
        detached = []
        try:
            for binding in reversed(self._bindings):
                binding.detach_surface(instance)
                detached.append(binding)
        except Exception:
            # Ownership has not changed yet.  Put every behaviour already
            # released in this transaction back before reporting failure.
            for binding in reversed(detached):
                binding.attach_surface(instance)
            raise

    def _membership_changed(self):
        """Say that which surfaces this workspace holds has changed."""

        if callable(self.on_membership_changed):
            self.on_membership_changed()

    def activate(self, surface_id):
        """Reveal and focus this one. The navigator's whole job, in one call."""

        instance = self._instances.get(surface_id)
        if instance is None:
            return None
        self.presentation.activate(instance)
        self._current = surface_id
        return instance

    def deactivate(self):
        """Say that no surface is what the reader is looking at.

        Something else has the view: the window's central container also
        holds the opt-in developer page, which is instrumentation rather
        than a place the writer goes and so is not a surface.

        Without this, ``current`` had to answer with whichever surface was
        showing last, which makes it untrustworthy to every caller and not
        only to the route that took the view. The rule it restores:

            if ``current()`` names a surface, that surface is what the
            presentation is showing; if something else owns the view,
            ``current()`` is None.

        Nothing is told to hide. A surface that is not current is simply
        not the one on screen, which is as true of all of them as it is
        of the rest.
        """

        self._current = None

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

    def dispose(self):
        """Let go of every surface, in the workspace's teardown order.

        Qt owns the widget tree and would take these with the window; this
        exists so that it happens while the window is still whole, and in
        the order the workspace disposes everything else. A wrapper over a
        widget Qt has already deleted crashes the interpreter later, during
        a collection, with no stack that names this code.
        """

        # Nothing is told about the emptying: this workspace is going, and
        # whatever lists or binds its surfaces is going with it. Bindings are
        # disposed independently in the workspace's reverse construction
        # order; invoking them again here would call already-disposed
        # controllers while tearing down the native widget tree.
        self.on_membership_changed = None
        self._bindings.clear()
        for surface_id in tuple(self._instances):
            self.close(surface_id)
        self.presentation = None
        self.registry = None
        self.context = None
