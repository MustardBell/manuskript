from unittest.mock import MagicMock

from PyQt5.QtCore import QPoint, QRect

from manuskript.ui.window_placement import (
    WindowPlacementController,
    WindowPlacementViews,
)


def test_child_is_centered_on_workspace_geometry():
    child = MagicMock()
    child.geometry.return_value = QRect(0, 0, 200, 100)
    controller = WindowPlacementController(
        WindowPlacementViews(
            workspace_geometry=lambda: QRect(50, 80, 1000, 600)
        )
    )

    controller.center(child)

    child.move.assert_called_once_with(
        QRect(50, 80, 1000, 600).center() - QPoint(100, 50)
    )


def test_dispose_releases_geometry_provider():
    controller = WindowPlacementController(
        WindowPlacementViews(workspace_geometry=MagicMock())
    )

    controller.dispose()

    assert controller._views is None
