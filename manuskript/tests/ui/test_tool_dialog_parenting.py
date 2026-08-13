def test_about_dialog_is_owned_by_its_workspace(MWEmptyProject):
    window = MWEmptyProject

    dialog = window.workspaceDialogs.show_about()
    try:
        assert dialog.parent() is window
    finally:
        dialog.close()


def test_targets_dialog_is_owned_without_receiving_main_window_authority(
        MWEmptyProject):
    window = MWEmptyProject

    dialog = window.workspaceDialogs.show_targets()
    try:
        assert dialog.parent() is window
        assert not hasattr(dialog, "mw")
        assert dialog.context.writing_session is window.writingSession
    finally:
        dialog.close()
