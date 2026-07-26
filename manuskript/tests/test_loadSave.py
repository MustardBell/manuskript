from unittest.mock import MagicMock, patch

from manuskript import loadSave
from manuskript.domain.persistence import (
    ProjectLoadResult,
    ProjectSaveResult,
)
from manuskript.services.project_persistence import (
    ProjectPersistenceContext,
)


def test_save_dispatches_explicit_context_to_current_format():
    context = MagicMock()
    cache = {}
    file_access = MagicMock()
    expected = ProjectSaveResult()

    with patch.object(
        loadSave.v1, "saveProject", return_value=expected
    ) as save_project:
        result = loadSave.saveProject(
            context,
            cache=cache,
            file_access=file_access,
        )

    assert result is expected
    save_project.assert_called_once_with(
        context,
        cache=cache,
        file_access=file_access,
    )


def test_save_dispatches_explicit_context_to_legacy_format():
    context = MagicMock()
    expected = ProjectSaveResult()

    with patch.object(
        loadSave.v0, "saveProject", return_value=expected
    ) as save_project:
        result = loadSave.saveProject(context, version=0)

    assert result is expected
    save_project.assert_called_once_with(context)


def test_load_dispatches_explicit_context_to_detected_format(tmp_path):
    project = tmp_path / "story.msk"
    project.write_text("1", encoding="utf-8")
    context = ProjectPersistenceContext(
        project_file=str(project),
        models=MagicMock(),
        settings=MagicMock(),
    )
    cache = {}
    file_access = MagicMock()
    expected = ProjectLoadResult()

    with patch.object(
        loadSave.v1, "loadProject", return_value=expected
    ) as load_project:
        result = loadSave.loadProject(
            context,
            cache=cache,
            file_access=file_access,
        )

    assert result is expected
    load_project.assert_called_once_with(
        context,
        zip=False,
        cache=cache,
        file_access=file_access,
    )


def test_persistence_facade_requires_explicit_context():
    try:
        loadSave.saveProject()
    except TypeError:
        pass
    else:
        raise AssertionError("saveProject accepted missing project context")


def test_invalid_project_marker_is_a_fatal_load_result(tmp_path):
    project = tmp_path / "story.msk"
    project.write_text("not-a-version", encoding="utf-8")
    context = ProjectPersistenceContext(
        project_file=str(project),
        models=MagicMock(),
        settings=MagicMock(),
    )

    result = loadSave.loadProject(context)

    assert not result.succeeded
    assert result.fatal_errors == (str(project),)
