from unittest.mock import MagicMock

from PyQt5.QtCore import QRect, QSize

from manuskript.ui.editors.themes import ThemePreviewRenderer


def test_theme_preview_renderer_reuses_matching_file_preview(tmp_path):
    theme_path = tmp_path / "focus.theme"
    theme_path.write_text("[General]\nName=Focus\n")
    theme_data = {"Name": "Focus", "Background/Color": "#000000"}
    loader = MagicMock(side_effect=lambda _path: dict(theme_data))
    preview = MagicMock()
    preview_factory = MagicMock(return_value=preview)
    renderer = ThemePreviewRenderer(loader, preview_factory)
    screen = QRect(0, 0, 1920, 1080)
    size = QSize(200, 120)

    first = renderer.render(str(theme_path), screen, size)
    second = renderer.render(str(theme_path), screen, size)

    assert first is preview
    assert second is preview
    assert loader.call_count == 2
    preview_factory.assert_called_once_with(theme_data, screen, size)


def test_theme_preview_renderer_invalidates_data_and_geometry(tmp_path):
    theme_path = tmp_path / "focus.theme"
    theme_path.touch()
    theme_data = {"Name": "Focus"}
    loader = MagicMock(side_effect=lambda _path: dict(theme_data))
    preview_factory = MagicMock(
        side_effect=[MagicMock(), MagicMock(), MagicMock()]
    )
    renderer = ThemePreviewRenderer(loader, preview_factory)
    screen = QRect(0, 0, 1920, 1080)

    renderer.render(str(theme_path), screen, QSize(200, 120))
    renderer.render(str(theme_path), screen, QSize(400, 240))
    theme_data["Name"] = "Changed"
    renderer.render(str(theme_path), screen, QSize(400, 240))

    assert preview_factory.call_count == 3


def test_theme_preview_renderer_does_not_cache_live_editor_data():
    preview_factory = MagicMock(
        side_effect=[MagicMock(), MagicMock()]
    )
    renderer = ThemePreviewRenderer(
        theme_loader=MagicMock(),
        preview_factory=preview_factory,
    )
    theme_data = {"Name": "Editing"}
    screen = QRect(0, 0, 1920, 1080)

    renderer.render(theme_data, screen)
    renderer.render(theme_data, screen)

    assert preview_factory.call_count == 2
