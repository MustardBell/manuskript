def test_frequency_analyzer_receives_project_dependencies(
        MWEmptyProject):
    window = MWEmptyProject

    window.workspaceDialogs.show_frequency()

    dialog = window.workspaceDialogs.frequency_dialog
    assert dialog.outline_model is window.projectRuntime.models.outline
    assert dialog.settings is window.projectRuntime.settingsManager
    assert dialog.parent() is window

    dialog.close()
