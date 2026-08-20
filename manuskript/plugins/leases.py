"""Who may ask for what, and for how long.

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

So a lease says what was granted, to whom, and over which project
generation, and carries an opaque id. The host keeps a register of which ids
are still live. A call asks whether *this lease* is still good -- not what
the world happens to look like now -- and the host can revoke it at any
moment.

Revocation happens at lifecycle boundaries rather than through a permission
system nobody asked for: disabling or reloading a plugin revokes its leases,
closing or replacing a project revokes the leases over that generation. A
plugin that comes back gets new leases rather than reanimating old ones.

Availability is deliberately not part of this. A reader switching Git
revisions off has not withdrawn permission to ask about Git history, and
treating it as revocation would mean manufacturing a new authority object
when they switch it back on. "Authorized, but currently unavailable" and
"no longer allowed to ask" are different sentences, and the second one is
not the host's to say on a preference's behalf.
"""

import itertools

from dataclasses import dataclass


#: The lease is gone: the plugin was disabled or reloaded, the project was
#: closed or replaced, or the grant was withdrawn.
CAPABILITY_REVOKED = "plugin.capability_revoked"


@dataclass(frozen=True)
class CapabilityLease:
    """What was granted, to whom, over which project -- and its name."""

    plugin_id: str
    capability: str
    project_generation: int
    grant_id: str

    def __str__(self):
        return "{} for {} over project {}".format(
            self.capability, self.plugin_id, self.project_generation
        )


class GrantRegistry:
    """Which leases are still live. The host's answer, not the holder's."""

    def __init__(self):
        self._active = {}
        self._ids = itertools.count(1)

    def issue(self, plugin_id, capability, project_generation):
        lease = CapabilityLease(
            plugin_id=str(plugin_id),
            capability=str(capability),
            project_generation=int(project_generation),
            grant_id="grant-{}".format(next(self._ids)),
        )
        self._active[lease.grant_id] = lease
        return lease

    def revoke(self, grant_id):
        self._active.pop(str(grant_id), None)

    def revoke_plugin(self, plugin_id):
        """A plugin disabled or reloaded keeps none of its old authority."""

        for lease in tuple(self._active.values()):
            if lease.plugin_id == str(plugin_id):
                self.revoke(lease.grant_id)

    def revoke_generation(self, project_generation):
        """A project closed or replaced takes its grants with it."""

        for lease in tuple(self._active.values()):
            if lease.project_generation == int(project_generation):
                self.revoke(lease.grant_id)

    def revoke_capability(self, capability):
        """A permission withdrawn, wherever it was held."""

        for lease in tuple(self._active.values()):
            if lease.capability == str(capability):
                self.revoke(lease.grant_id)

    def refusal(self, lease, capability=None, project_generation=None):
        """Why this lease cannot be used now, or empty if it can.

        Everything asked here is about the lease. Nothing consults the
        current manifest or the currently open project, because a holder's
        authority is not supposed to follow the world around.
        """

        if lease is None:
            return "No capability was granted."
        held = self._active.get(lease.grant_id)
        if held is None or held != lease:
            return "This grant has been withdrawn."
        if capability is not None and lease.capability != str(capability):
            return "This grant does not cover {}.".format(capability)
        if (
            project_generation is not None
            and lease.project_generation != int(project_generation)
        ):
            return (
                "This grant belongs to a project that is no longer open."
            )
        return ""

    def allows(self, lease, **checks):
        return not self.refusal(lease, **checks)
