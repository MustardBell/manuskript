"""Revisions default to Git, and say so plainly when Git cannot work.

Three situations have to look different: Git usable, Git installed but the
project is not in a repository, and Git missing entirely. In the last case
turning revisions off and choosing the legacy backend must stay reachable,
or the writer is trapped with a setting they cannot change.
"""

from manuskript.domain.revisions import RevisionBackendKind
from manuskript.services.git_revisions import (
    GitAvailability,
    inspect_git_availability,
)


GIT = RevisionBackendKind.GIT.value
INTERNAL = RevisionBackendKind.INTERNAL.value


class StubRunner:
    """A Git that is not installed."""

    available = False

    def execute(self, *args, **kwargs):
        raise AssertionError("Git must not be run when unavailable")


def settings_window(window, availability):
    dialog = window.workspaceDialogs.show_settings()
    dialog.gitAvailability = lambda: availability
    return dialog


# The revisions page lives in a stack that is not current during tests, so
# isVisibleTo() would report everything as hidden. isHidden() reflects what
# updateRevisionBackendUi actually set.
def select(dialog, backend, keep=True):
    dialog.chkRevisionsKeep.setChecked(keep)
    dialog.cmbRevisionBackend.setCurrentIndex(
        dialog.cmbRevisionBackend.findData(backend)
    )
    dialog.updateRevisionBackendUi()


# --------------------------------------------------------------- defaults

def test_git_is_the_shipped_default_and_listed_first(MWEmptyProject):
    from manuskript import settings as defaults

    assert defaults.revisions["backend"] == GIT

    dialog = settings_window(
        MWEmptyProject,
        GitAvailability(git_installed=True, repository_root="/repo"),
    )
    try:
        assert dialog.cmbRevisionBackend.itemData(0) == GIT
        assert dialog.cmbRevisionBackend.itemData(1) == INTERNAL
    finally:
        dialog.close()


# ------------------------------------------------------- git usable

def test_a_usable_git_offers_history_without_warnings(MWEmptyProject):
    dialog = settings_window(
        MWEmptyProject,
        GitAvailability(git_installed=True, repository_root="/repo"),
    )
    try:
        select(dialog, GIT)

        assert dialog.grpGitRevisionOptions.isEnabled()
        assert dialog.btnManageGitRevisions.isEnabled()
        assert dialog.lblRevisionStatus.isHidden()
        assert dialog.btnInitGitRepository.isHidden()
    finally:
        dialog.close()


# ------------------------------------------- git installed, no repository

def test_a_project_outside_a_repository_is_warned_and_offered_init(
        MWEmptyProject):
    dialog = settings_window(
        MWEmptyProject,
        GitAvailability(git_installed=True, repository_root=None),
    )
    try:
        select(dialog, GIT)

        assert not dialog.lblRevisionStatus.isHidden()
        message = dialog.lblRevisionStatus.text()
        assert "not inside a Git repository" in message
        assert "no history is being recorded" in message
        # The fix is offered rather than only described.
        assert not dialog.btnInitGitRepository.isHidden()
        # Nothing to open yet.
        assert not dialog.btnManageGitRevisions.isEnabled()
        # But the options are not falsely greyed out: Git does work here.
        assert dialog.grpGitRevisionOptions.isEnabled()
    finally:
        dialog.close()


# ----------------------------------------------------- git not installed

def test_without_git_only_turning_off_and_legacy_stay_available(
        MWEmptyProject):
    dialog = settings_window(
        MWEmptyProject,
        GitAvailability(git_installed=False),
    )
    try:
        select(dialog, GIT)

        # The two escapes the writer needs.
        assert dialog.chkRevisionsKeep.isEnabled()
        assert dialog.cmbRevisionBackend.isEnabled()
        # Everything Git cannot deliver is inert.
        assert not dialog.grpGitRevisionOptions.isEnabled()
        assert not dialog.btnManageGitRevisions.isEnabled()
        assert dialog.btnInitGitRepository.isHidden()
        assert "Git is not installed" in dialog.lblRevisionStatus.text()
    finally:
        dialog.close()


def test_git_stays_selectable_without_git_installed(MWEmptyProject):
    """Choosing Git must remain possible; it simply records nothing."""
    dialog = settings_window(
        MWEmptyProject,
        GitAvailability(git_installed=False),
    )
    try:
        select(dialog, GIT)

        assert dialog.cmbRevisionBackend.currentData() == GIT
        assert dialog.settings.revisions["backend"] == GIT
    finally:
        dialog.close()


def test_switching_to_legacy_without_git_restores_its_options(
        MWEmptyProject):
    dialog = settings_window(
        MWEmptyProject,
        GitAvailability(git_installed=False),
    )
    try:
        select(dialog, INTERNAL)

        assert dialog.chkRevisionRemove.isEnabled()
        assert not dialog.label_revisionDeprecation.isHidden()
        assert dialog.lblRevisionStatus.isHidden()
    finally:
        dialog.close()


def test_turning_revisions_off_disables_the_backend_choice(MWEmptyProject):
    dialog = settings_window(
        MWEmptyProject,
        GitAvailability(git_installed=True, repository_root="/repo"),
    )
    try:
        select(dialog, GIT, keep=False)

        assert dialog.chkRevisionsKeep.isEnabled()
        assert not dialog.cmbRevisionBackend.isEnabled()
        assert not dialog.btnManageGitRevisions.isEnabled()
    finally:
        dialog.close()


# ------------------------------------------------------------- the probe

def test_the_probe_reports_a_missing_git_without_running_it():
    availability = inspect_git_availability(
        "/nowhere/story.msk", runner=StubRunner()
    )

    assert not availability.git_installed
    assert not availability.usable
    assert not availability.needs_repository


def test_the_probe_separates_a_missing_repository_from_a_missing_git(
        tmp_path):
    project = tmp_path / "story.msk"
    project.write_text("1", encoding="utf-8")

    availability = inspect_git_availability(str(project))

    # tmp_path is not a worktree, but Git itself is present here.
    assert availability.git_installed
    assert availability.needs_repository
    assert not availability.usable


def test_the_probe_finds_a_repository_that_contains_the_project():
    import os

    from manuskript.functions import appPath

    availability = inspect_git_availability(
        os.path.join(appPath("sample-projects"), "book-of-acts.msk")
    )

    assert availability.git_installed
    assert availability.usable
    assert availability.repository_root


def test_no_git_is_invoked_when_auto_commit_is_off():
    """Choosing Git without Git installed must stay silent, not error.

    Auto-commit is the only thing that reaches for Git on save, and it is
    off by default, so a project set to Git on a machine without Git simply
    records nothing instead of failing on every save.
    """
    from manuskript.services.revision_coordinator import (
        ProjectRevisionCoordinator,
    )

    class Settings:
        revisions = {
            "keep": True,
            "backend": GIT,
            "git": {"autoCommit": False, "taggedOnly": True},
        }

    def refuse(*args, **kwargs):
        raise AssertionError("Git must not be reached")

    coordinator = ProjectRevisionCoordinator(backend_factory=refuse)

    assert coordinator.after_project_save(
        "/nowhere/story.msk", Settings()
    ) is None
