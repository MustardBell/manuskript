"""Who may ask for what, and whether they still may.

A capability handed to a plugin used to be resolved afresh on every call:
what does the manifest say now, which project is open now. That conflates
five different events into one answer -- the plugin was reloaded, the
capability was revoked, the project changed, the record went missing, the
wrong runtime was consulted -- and it has a worse property than the
ambiguity. Re-resolving against whatever project is current means a panel
that outlives its project does not lose authority; it silently acquires
authority over the next one.

The rule here is the user's: **capture the grant's scope and identity, never
capture its validity.** Or shorter, a stable authority reference with live
revocation.

So a lease says what was granted, to whom, and over which opening of which
project, and carries an opaque id. This module owns the answer to whether
that lease is still good. A call asks about *this lease* -- not what the
world happens to look like now -- and authority can be withdrawn at any
moment without the holder knowing in advance.

Two independent facts end a lease, and they are deliberately not folded into
one lifecycle event, because they really are two:

* the plugin instance stopped being the instance that was granted -- it was
  disabled, or reloaded;
* the project session stopped being the one it was granted over -- it was
  closed, or replaced, or closed and reopened.

What is singular is the *policy owner*, not the events. Both are compared
rather than bookkept: a plugin carries an epoch that reloading advances, and
a project opening carries a generation that opening advances. Revoking every
lease a plugin holds is one increment rather than a sweep of a table.

Availability is deliberately not part of this. A reader switching Git
revisions off has not withdrawn permission to ask about Git history, and
treating it as revocation would mean manufacturing a new authority object
when they switch it back on. "Authorized, but currently unavailable" and
"no longer allowed to ask" are different sentences, and the second one is
not the host's to say on a preference's behalf.
"""

import itertools
import threading

from dataclasses import dataclass


#: The lease is gone: the plugin was disabled or reloaded, the project was
#: closed or replaced, or the grant was withdrawn.
CAPABILITY_REVOKED = "plugin.capability_revoked"


@dataclass(frozen=True)
class SessionIdentity:
    """One opening of one project.

    Both halves are load-bearing. A path alone cannot tell a reopening from
    the original, and a generation alone means an application holding two
    projects would treat one project's third opening as the other's.
    """

    project: str
    generation: int

    def __str__(self):
        return "{} (opening {})".format(self.project, self.generation)


def session_of(manager):
    """The identity of whatever project a manager currently holds open.

    One function, used both to stamp a lease and to read what is open now,
    because two spellings of "which project is this" that drift apart would
    make every lease refuse or every lease pass.
    """

    session = getattr(manager, "session", None)
    if session is None or not getattr(session, "is_open", False):
        return None
    return SessionIdentity(
        project=str(getattr(session, "path", "") or ""),
        generation=int(getattr(session, "generation", 0)),
    )


@dataclass(frozen=True)
class CapabilityLease:
    """What was granted, to whom, over which project -- and its name."""

    plugin_id: str
    plugin_epoch: int
    session: SessionIdentity
    capability: str
    grant_id: str

    def __str__(self):
        return "{} for {} over {}".format(
            self.capability, self.plugin_id, self.session
        )


class CapabilityAuthority:
    """The one owner of issuance and validity.

    Deliberately not assembled inside whatever builds a capability. A
    builder's job is to construct services; deciding who may hold them is a
    different job, and a builder that decides it privately becomes a second
    policy nobody can see.

    ``session_source`` reads which project is open *now*. That is the only
    live thing here, and it is live on purpose: the world moves, and a
    lease's scope must not move with it. Everything the lease itself says
    was fixed when it was issued.

    Every method takes the lock. Search workers ask about their lease from
    worker threads while the interface withdraws grants from another, and
    an ordinary dict is not a synchronization primitive whatever CPython
    happens to do today.
    """

    def __init__(self, session_source=None):
        self._lock = threading.RLock()
        self._session_source = session_source
        self._epochs = {}
        self._issued = {}
        self._withdrawn = set()
        self._ids = itertools.count(1)

    # -- what the world looks like now -----------------------------------

    def session(self):
        """The project session open now, or None."""

        with self._lock:
            source = self._session_source
        return source() if source is not None else None

    def epoch(self, plugin_id):
        """Which incarnation of this plugin is current."""

        with self._lock:
            return self._epochs.get(str(plugin_id), 1)

    # -- granting and taking away ----------------------------------------

    def issue(self, plugin_id, capability, session=None):
        """A lease over the open project, or None when none is open."""

        target = session if session is not None else self.session()
        if target is None:
            return None
        with self._lock:
            lease = CapabilityLease(
                plugin_id=str(plugin_id),
                plugin_epoch=self._epochs.get(str(plugin_id), 1),
                session=target,
                capability=str(capability),
                grant_id="grant-{}".format(next(self._ids)),
            )
            self._issued[lease.grant_id] = lease
            return lease

    def retire_plugin(self, plugin_id):
        """Disabled or reloaded: every lease it holds stops working.

        One increment rather than a sweep, and a plugin that comes back gets
        leases at the new epoch rather than reanimating the old ones.
        """

        with self._lock:
            plugin_id = str(plugin_id)
            self._epochs[plugin_id] = self._epochs.get(plugin_id, 1) + 1
            self._forget(lambda lease: lease.plugin_id == plugin_id)

    def withdraw(self, grant_id):
        """One grant, taken back by name."""

        with self._lock:
            self._withdrawn.add(str(grant_id))
            self._issued.pop(str(grant_id), None)

    def forget_stale(self):
        """Drop records of leases nothing can use, at a quiet moment."""

        with self._lock:
            self._forget(lambda lease: bool(self._refusal(lease)))

    def _forget(self, matches):
        for lease in tuple(self._issued.values()):
            if matches(lease):
                self._issued.pop(lease.grant_id, None)

    # -- whether a lease may still be used --------------------------------

    def refusal(self, lease, capability=None):
        """Why this lease cannot be used now, or empty if it can."""

        with self._lock:
            return self._refusal(lease, capability)

    def _refusal(self, lease, capability=None):
        if lease is None:
            return "No capability was granted."
        if lease.grant_id in self._withdrawn:
            return "This grant has been withdrawn."
        if capability is not None and lease.capability != str(capability):
            return "This grant does not cover {}.".format(capability)
        # The two comparisons come before the identity check so that a lease
        # refused for a real reason is told that reason. Forgetting a stale
        # record is tidying, and tidying must not turn "your project closed"
        # into the generic answer.
        if lease.plugin_epoch != self._epochs.get(lease.plugin_id, 1):
            return "This grant belongs to a plugin that has been reloaded."
        current = self.session()
        if current is None or current != lease.session:
            return "This grant belongs to a project that is no longer open."
        held = self._issued.get(lease.grant_id)
        if held is None or held != lease:
            # Holding the shape of a grant is not holding the grant. The
            # authority remembers what it issued, so a lease carrying a known
            # id while naming a different plugin is not that grant.
            return "This grant has been withdrawn."
        return ""

    def allows(self, lease, **checks):
        return not self.refusal(lease, **checks)
