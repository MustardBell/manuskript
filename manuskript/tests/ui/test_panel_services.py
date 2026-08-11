"""Feature-panel services expose capabilities, not MainWindow."""


def test_panel_dialogs_keep_only_parenting_and_translation(MW):
    from manuskript.ui.panel_services import PanelDialogs

    dialogs = PanelDialogs(MW.centralWidget(), MW.tr)

    assert dialogs.parent is MW.centralWidget()
    assert dialogs.translate("Name") == MW.tr("Name")
    assert not hasattr(dialogs, "window")
    assert not hasattr(dialogs, "_window")
