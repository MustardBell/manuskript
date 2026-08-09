import zipfile

import pytest


@pytest.mark.parametrize("zipped", [False, True])
def test_absent_plugin_raw_file_survives_save_reopen_and_resave(
        MWNoProject, tmp_path, zipped):
    window = MWNoProject
    project_file = tmp_path / (
        "portable-zipped.msk" if zipped else "portable-folder.msk"
    )
    window.welcome.createFile(str(project_file), overwrite=True)
    window.projectRuntime.settingsManager.saveToZip = zipped
    namespace = window.projectManager.models.plugin_data.namespace(
        "example.archive",
        on_change=window.projectManager.startTimerNoChanges,
    )
    content = "Raw, editable plugin representation.\n"
    namespace.write("documents/main.data", content)

    assert window.projectManager.saveDatas()
    assert window.projectManager.closeProject()

    if zipped:
        with zipfile.ZipFile(project_file) as archive:
            assert (
                archive.read(
                    "plugins/example.archive/documents/main.data"
                ).decode("utf-8")
                == content
            )
    else:
        assert (
            (
                tmp_path
                / "portable-folder"
                / "plugins"
                / "example.archive"
                / "documents"
                / "main.data"
            ).read_text(encoding="utf-8")
            == content
        )

    assert window.projectManager.loadProject(str(project_file))
    loaded = window.projectManager.models.plugin_data.namespace(
        "example.archive"
    )
    assert loaded.read("documents/main.data") == content
    assert window.projectManager.saveDatas()
    assert loaded.read("documents/main.data") == content
