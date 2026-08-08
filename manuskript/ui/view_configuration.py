from functools import partial

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QActionGroup, QMenu

from manuskript import functions as F
from manuskript.enums import Outline
from manuskript.ui.views.outlineView import outlineView
from manuskript.ui.views.propertiesView import propertiesView


class MainViewConfiguration:
    """Adapt view-configuration operations to concrete main-window widgets."""

    def __init__(self, window):
        self.window = window

    def select_editor_tab(self):
        self.window.tabMain.setCurrentIndex(self.window.TabRedac)

    def set_mode_checked(self, mode):
        if mode == "simple":
            self.window.actModeSimple.setChecked(True)
        else:
            self.window.actModeFiction.setChecked(True)

    def set_fiction_features_visible(self, visible):
        window = self.window
        window.toolbar.setDockVisibility(
            window.dckNavigation,
            visible,
        )
        for properties in window.findChildren(propertiesView):
            properties.lblPOV.setVisible(visible)
            properties.cmbPOV.setVisible(visible)

        for outline in window.findChildren(outlineView):
            outline.hideColumns()
            if not visible:
                # Suppress POV in simple mode without losing the saved
                # fiction-mode column selection.
                outline.hideColumn(Outline.POV)

    def refresh_category(self, category):
        window = self.window
        if category == "Cork":
            window.mainEditor.updateCorkView()
        elif category == "Outline":
            window.mainEditor.updateTreeView()
            window.treeOutlineOutline.viewport().update()
        elif category == "Tree":
            window.corePanels.project_tree.tree.viewport().update()


class ViewSettingsMenuBuilder:
    """Build the dynamic color-source menus for project views."""

    def __init__(self, window, controller):
        self.window = window
        self.controller = controller

    def rebuild(self):
        window = self.window
        values = [
            (window.tr("Nothing"), "Nothing"),
            (window.tr("POV"), "POV"),
            (window.tr("Label"), "Label"),
            (window.tr("Progress"), "Progress"),
            (window.tr("Compile"), "Compile"),
        ]
        menus = [
            (window.tr("Tree"), "Tree", "view-list-tree"),
            (window.tr("Index cards"), "Cork", "view-cards"),
            (window.tr("Outline"), "Outline", "view-outline"),
        ]
        submenus = {
            "Tree": [
                (window.tr("Icon color"), "Icon"),
                (window.tr("Text color"), "Text"),
                (window.tr("Background color"), "Background"),
            ],
            "Cork": [
                (window.tr("Icon"), "Icon"),
                (window.tr("Text"), "Text"),
                (window.tr("Background"), "Background"),
                (window.tr("Border"), "Border"),
                (window.tr("Corner"), "Corner"),
            ],
            "Outline": [
                (window.tr("Icon color"), "Icon"),
                (window.tr("Text color"), "Text"),
                (window.tr("Background color"), "Background"),
            ],
        }

        window.menuView.clear()
        window.menuView.addMenu(window.menuMode)
        window.menuView.addMenu(window.menuMarkdownMode)
        window.menuView.addSeparator()

        for title, category, icon_name in menus:
            menu = QMenu(title, window.menuView)
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
                    action.triggered.connect(
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
            window.menuView.addMenu(menu)
