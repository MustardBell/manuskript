def test_frequency_analyzer_receives_project_dependencies(
        MWEmptyProject):
    window = MWEmptyProject

    window.frequencyAnalyzer()

    assert window.fw.outline_model is window.projectRuntime.models.outline
    assert window.fw.settings is window.settingsManager
    assert window.fw.parent() is window

    window.fw.close()
