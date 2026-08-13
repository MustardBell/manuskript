from dataclasses import dataclass
from functools import partial
from types import MappingProxyType
from typing import Any, Callable, Mapping, Tuple

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QActionGroup, QMenu

from manuskript import functions as F
from manuskript.enums import Outline
from manuskript.panels.core import EDITOR
from manuskript.ui.connections import SignalConnectionRegistry
from manuskript.ui.views.outlineView import outlineView
from manuskript.ui.views.propertiesView import propertiesView


@dataclass(frozen=True)
class ViewConfigurationViews:
    """Capabilities needed to apply view settings in one workspace."""

    select_editor: Callable[[], None]
    simple_action: Any
    fiction_action: Any
    set_navigation_visible: Callable[[bool], None]
    properties: Callable[[], Tuple[Any, ...]]
    outlines: Callable[[], Tuple[Any, ...]]
    refreshers: Mapping[str, Callable[[], None]]

    @classmethod
    def for_window(cls, window):
        toolbar = window.toolbar
        navigation = window.dckNavigation
        main_editor = window.corePanels.editor.editor
        outline_tree = window.corePanels.outline.treeOutlineOutline
        project_tree = window.corePanels.project_tree.tree

        def refresh_outline():
            main_editor.updateTreeView()
            outline_tree.viewport().update()

        return cls(
            select_editor=lambda: window.activatePanel(EDITOR),
            simple_action=window.actModeSimple,
            fiction_action=window.actModeFiction,
            set_navigation_visible=lambda visible: (
                toolbar.setDockVisibility(navigation, visible)
            ),
            properties=lambda: tuple(
                window.findChildren(propertiesView)
            ),
            outlines=lambda: tuple(window.findChildren(outlineView)),
            refreshers=MappingProxyType({
                "Cork": main_editor.updateCorkView,
                "Outline": refresh_outline,
                "Tree": project_tree.viewport().update,
            }),
        )


class MainViewConfiguration:
    """Apply view configuration through explicit workspace capabilities."""

    def __init__(self, views):
        self.views = views

    def select_editor_tab(self):
        self.views.select_editor()

    def set_mode_checked(self, mode):
        if mode == "simple":
            self.views.simple_action.setChecked(True)
        else:
            self.views.fiction_action.setChecked(True)

    def set_fiction_features_visible(self, visible):
        self.views.set_navigation_visible(visible)
        for properties in self.views.properties():
            properties.lblPOV.setVisible(visible)
            properties.cmbPOV.setVisible(visible)

        for outline in self.views.outlines():
            outline.hideColumns()
            if not visible:
                # Suppress POV in simple mode without losing the saved
                # fiction-mode column selection.
                outline.hideColumn(Outline.POV)

    def refresh_category(self, category):
        refresh = self.views.refreshers.get(category)
        if refresh is not None:
            refresh()


@dataclass(frozen=True)
class ViewSettingsMenuViews:
    """The menus and translation capability used by the menu builder."""

    menu: Any
    mode_menu: Any
    markdown_menu: Any
    translate: Callable[[str], str]

    @classmethod
    def for_window(cls, window):
        return cls(
            menu=window.menuView,
            mode_menu=window.menuMode,
            markdown_menu=window.menuMarkdownMode,
            translate=window.tr,
        )


class ViewSettingsMenuBuilder:
    """Build the dynamic color-source menus for project views."""

    def __init__(self, views, controller):
        self.views = views
        self.controller = controller
        self.connections = SignalConnectionRegistry()

    def rebuild(self):
        self.connections.disconnect_all()
        views = self.views
        tr = views.translate
        values = [
            (tr("Nothing"), "Nothing"),
            (tr("POV"), "POV"),
            (tr("Label"), "Label"),
            (tr("Progress"), "Progress"),
            (tr("Compile"), "Compile"),
        ]
        menus = [
            (tr("Tree"), "Tree", "view-list-tree"),
            (tr("Index cards"), "Cork", "view-cards"),
            (tr("Outline"), "Outline", "view-outline"),
        ]
        submenus = {
            "Tree": [
                (tr("Icon color"), "Icon"),
                (tr("Text color"), "Text"),
                (tr("Background color"), "Background"),
            ],
            "Cork": [
                (tr("Icon"), "Icon"),
                (tr("Text"), "Text"),
                (tr("Background"), "Background"),
                (tr("Border"), "Border"),
                (tr("Corner"), "Corner"),
            ],
            "Outline": [
                (tr("Icon color"), "Icon"),
                (tr("Text color"), "Text"),
                (tr("Background color"), "Background"),
            ],
        }

        views.menu.clear()
        views.menu.addMenu(views.mode_menu)
        views.menu.addMenu(views.markdown_menu)
        views.menu.addSeparator()

        for title, category, icon_name in menus:
            menu = QMenu(title, views.menu)
            menu.setIcon(QIcon.fromTheme(icon_name))
            for subtitle, part in submenus[category]:
                submenu = QMenu(subtitle, menu)
                action_group = QActionGroup(submenu)
                for label, value in values:
                    action = QAction(label, submenu)
                    action.setCheckable(True)
                    action.setChecked(
                        self.controller.settings.viewSettings[
                            category
                        ][part]
                        == value
                    )
                    self.connections.connect_weak(
                        action.triggered,
                        partial(
                            self.controller.set_view_setting,
                            category,
                            part,
                            value,
                        ),
                        F.AUC,
                    )
                    action_group.addAction(action)
                    submenu.addAction(action)
                menu.addMenu(submenu)
            views.menu.addMenu(menu)

    def dispose(self):
        self.connections.disconnect_all()
        self.views = None
        self.controller = None
