from unittest.mock import MagicMock, patch

from manuskript import loadSave


def test_save_dispatches_explicit_context_to_current_format():
    context = MagicMock()

    with patch.object(
        loadSave.v1, "saveProject", return_value=True
    ) as save_project:
        result = loadSave.saveProject(context)

    assert result
    save_project.assert_called_once_with(context)


def test_save_dispatches_explicit_context_to_legacy_format():
    context = MagicMock()

    with patch.object(
        loadSave.v0, "saveProject", return_value=True
    ) as save_project:
        result = loadSave.saveProject(context, version=0)

    assert result
    save_project.assert_called_once_with(context)


def test_load_dispatches_explicit_context_to_detected_format(tmp_path):
    context = MagicMock()
    project = tmp_path / "story.msk"
    project.write_text("1", encoding="utf-8")

    with patch.object(
        loadSave.v1, "loadProject", return_value=[]
    ) as load_project:
        result = loadSave.loadProject(str(project), context)

    assert result == []
    load_project.assert_called_once_with(str(project), context, zip=False)


def test_persistence_facade_requires_explicit_context():
    try:
        loadSave.saveProject()
    except TypeError:
        pass
    else:
        raise AssertionError("saveProject accepted missing project context")
