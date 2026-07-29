from unittest.mock import patch

from PyQt5.QtCore import QCoreApplication, QEvent
from PyQt5.QtGui import QHelpEvent
from PyQt5.QtWidgets import QMenuBar, qApp

from manuskript.ui.menu_tooltips import MenuTooltipController
import manuskript.ui.menu_tooltips as menu_tooltips_module


def test_menu_tooltips_are_enabled_and_status_tips_are_promoted():
    menu_bar = QMenuBar()
    menu = menu_bar.addMenu("&View")
    action = menu.addAction("Live Preview")
    action.setStatusTip("Render Markdown around the active line")

    MenuTooltipController(menu_bar)

    assert menu.toolTipsVisible()
    assert action.toolTip() == (
        "Render Markdown around the active line"
    )


def test_menu_bar_tooltip_event_shows_the_action_description():
    menu_bar = QMenuBar()
    menu = menu_bar.addMenu("&File")
    controller = MenuTooltipController(
        menu_bar,
        {menu: "Open and save projects"},
    )
    menu_bar.resize(400, 30)
    menu_bar.show()
    qApp.processEvents()
    action = menu.menuAction()
    rect = menu_bar.actionGeometry(action)
    event = QHelpEvent(
        QEvent.ToolTip,
        rect.center(),
        menu_bar.mapToGlobal(rect.center()),
    )

    with patch.object(
        menu_tooltips_module.QToolTip,
        "showText",
    ) as show_tooltip:
        assert QCoreApplication.sendEvent(menu_bar, event)

    show_tooltip.assert_called_once_with(
        event.globalPos(),
        "Open and save projects",
        menu_bar,
        rect,
    )
    assert controller.parent() is menu_bar


def test_main_window_configures_top_level_menu_descriptions(MW):
    menus = (
        MW.menuFile,
        MW.menuEdit,
        MW.menuOrganize,
        MW.menuNavigate,
        MW.menuView,
        MW.menuTools,
        MW.menuHelp,
    )

    assert all(menu.toolTipsVisible() for menu in menus)
    assert all(
        menu.menuAction().toolTip()
        != menu.menuAction().text()
        for menu in menus
    )
