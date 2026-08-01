from manuskript.domain.revisions import (
    RevisionBackendKind,
    RevisionConfiguration,
)


def test_old_revision_settings_select_internal_backend():
    configuration = RevisionConfiguration.from_mapping({
        "keep": True,
    })

    assert configuration.enabled
    assert configuration.backend is RevisionBackendKind.INTERNAL
    assert configuration.uses_internal_snapshots
    assert not configuration.uses_git


def test_git_revision_settings_do_not_capture_internal_snapshots():
    configuration = RevisionConfiguration.from_mapping({
        "keep": True,
        "backend": "git",
        "git": {
            "autoCommit": True,
            "taggedOnly": True,
        },
    })

    assert configuration.backend is RevisionBackendKind.GIT
    assert configuration.uses_git
    assert not configuration.uses_internal_snapshots
    assert configuration.auto_commit
    assert configuration.tagged_only


def test_unknown_backend_falls_back_to_internal():
    configuration = RevisionConfiguration.from_mapping({
        "keep": True,
        "backend": "future-backend",
    })

    assert configuration.backend is RevisionBackendKind.INTERNAL
