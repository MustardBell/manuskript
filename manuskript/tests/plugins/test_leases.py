"""A stable authority reference, with live revocation."""

from manuskript.plugins.leases import CapabilityLease, GrantRegistry


def test_a_lease_says_what_was_granted_and_over_which_project():
    grants = GrantRegistry()

    lease = grants.issue("vendor.provenance", "git.history", 3)

    assert lease.plugin_id == "vendor.provenance"
    assert lease.capability == "git.history"
    assert lease.project_generation == 3
    assert lease.grant_id


def test_a_live_lease_is_usable():
    grants = GrantRegistry()

    lease = grants.issue("vendor.provenance", "git.history", 1)

    assert grants.allows(lease, capability="git.history", project_generation=1)


def test_a_withdrawn_grant_cannot_be_used_by_the_object_still_holding_it():
    """The holder keeps the Python object; it does not keep the authority."""

    grants = GrantRegistry()
    lease = grants.issue("vendor.provenance", "git.history", 1)

    grants.revoke(lease.grant_id)

    assert "withdrawn" in grants.refusal(lease)


def test_disabling_a_plugin_takes_all_of_its_authority():
    grants = GrantRegistry()
    history = grants.issue("vendor.provenance", "git.history", 1)
    other = grants.issue("vendor.other", "git.history", 1)

    grants.revoke_plugin("vendor.provenance")

    assert grants.refusal(history)
    assert not grants.refusal(other)


def test_closing_a_project_takes_the_grants_over_it():
    grants = GrantRegistry()
    old = grants.issue("vendor.provenance", "git.history", 1)
    new = grants.issue("vendor.provenance", "git.history", 2)

    grants.revoke_generation(1)

    assert grants.refusal(old)
    assert not grants.refusal(new)


def test_a_lease_never_follows_the_project_that_replaced_its_own():
    """The failure the live resolution had, stated as a rule.

    Re-resolving against whatever project is current did not stop a panel
    outliving its project from having authority. It gave it authority over
    the next one.
    """

    grants = GrantRegistry()
    lease = grants.issue("vendor.provenance", "git.history", 1)

    assert "no longer open" in grants.refusal(lease, project_generation=2)


def test_a_lease_does_not_cover_a_capability_it_was_not_granted():
    grants = GrantRegistry()

    lease = grants.issue("vendor.provenance", "git.history", 1)

    assert "does not cover" in grants.refusal(lease, capability="outline.write")


def test_a_lease_claiming_someone_elses_grant_is_refused():
    """Holding the shape of a grant is not holding the grant.

    The register remembers what it issued, so a lease that merely carries a
    known id while naming a different plugin is not the lease that id
    belongs to.
    """

    grants = GrantRegistry()
    real = grants.issue("vendor.provenance", "git.history", 1)

    forged = CapabilityLease(
        plugin_id="vendor.impostor",
        capability="git.history",
        project_generation=1,
        grant_id=real.grant_id,
    )

    assert grants.refusal(forged)
    assert not grants.refusal(real)


def test_no_grant_at_all_is_refused_plainly():
    assert "No capability was granted." in GrantRegistry().refusal(None)


def test_a_plugin_that_comes_back_gets_new_authority_not_the_old():
    grants = GrantRegistry()
    first = grants.issue("vendor.provenance", "git.history", 1)
    grants.revoke_plugin("vendor.provenance")

    second = grants.issue("vendor.provenance", "git.history", 1)

    assert first.grant_id != second.grant_id
    assert grants.refusal(first)
    assert not grants.refusal(second)
