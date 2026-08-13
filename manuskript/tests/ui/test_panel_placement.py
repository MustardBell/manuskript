"""Precise dock placement without depending on drag target geometry."""

from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDockWidget, QMainWindow, QMenu

from manuskript.ui.panels.placement import (
    DockEntry,
    DockLayoutPort,
    DockRelation,
    PanelPlacementController,
    PanelPlacementTarget,
    PanelPlacementViews,
    PanelTogglePort,
)


# Native Qt objects must never predate the suite's one QApplication. Creating
# these lightweight controller fixtures first and the application later left
# stale native wrappers for cyclic collection during QApplication startup.
pytestmark = pytest.mark.usefixtures("test_application")


def placement_fixture():
    window = QMainWindow()
    source = QDockWidget("Source", window)
    source.setObjectName("source")
    target = QDockWidget("Target", window)
    target.setObjectName("target")
    add = MagicMock()
    split = MagicMock()
    tabify = MagicMock()
    area = MagicMock(return_value=Qt.RightDockWidgetArea)
    views = PanelPlacementViews(
        target=PanelPlacementTarget(
            host=MagicMock(),
            toggles=PanelTogglePort(MagicMock(), MagicMock()),
            title=lambda: "Window",
            watch_dock=lambda _dock: None,
        ),
        floating_menu=QMenu(window),
        move_menu=QMenu(window),
        arrange_menu=QMenu(window),
        docks=DockLayoutPort(
            entries=lambda: (
                DockEntry("source", "Source", source),
                DockEntry("target", "Target", target),
            ),
            area=area,
            add=add,
            split=split,
            tabify=tabify,
        ),
        translate=lambda text: text,
        targets=lambda: (),
    )
    return (
        PanelPlacementController(views),
        window,
        source,
        target,
        add,
        split,
        tabify,
    )


@pytest.mark.parametrize(
    "relation, expected_first, expected_second, orientation",
    (
        (DockRelation.LEFT, "source", "target", Qt.Horizontal),
        (DockRelation.RIGHT, "target", "source", Qt.Horizontal),
        (DockRelation.ABOVE, "source", "target", Qt.Vertical),
        (DockRelation.BELOW, "target", "source", Qt.Vertical),
    ),
)
def test_relative_commands_have_unambiguous_split_order(
        relation, expected_first, expected_second, orientation):
    controller, window, source, target, add, split, _tabify = (
        placement_fixture()
    )
    docks = {"source": source, "target": target}
    try:
        assert controller.place_relative(source, target, relation)

        add.assert_called_once_with(Qt.RightDockWidgetArea, source)
        split.assert_called_once_with(
            docks[expected_first], docks[expected_second], orientation,
        )
    finally:
        controller.dispose()
        window.close()


def test_tab_command_docks_then_groups_and_selects_the_source():
    controller, window, source, target, add, _split, tabify = (
        placement_fixture()
    )
    source.raise_ = raised = MagicMock()
    try:
        assert controller.tab_with(source, target)

        add.assert_called_once_with(Qt.RightDockWidgetArea, source)
        tabify.assert_called_once_with(target, source)
        raised.assert_called_once_with()
    finally:
        controller.dispose()
        window.close()


def test_floating_target_is_refused_before_any_layout_mutation():
    controller, window, source, target, add, split, tabify = (
        placement_fixture()
    )
    target.setFloating(True)
    try:
        assert not controller.place_relative(
            source, target, DockRelation.RIGHT,
        )
        assert not controller.tab_with(source, target)

        add.assert_not_called()
        split.assert_not_called()
        tabify.assert_not_called()
    finally:
        controller.dispose()
        window.close()
