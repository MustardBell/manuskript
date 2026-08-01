def test_status_presenter_renders_critical_message(MW):
    MW.statusPresenter.show(
        "Could not save project",
        duration=10000,
        importance=3,
    )

    assert MW.statusLabel.text() == "Could not save project"
    assert "color:red" in MW.statusLabel.styleSheet()
    assert not MW.statusLabel.isHidden()

    MW.statusLabel.hide()
