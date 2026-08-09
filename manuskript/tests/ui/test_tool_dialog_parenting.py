def test_about_dialog_is_owned_by_its_workspace(MWEmptyProject):
    window = MWEmptyProject

    window.about()
    try:
        assert window.dialog.parent() is window
    finally:
        window.dialog.close()


def test_targets_dialog_is_owned_without_receiving_main_window_authority(
        MWEmptyProject):
    window = MWEmptyProject

    window.sessionTargets()
    try:
        assert window.td.parent() is window
        assert not hasattr(window.td, "mw")
        assert window.td.context.writing_session is window.writingSession
    finally:
        window.td.close()
