"""A stable authority reference, with live revocation."""

import threading

from manuskript.plugins.authority import (
    CapabilityAuthority,
    CapabilityLease,
    SessionIdentity,
    session_of,
)


BOOK = SessionIdentity(project="/books/one.msk", generation=1)
REOPENED = SessionIdentity(project="/books/one.msk", generation=2)
OTHER = SessionIdentity(project="/books/two.msk", generation=1)


def authority_over(session=BOOK):
    """An authority whose current session is whatever we point it at."""

    holder = {"session": session}
    grants = CapabilityAuthority(session_source=lambda: holder["session"])
    return grants, holder


def test_a_lease_says_what_was_granted_and_over_which_project():
    grants, _ = authority_over()

    lease = grants.issue("vendor.provenance", "git.history")

    assert lease.plugin_id == "vendor.provenance"
    assert lease.capability == "git.history"
    assert lease.session == BOOK
    assert lease.grant_id


def test_a_live_lease_is_usable():
    grants, _ = authority_over()

    lease = grants.issue("vendor.provenance", "git.history")

    assert grants.allows(lease, capability="git.history")


def test_nothing_is_granted_when_no_project_is_open():
    grants, holder = authority_over()
    holder["session"] = None

    assert grants.issue("vendor.provenance", "git.history") is None


def test_a_withdrawn_grant_cannot_be_used_by_the_object_still_holding_it():
    """The holder keeps the Python object; it does not keep the authority."""

    grants, _ = authority_over()
    lease = grants.issue("vendor.provenance", "git.history")

    grants.withdraw(lease.grant_id)

    assert "withdrawn" in grants.refusal(lease)


def test_disabling_a_plugin_takes_all_of_its_authority():
    grants, _ = authority_over()
    history = grants.issue("vendor.provenance", "git.history")
    other = grants.issue("vendor.other", "git.history")

    grants.retire_plugin("vendor.provenance")

    assert "reloaded" in grants.refusal(history)
    assert not grants.refusal(other)


def test_closing_a_project_takes_the_grants_over_it():
    grants, holder = authority_over()
    lease = grants.issue("vendor.provenance", "git.history")

    holder["session"] = None

    assert "no longer open" in grants.refusal(lease)


def test_a_lease_never_follows_the_project_that_replaced_its_own():
    """The failure the live resolution had, stated as a rule.

    Re-resolving against whatever project is current did not stop a panel
    outliving its project from having authority. It gave it authority over
    the next one.
    """

    grants, holder = authority_over()
    lease = grants.issue("vendor.provenance", "git.history")

    holder["session"] = OTHER

    assert "no longer open" in grants.refusal(lease)


def test_reopening_the_same_project_is_a_new_authority_domain():
    """Path alone cannot tell a reopening from the original opening.

    Closing a project and opening the same file again is a new session, and
    a lease granted over the first must not silently carry into the second.
    """

    grants, holder = authority_over()
    lease = grants.issue("vendor.provenance", "git.history")

    holder["session"] = REOPENED

    assert "no longer open" in grants.refusal(lease)


def test_a_lease_does_not_cover_a_capability_it_was_not_granted():
    grants, _ = authority_over()

    lease = grants.issue("vendor.provenance", "git.history")

    assert "does not cover" in grants.refusal(lease, capability="outline.write")


def test_a_lease_claiming_someone_elses_grant_is_refused():
    """Holding the shape of a grant is not holding the grant.

    The authority remembers what it issued, so a lease that merely carries a
    known id while naming a different plugin is not the lease that id
    belongs to.
    """

    grants, _ = authority_over()
    real = grants.issue("vendor.provenance", "git.history")

    forged = CapabilityLease(
        plugin_id="vendor.impostor",
        plugin_epoch=1,
        session=BOOK,
        capability="git.history",
        grant_id=real.grant_id,
    )

    assert grants.refusal(forged)
    assert not grants.refusal(real)


def test_no_grant_at_all_is_refused_plainly():
    grants, _ = authority_over()

    assert "No capability was granted." in grants.refusal(None)


def test_a_plugin_that_comes_back_gets_new_authority_not_the_old():
    grants, _ = authority_over()
    first = grants.issue("vendor.provenance", "git.history")
    grants.retire_plugin("vendor.provenance")

    second = grants.issue("vendor.provenance", "git.history")

    assert first.grant_id != second.grant_id
    assert grants.refusal(first)
    assert not grants.refusal(second)


def test_asking_and_withdrawing_at_once_does_not_corrupt_the_register():
    """Workers ask from their own threads while the interface withdraws.

    An ordinary dict is not a synchronization primitive, whatever CPython
    happens to do today, and this is exactly the shape the search creates:
    a job on a worker thread asking about its lease on every file it reads.
    """

    grants, _ = authority_over()
    leases = [
        grants.issue("vendor.provenance", "git.history") for _ in range(200)
    ]
    answers = []

    def ask():
        for lease in leases:
            answers.append(grants.refusal(lease))

    def take():
        for lease in leases:
            grants.withdraw(lease.grant_id)

    readers = [threading.Thread(target=ask) for _ in range(4)]
    writer = threading.Thread(target=take)
    for thread in readers:
        thread.start()
    writer.start()
    for thread in readers + [writer]:
        thread.join()

    assert len(answers) == 800
    # Every lease is gone by the end, whatever order the threads ran in.
    assert all(grants.refusal(lease) for lease in leases)


def test_the_session_of_a_closed_project_is_nothing():
    class Session:
        is_open = False
        path = "/books/one.msk"
        generation = 1

    class Manager:
        session = Session()

    assert session_of(Manager()) is None


def test_the_session_of_an_open_project_names_the_opening():
    class Session:
        is_open = True
        path = "/books/one.msk"
        generation = 3

    class Manager:
        session = Session()

    assert session_of(Manager()) == SessionIdentity(
        project="/books/one.msk", generation=3
    )
