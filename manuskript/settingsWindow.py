#!/usr/bin/env python
# --!-- coding: utf8 --!--
import os
import shutil

from PyQt5.QtCore import QSize, QTranslator, QObject
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QFont, QColor, QPixmap, QStandardItem, QPainter
from PyQt5.QtGui import QStyleHints
from PyQt5.QtWidgets import QWidget, QStyle, QColorDialog, QListWidgetItem, QMessageBox
from PyQt5.QtWidgets import qApp, QFileDialog

from manuskript.domain.theme import ThemeEditorSession
from manuskript.services.git_revisions import (
    inspect_git_availability,
)
from manuskript.services.application_preferences import (
    ApplicationPreferences,
)
from manuskript.services.theme_repository import ThemeRepository
# Spell checker support
from manuskript.enums import Outline
from manuskript.functions import (
    allPaths,
    appPath,
    iconColor,
    writablePath,
)
from manuskript.functions import findBackground, themeIcon
from manuskript.ui.application_settings_controller import (
    ApplicationSettingsController,
    ApplicationSettingsViews,
)
from manuskript.ui.editors.themes import ThemePreviewRenderer
from manuskript.ui.plugins.index_card_styles import (
    IndexCardStyleService,
)
from manuskript.ui.revision_settings_controller import (
    RevisionSettingsController,
    RevisionSettingsViews,
)
from manuskript.ui.settings_ui import Ui_Settings
from manuskript.ui import style as S


class settingsWindow(QWidget, Ui_Settings):
    def __init__(
        self,
        views,
        settings_manager,
        theme_repository=None,
        theme_preview_renderer=None,
        application_preferences=None,
        card_styles=None,
    ):
        QWidget.__init__(self, views.parent)
        self.setupUi(self)
        self.views = views
        self.settings = settings_manager
        self.themeRepository = (
            theme_repository
            if theme_repository is not None
            else ThemeRepository()
        )
        self.themePreviewRenderer = (
            theme_preview_renderer
            if theme_preview_renderer is not None
            else ThemePreviewRenderer()
        )
        self.applicationPreferences = (
            application_preferences
            if application_preferences is not None
            else ApplicationPreferences()
        )
        self.cardStyles = (
            card_styles
            if card_styles is not None
            else IndexCardStyleService()
        )

        # UI
        for l in [self.lblTitleGeneral,
                  self.lblTitleGeneral_2,
                  self.lblTitleViews,
                  self.lblTitleLabels,
                  self.lblTitleStatus,
                  self.lblTitleFullscreen,
                  self.lblTitleStyle,
                  ]:
            l.setStyleSheet(S.titleLabelSS())

        icons = [QIcon.fromTheme("configure"),
                 QIcon.fromTheme("history-view"),
                 QIcon.fromTheme("gnome-settings"),
                 themeIcon("label"),
                 themeIcon("status"),
                 QIcon.fromTheme("preferences-desktop-theme"),
                 QIcon.fromTheme("color-picker")
                ]
        for i in range(self.lstMenu.count()):
            item = self.lstMenu.item(i)
            item.setSizeHint(QSize(item.sizeHint().width(), 42))
            item.setTextAlignment(Qt.AlignCenter)
            if icons[i]:
                item.setIcon(icons[i])
        self.lstMenu.setMaximumWidth(140)
        self.lstMenu.setMinimumWidth(140)

        self.applicationSettings = ApplicationSettingsController(
            ApplicationSettingsViews.for_dialog(self),
            self.settings,
            self.applicationPreferences,
            qApp,
            auto_load_values=self.views.startup.auto_load_values,
            set_auto_load=self.views.startup.set_auto_load,
            reconfigure_autosave=self.views.project.reconfigure_autosave,
            apply_workspace_font=self.views.appearance.set_font,
            update_stats=self.views.appearance.update_stats,
        )
        self.applicationSettings.install()
        # Compatibility for extensions that inspect the available mapping.
        self.translations = self.applicationSettings.translations

        # Revisions are one settings feature with their own state and
        # commands. The dialog exposes compatibility methods below, but no
        # longer coordinates Git availability and ten controls itself.
        self.revisionSettings = RevisionSettingsController(
            RevisionSettingsViews.for_dialog(self),
            self.settings,
            current_project=self.views.project.current_file,
            show_history=self.views.project.show_revision_history,
            availability=lambda: self.gitAvailability(),
            translate=self.tr,
        )
        self.revisionSettings.install()

        # Views
        self.tabViews.setCurrentIndex(0)
        lst = ["Nothing", "POV", "Label", "Progress", "Compile"]
        for cmb in self.viewSettingsDatas():
            item, part = self.viewSettingsDatas()[cmb]
            cmb.setCurrentIndex(lst.index(self.settings.viewSettings[item][part]))
            cmb.currentIndexChanged.connect(self.viewSettingsChanged)

        for chk in self.outlineColumnsData():
            col = self.outlineColumnsData()[chk]
            chk.setChecked(col in self.settings.outlineViewColumns)
            chk.stateChanged.connect(self.outlineColumnsChanged)

        self.chkOutlinePOV.setVisible(self.settings.viewMode != "simple") #  Hides checkbox if non-fiction view mode

        for item, what, value in [
            (self.rdoTreeItemCount, "InfoFolder", "Count"),
            (self.rdoTreeWC, "InfoFolder", "WC"),
            (self.rdoTreeCC, "InfoFolder", "CC"),
            (self.rdoTreeProgress, "InfoFolder", "Progress"),
            (self.rdoTreeSummary, "InfoFolder", "Summary"),
            (self.rdoTreeNothing, "InfoFolder", "Nothing"),
            (self.rdoTreeTextWC, "InfoText", "WC"),
            (self.rdoTreeTextCC, "InfoText", "CC"),
            (self.rdoTreeTextProgress, "InfoText", "Progress"),
            (self.rdoTreeTextSummary, "InfoText", "Summary"),
            (self.rdoTreeTextNothing, "InfoText", "Nothing"),
        ]:
            item.setChecked(self.settings.viewSettings["Tree"][what] == value)
            item.toggled.connect(self.treeViewSettignsChanged)

        self.sldTreeIconSize.valueChanged.connect(self.treeViewSettignsChanged)
        self.sldTreeIconSize.valueChanged.connect(
            lambda v: self.lblTreeIconSize.setText("{}x{}".format(v, v)))
        self.sldTreeIconSize.setValue(self.settings.viewSettings["Tree"]["iconSize"])

        self.chkCountSpaces.setChecked(self.settings.countSpaces);
        self.chkCountSpaces.stateChanged.connect(self.countSpacesChanged)

        self.populateCorkStyles()
        self.cmbCorkStyle.currentIndexChanged.connect(self.setCorkStyle)

        self.populatesCmbBackgrounds(self.cmbCorkImage)
        self.setCorkImageDefault()
        self.updateCorkColor()
        self.cmbCorkImage.currentIndexChanged.connect(self.setCorkBackground)
        self.btnCorkColor.clicked.connect(self.setCorkColor)

        # Text editor
        opt = self.settings.textEditor
            # Font
        self.setButtonColor(self.btnEditorFontColor, opt["fontColor"])
        self.btnEditorFontColor.clicked.connect(self.choseEditorFontColor)
        self.setButtonColor(self.btnEditorMisspelledColor, opt["misspelled"])
        self.btnEditorMisspelledColor.clicked.connect(self.choseEditorMisspelledColor)
        self.setButtonColor(self.btnEditorBackgroundColor, opt["background"])
        self.btnEditorBackgroundColor.clicked.connect(self.choseEditorBackgroundColor)
        self.chkEditorBackgroundTransparent.setChecked(opt["backgroundTransparent"])
        self.chkEditorBackgroundTransparent.stateChanged.connect(self.updateEditorSettings)
        self.btnEditorColorDefault.clicked.connect(self.restoreEditorColors)
        f = QFont()
        f.fromString(opt["font"])
        self.cmbEditorFontFamily.setCurrentFont(f)
        self.cmbEditorFontFamily.currentFontChanged.connect(self.updateEditorSettings)
        self.spnEditorFontSize.setValue(f.pointSize())
        self.spnEditorFontSize.valueChanged.connect(self.updateEditorSettings)
            # Cursor
        self.chkEditorCursorWidth.setChecked(opt["cursorWidth"] != 1)
        self.chkEditorCursorWidth.stateChanged.connect(self.updateEditorSettings)
        self.spnEditorCursorWidth.setValue(opt["cursorWidth"] if opt["cursorWidth"] != 1 else 9)
        self.spnEditorCursorWidth.valueChanged.connect(self.updateEditorSettings)
        self.spnEditorCursorWidth.setEnabled(opt["cursorWidth"] != 1)
        self.chkEditorNoBlinking.setChecked(opt["cursorNotBlinking"])
        self.chkEditorNoBlinking.stateChanged.connect(self.setApplicationCursorBlinking)
        self.chkEditorTypeWriterMode.setChecked(opt["alwaysCenter"])
        self.chkEditorTypeWriterMode.stateChanged.connect(self.updateEditorSettings)
        self.cmbEditorFocusMode.setCurrentIndex(
                0 if not opt["focusMode"] else
                1 if opt["focusMode"] == "sentence" else
                2 if opt["focusMode"] == "line" else
                3)
        self.cmbEditorFocusMode.currentIndexChanged.connect(self.updateEditorSettings)
            # Text areas
        self.chkEditorMaxWidth.setChecked(opt["maxWidth"] != 0)
        self.chkEditorMaxWidth.stateChanged.connect(self.updateEditorSettings)
        self.spnEditorMaxWidth.setEnabled(opt["maxWidth"] != 0)
        self.spnEditorMaxWidth.setValue(500 if opt["maxWidth"] == 0 else opt["maxWidth"])
        self.spnEditorMaxWidth.valueChanged.connect(self.updateEditorSettings)
        self.spnEditorMarginsLR.setValue(opt["marginsLR"])
        self.spnEditorMarginsLR.valueChanged.connect(self.updateEditorSettings)
        self.spnEditorMarginsTB.setValue(opt["marginsTB"])
        self.spnEditorMarginsTB.valueChanged.connect(self.updateEditorSettings)
            # Paragraphs
        self.cmbEditorAlignment.setCurrentIndex(opt["textAlignment"])
        self.cmbEditorAlignment.currentIndexChanged.connect(self.updateEditorSettings)
        self.cmbEditorLineSpacing.setCurrentIndex(
                0 if opt["lineSpacing"] == 100 else
                1 if opt["lineSpacing"] == 150 else
                2 if opt["lineSpacing"] == 200 else
                3)
        self.cmbEditorLineSpacing.currentIndexChanged.connect(self.updateEditorSettings)
        self.spnEditorLineSpacing.setValue(opt["lineSpacing"])
        self.spnEditorLineSpacing.valueChanged.connect(self.updateEditorSettings)
        self.spnEditorLineSpacing.setEnabled(opt["lineSpacing"] not in [100, 150, 200])
        self.spnEditorLineSpacing.valueChanged.connect(self.updateEditorSettings)
        self.spnEditorTabWidth.setValue(opt["tabWidth"])
        self.spnEditorTabWidth.valueChanged.connect(self.updateEditorSettings)
        self.chkEditorIndent.setChecked(opt["indent"])
        self.chkEditorIndent.stateChanged.connect(self.updateEditorSettings)
        self.spnEditorParaAbove.setValue(opt["spacingAbove"])
        self.spnEditorParaAbove.valueChanged.connect(self.updateEditorSettings)
        self.spnEditorParaBelow.setValue(opt["spacingBelow"])
        self.spnEditorParaBelow.valueChanged.connect(self.updateEditorSettings)
        self.timerUpdateWidgets = QTimer()
        self.timerUpdateWidgets.setSingleShot(True)
        self.timerUpdateWidgets.setInterval(250)
        self.timerUpdateWidgets.timeout.connect(self.updateAllWidgets)

        # Labels
        self.lstLabels.setModel(self._models().labels)
        self.lstLabels.setRowHidden(0, True)
        self.lstLabels.clicked.connect(self.updateLabelColor)
        self.btnLabelAdd.clicked.connect(self.addLabel)
        self.btnLabelRemove.clicked.connect(self.removeLabel)
        self.btnLabelColor.clicked.connect(self.setLabelColor)

        # Statuses
        self.lstStatus.setModel(self._models().statuses)
        self.lstStatus.setRowHidden(0, True)
        self.btnStatusAdd.clicked.connect(self.addStatus)
        self.btnStatusRemove.clicked.connect(self.removeStatus)

        # Fullscreen
        self.themeEditor = ThemeEditorSession()
        self._loadingTheme = False
        self.btnThemeEditOK.setIcon(qApp.style().standardIcon(QStyle.SP_DialogApplyButton))
        self.btnThemeEditOK.clicked.connect(self.saveTheme)
        self.btnThemeEditCancel.setIcon(qApp.style().standardIcon(QStyle.SP_DialogCancelButton))
        self.btnThemeEditCancel.clicked.connect(self.cancelEdit)
        self.cmbThemeEdit.currentIndexChanged.connect(self.themeEditStack.setCurrentIndex)
        self.cmbThemeEdit.setCurrentIndex(0)
        self.cmbThemeEdit.currentIndexChanged.emit(0)
        self.themeStack.setCurrentIndex(0)
        self.lstThemes.currentItemChanged.connect(self.themeSelected)
        self.populatesThemesList()
        self.btnThemeAdd.clicked.connect(self.newTheme)
        self.btnThemeEdit.clicked.connect(self.editTheme)
        self.btnThemeRemove.clicked.connect(self.removeTheme)
        self.timerUpdateFSPreview = QTimer()
        self.timerUpdateFSPreview.setSingleShot(True)
        self.timerUpdateFSPreview.setInterval(250)
        self.timerUpdateFSPreview.timeout.connect(self.updatePreview)
        self._connectThemeEditorSignals()

        # Style - Tooltips  
        self.chkUseSystemTooltips.setChecked(self.settings.tooltipStyle["useSystemDefaultsForTooltips"])
        self.chkUseSystemTooltips.stateChanged.connect(self.toggleTooltipCustomization)
        self.setButtonColor(self.btnTooltipTextColor, self.settings.tooltipStyle["textColor"])
        self.btnTooltipTextColor.clicked.connect(self.chooseTooltipTextColor)
        self.setButtonColor(self.btnTooltipBackgroundColor, self.settings.tooltipStyle["backgroundColor"])
        self.btnTooltipBackgroundColor.clicked.connect(self.chooseTooltipBackgroundColor)
        self.setButtonColor(self.btnTooltipBorderColor, self.settings.tooltipStyle["borderColor"])
        self.btnTooltipBorderColor.clicked.connect(self.chooseTooltipBorderColor)
        self.updateTooltipControlsState()

    def _models(self):
        """The project's models, from the runtime that owns them.

        Read when needed rather than captured: this window outlives any
        one project, and the models under it are replaced with each.
        """
        return self.views.project.models()

    def setTab(self, tab):

        tabs = {
            "General": 0,
            "Views": 1,
            "Labels": 2,
            "Status": 3,
            "Fullscreen": 4,
            "Style": 5,
        }

        if tab in tabs:
            self.lstMenu.setCurrentRow(tabs[tab])
        else:
            self.lstMenu.setCurrentRow(tab)
    ####################################################################################################
    #                                           GENERAL                                                #
    ####################################################################################################

    def setStyle(self, style):
        self.applicationSettings.set_style(style)

    def setTranslation(self, index):
        self.applicationSettings.set_translation(index)

    def setAppFontSize(self, val):
        self.applicationSettings.set_font_size(val)

    def charSettingsChanged(self, state=None):
        self.applicationSettings.set_progress_characters(state)

    def saveSettingsChanged(self, *_args):
        self.applicationSettings.save_project_preferences()

    ####################################################################################################
    #                                           REVISION                                               #
    ####################################################################################################

    def revisionsSettingsChanged(self, *_args):
        self.revisionSettings.save()

    def gitAvailability(self):
        return inspect_git_availability(self.views.project.current_file())

    def updateRevisionBackendUi(self):
        self.revisionSettings.update()

    def revisionStatusMessage(self, availability):
        return self.revisionSettings.status_message(availability)

    def initGitRepository(self):
        return self.revisionSettings.initialize_git_repository()

    ####################################################################################################
    #                                           VIEWS                                                  #
    ####################################################################################################

    def viewSettingsDatas(self):
        return {
            self.cmbTreeIcon: ("Tree", "Icon"),
            self.cmbTreeText: ("Tree", "Text"),
            self.cmbTreeBackground: ("Tree", "Background"),
            self.cmbOutlineIcon: ("Outline", "Icon"),
            self.cmbOutlineText: ("Outline", "Text"),
            self.cmbOutlineBackground: ("Outline", "Background"),
            self.cmbCorkIcon: ("Cork", "Icon"),
            self.cmbCorkText: ("Cork", "Text"),
            self.cmbCorkBackground: ("Cork", "Background"),
            self.cmbCorkBorder: ("Cork", "Border"),
            self.cmbCorkCorner: ("Cork", "Corner")
        }

    def viewSettingsChanged(self):
        cmb = self.sender()
        lst = ["Nothing", "POV", "Label", "Progress", "Compile"]
        item, part = self.viewSettingsDatas()[cmb]
        element = lst[cmb.currentIndex()]
        self.views.appearance.set_view_setting(item, part, element)
        self.views.appearance.rebuild_view_menu()

    def outlineColumnsData(self):
        return {
            self.chkOutlineTitle: Outline.title,
            self.chkOutlinePOV: Outline.POV,
            self.chkOutlineLabel: Outline.label,
            self.chkOutlineStatus: Outline.status,
            self.chkOutlineCompile: Outline.compile,
            self.chkOutlineWordCount: Outline.wordCount,
            self.chkOutlineGoal: Outline.goal,
            self.chkOutlinePercentage: Outline.goalPercentage,
        }

    def outlineColumnsChanged(self):
        chk = self.sender()
        val = True if chk.checkState() else False
        col = self.outlineColumnsData()[chk]
        if val and not col in self.settings.outlineViewColumns:
            self.settings.outlineViewColumns.append(col)
        elif not val and col in self.settings.outlineViewColumns:
            self.settings.outlineViewColumns.remove(col)

        # Update views
        for w in self.views.appearance.outlines():
            w.hideColumns()

    def treeViewSettignsChanged(self):
        for item, what, value in [
            (self.rdoTreeItemCount, "InfoFolder", "Count"),
            (self.rdoTreeWC, "InfoFolder", "WC"),
            (self.rdoTreeCC, "InfoFolder", "CC"),
            (self.rdoTreeProgress, "InfoFolder", "Progress"),
            (self.rdoTreeSummary, "InfoFolder", "Summary"),
            (self.rdoTreeNothing, "InfoFolder", "Nothing"),
            (self.rdoTreeTextWC, "InfoText", "WC"),
            (self.rdoTreeTextCC, "InfoText", "CC"),
            (self.rdoTreeTextProgress, "InfoText", "Progress"),
            (self.rdoTreeTextSummary, "InfoText", "Summary"),
            (self.rdoTreeTextNothing, "InfoText", "Nothing"),
        ]:
            if item.isChecked():
                self.settings.viewSettings["Tree"][what] = value

        iconSize = self.sldTreeIconSize.value()
        if iconSize != self.settings.viewSettings["Tree"]["iconSize"]:
            self.settings.viewSettings["Tree"]["iconSize"] = iconSize
            if self.views.appearance.project_tree is not None:
                self.views.appearance.project_tree.setIconSize(
                    QSize(iconSize, iconSize)
                )

        if self.views.appearance.project_tree is not None:
            self.views.appearance.project_tree.viewport().update()

    def countSpacesChanged(self):
        self.settings.countSpaces = True if self.chkCountSpaces.checkState() else False

        self.views.appearance.update_stats()

    def setCorkColor(self):
        color = QColor(self.settings.corkBackground["color"])
        self.colorDialog = QColorDialog(color, self)
        color = self.colorDialog.getColor(color)
        if color.isValid():
            self.settings.corkBackground["color"] = color.name()
            self.updateCorkColor()
            # Update Cork view
            self.views.appearance.update_cork_background()

    def populateCorkStyles(self):
        """List built-in and plugin card styles without firing a save."""
        previous = self.cmbCorkStyle.blockSignals(True)
        try:
            self.cmbCorkStyle.clear()
            for style_id, name in self.cardStyles.styles():
                self.cmbCorkStyle.addItem(name, style_id)
            index = self.cmbCorkStyle.findData(
                self.settings.indexCardStyle)
            if index < 0:
                # The project names a style whose plugin is gone.
                index = self.cmbCorkStyle.findData(
                    self.cardStyles.DEFAULT_ID)
            self.cmbCorkStyle.setCurrentIndex(max(0, index))
        finally:
            self.cmbCorkStyle.blockSignals(previous)

    def setCorkStyle(self):
        style_id = self.cmbCorkStyle.currentData()
        if not style_id:
            return
        self.settings.indexCardStyle = style_id
        self.views.appearance.update_cork_view()

    def updateCorkColor(self):
        self.btnCorkColor.setStyleSheet("background:{};".format(self.settings.corkBackground["color"]))

    def setCorkBackground(self, i):
        # Check if combobox was reset
        if i == -1:
            return

        img = self.cmbCorkImage.itemData(i)
        img = os.path.basename(img)
        if img:
            self.settings.corkBackground["image"] = img
        else:
            txt = self.cmbCorkImage.itemText(i)
            if txt == "":
                self.settings.corkBackground["image"] = ""
            else:
                img = self.addBackgroundImage()
                if img:
                    self.populatesCmbBackgrounds(self.cmbCorkImage)
                    self.settings.corkBackground["image"] = img
                self.setCorkImageDefault()
        # Update Cork view
        self.views.appearance.update_cork_background()

    def populatesCmbBackgrounds(self, cmb):
        # self.cmbDelegate = cmbPixmapDelegate()
        # self.cmbCorkImage.setItemDelegate(self.cmbDelegate)

        paths = allPaths(os.path.join("resources", "backgrounds"))
        cmb.clear()
        cmb.addItem(QIcon.fromTheme("list-remove"), "", "")
        for p in paths:
            lst = os.listdir(p)
            for l in lst:
                if l.lower()[-4:] in [".jpg", ".png"] or \
                                l.lower()[-5:] in [".jpeg"]:
                    px = QPixmap(os.path.join(p, l)).scaled(128, 64, Qt.KeepAspectRatio)
                    cmb.addItem(QIcon(px), "", os.path.join(p, l))

        cmb.addItem(QIcon.fromTheme("list-add"), " ", "")
        cmb.setIconSize(QSize(128, 64))

    def addBackgroundImage(self):
        lastDirectory = self.views.startup.last_accessed_directory()

        """File dialog that request an existing file. For opening an image."""
        filename = QFileDialog.getOpenFileName(self,
                                               self.tr("Open Image"),
                                               lastDirectory,
                                               self.imageFileFilter())[0]
        if filename:
            try:
                px = QPixmap()
                valid = px.load(filename)
                del px
                if valid:
                    shutil.copy(filename, writablePath(os.path.join("resources", "backgrounds")))
                    return os.path.basename(filename)
                else:
                    QMessageBox.warning(self, self.tr("Error"),
                                        self.tr("Unable to load selected file"))
            except Exception as e:
                QMessageBox.warning(self, self.tr("Error"),
                                    self.tr("Unable to add selected image:\n{}").format(str(e)))
        return None

    def imageFileFilter(self):
        """Return a translated label with Qt-compatible file patterns."""
        return "{} (*.png *.jpg *.jpeg);;{} (*)".format(
            self.tr("Image files"),
            self.tr("All files"),
        )
                

    def setCorkImageDefault(self):
        if self.settings.corkBackground["image"] != "":
            i = self.cmbCorkImage.findData(findBackground(self.settings.corkBackground["image"]))
            if i != -1:
                self.cmbCorkImage.setCurrentIndex(i)

            ####################################################################################################
            # VIEWS / EDITOR
            ####################################################################################################

    def updateEditorSettings(self):
        """
        Stores settings for editor appearance.
        """

        # Background
        self.settings.textEditor["backgroundTransparent"] = True if self.chkEditorBackgroundTransparent.checkState() else False

        # Font
        f = self.cmbEditorFontFamily.currentFont()
        f.setPointSize(self.spnEditorFontSize.value())
        self.settings.textEditor["font"] = f.toString()

        # Cursor
        self.settings.textEditor["cursorWidth"] = \
            1 if not self.chkEditorCursorWidth.isChecked() else \
            self.spnEditorCursorWidth.value()
        self.spnEditorCursorWidth.setEnabled(self.chkEditorCursorWidth.isChecked())
        self.settings.textEditor["alwaysCenter"] = self.chkEditorTypeWriterMode.isChecked()
        self.settings.textEditor["focusMode"] = \
            False if self.cmbEditorFocusMode.currentIndex() == 0 else \
            "sentence" if self.cmbEditorFocusMode.currentIndex() == 1 else \
            "line" if self.cmbEditorFocusMode.currentIndex() == 2 else \
            "paragraph"

        # Text area
        self.settings.textEditor["maxWidth"] = \
            0 if not self.chkEditorMaxWidth.isChecked() else \
            self.spnEditorMaxWidth.value()
        self.spnEditorMaxWidth.setEnabled(self.chkEditorMaxWidth.isChecked())
        self.settings.textEditor["marginsLR"] = self.spnEditorMarginsLR.value()
        self.settings.textEditor["marginsTB"] = self.spnEditorMarginsTB.value()

        # Paragraphs
        self.settings.textEditor["textAlignment"] = self.cmbEditorAlignment.currentIndex()
        self.settings.textEditor["lineSpacing"] = \
            100 if self.cmbEditorLineSpacing.currentIndex() == 0 else \
            150 if self.cmbEditorLineSpacing.currentIndex() == 1 else \
            200 if self.cmbEditorLineSpacing.currentIndex() == 2 else \
            self.spnEditorLineSpacing.value()
        self.spnEditorLineSpacing.setEnabled(self.cmbEditorLineSpacing.currentIndex() == 3)
        self.settings.textEditor["tabWidth"] = self.spnEditorTabWidth.value()
        self.settings.textEditor["indent"] = True if self.chkEditorIndent.checkState() else False
        self.settings.textEditor["spacingAbove"] = self.spnEditorParaAbove.value()
        self.settings.textEditor["spacingBelow"] = self.spnEditorParaBelow.value()

        self.timerUpdateWidgets.start()

    def updateAllWidgets(self):

        # Update font and defaultBlockFormat to all textEditView. Drastically.
        for w in self.views.editors.text_editors():
            w.loadFontSettings()

        # Update background color in all tabSplitter (tabs)
        for w in self.views.editors.tab_splitters():
            w.updateStyleSheet()

        # Update background color in all folder text view:
        for w in self.views.editors.folder_text_views():
            w.setStyleSheet("background: {};".format(self.settings.textEditor["background"]))

    def setApplicationCursorBlinking(self):
        self.settings.textEditor["cursorNotBlinking"] = self.chkEditorNoBlinking.isChecked()
        self.settings.applyCursorFlashTime()

    def choseEditorFontColor(self):
        color = self.settings.textEditor["fontColor"]
        self.colorDialog = QColorDialog(QColor(color), self)
        color = self.colorDialog.getColor(QColor(color))
        if color.isValid():
            self.settings.textEditor["fontColor"] = color.name()
            self.setButtonColor(self.btnEditorFontColor, color.name())
            self.updateEditorSettings()

    def choseEditorMisspelledColor(self):
        color = self.settings.textEditor["misspelled"]
        self.colorDialog = QColorDialog(QColor(color), self)
        color = self.colorDialog.getColor(QColor(color))
        if color.isValid():
            self.settings.textEditor["misspelled"] = color.name()
            self.setButtonColor(self.btnEditorMisspelledColor, color.name())
            self.updateEditorSettings()

    def choseEditorBackgroundColor(self):
        color = self.settings.textEditor["background"]
        self.colorDialog = QColorDialog(QColor(color), self)
        color = self.colorDialog.getColor(QColor(color))
        if color.isValid():
            self.settings.textEditor["background"] = color.name()
            self.setButtonColor(self.btnEditorBackgroundColor, color.name())
            self.updateEditorSettings()

    def restoreEditorColors(self):
        self.settings.textEditor["background"] = S.base
        self.setButtonColor(self.btnEditorBackgroundColor, S.base)
        self.settings.textEditor["fontColor"] = S.text
        self.setButtonColor(self.btnEditorFontColor, S.text)
        self.updateEditorSettings()

        ####################################################################################################
        #                                           STATUS                                                 #
        ####################################################################################################

    def addStatus(self):
        self._models().statuses.appendRow(QStandardItem(self.tr("New status")))

    def removeStatus(self):
        for i in self.lstStatus.selectedIndexes():
            self._models().statuses.removeRows(i.row(), 1)

        ####################################################################################################
        #                                           LABELS                                                 #
        ####################################################################################################

    def updateLabelColor(self, index):
        # px = QPixmap(64, 64)
        # px.fill(iconColor(self._models().labels.item(index.row()).icon()))
        # self.btnLabelColor.setIcon(QIcon(px))
        self.btnLabelColor.setStyleSheet("background:{};".format(
            iconColor(self._models().labels.item(index.row()).icon()).name()))
        self.btnLabelColor.setEnabled(True)

    def addLabel(self):
        px = QPixmap(32, 32)
        px.fill(Qt.transparent)
        self._models().labels.appendRow(QStandardItem(QIcon(px), self.tr("New label")))

    def removeLabel(self):
        for i in self.lstLabels.selectedIndexes():
            self._models().labels.removeRows(i.row(), 1)

    def setLabelColor(self):
        index = self.lstLabels.currentIndex()
        color = iconColor(self._models().labels.item(index.row()).icon())
        self.colorDialog = QColorDialog(color, self)
        color = self.colorDialog.getColor(color)
        if color.isValid():
            px = QPixmap(32, 32)
            px.fill(color)
            self._models().labels.item(index.row()).setIcon(QIcon(px))
            self.updateLabelColor(index)

        ####################################################################################################
        #                                       FULLSCREEN                                                 #
        ####################################################################################################

    def themeSelected(self, current, previous):
        if current:
            # UI updates
            self.btnThemeEdit.setEnabled(current.data(Qt.UserRole + 1))
            self.btnThemeRemove.setEnabled(current.data(Qt.UserRole + 1))
            # Save settings
            theme = current.data(Qt.UserRole)
            self.settings.fullScreenTheme = os.path.splitext(os.path.split(theme)[1])[0]
        else:
            # UI updates
            self.btnThemeEdit.setEnabled(False)
            self.btnThemeRemove.setEnabled(False)

    def newTheme(self):
        self.themeRepository.create(
            self.tr("newtheme"),
            self.tr("New theme"),
        )
        self.populatesThemesList()

    def editTheme(self):
        item = self.lstThemes.currentItem()
        theme = item.data(Qt.UserRole)
        self.loadTheme(theme)
        self.themeStack.setCurrentIndex(1)

    def removeTheme(self):
        item = self.lstThemes.currentItem()
        theme = item.data(Qt.UserRole)
        self.themeRepository.remove(theme)
        self.populatesThemesList()

    def populatesThemesList(self):
        current = self.settings.fullScreenTheme
        self.lstThemes.clear()

        for theme in self.themeRepository.list():
            item = QListWidgetItem(theme.name)
            item.setData(Qt.UserRole, theme.path)
            item.setData(Qt.UserRole + 1, theme.editable)
            item.setToolTip("{}{}".format(
                theme.name,
                self.tr(" (read-only)")
                if not theme.editable
                else "",
            ))

            thumb = os.path.splitext(theme.path)[0] + ".jpg"
            px = QPixmap(200, 120)
            px.fill(Qt.white)
            if not os.path.exists(thumb):
                currentScreen = qApp.desktop().screenNumber(self)
                screenRect = qApp.desktop().screenGeometry(
                    currentScreen
                )
                thumb = self.themePreviewRenderer.render(
                    theme.path,
                    screenRect,
                )

            icon = QPixmap(thumb).scaled(
                200,
                120,
                Qt.KeepAspectRatio,
            )
            painter = QPainter(px)
            painter.drawPixmap(
                px.rect().center() - icon.rect().center(),
                icon,
            )
            painter.end()
            item.setIcon(QIcon(px))

            self.lstThemes.addItem(item)

            if (
                current
                and current in os.path.basename(theme.path)
            ):
                self.lstThemes.setCurrentItem(item)
                current = None

        self.lstThemes.setIconSize(QSize(200, 120))

        if current:  # the theme from settings wasn't found
            # select the last from the list
            self.lstThemes.setCurrentRow(self.lstThemes.count() - 1)

    def _connectThemeEditorSignals(self):
        # Window Background
        self.btnThemWindowBackgroundColor.clicked.connect(
            lambda _checked=False: self.getThemeColor(
                "Background/Color"
            )
        )
        self.cmbThemeBackgroundImage.currentIndexChanged.connect(
            self.updateThemeBackground
        )
        self.cmbThemBackgroundType.currentIndexChanged.connect(
            lambda index: self.setSetting(
                "Background/Type",
                index,
            )
        )

        # Text Background
        self.btnThemeTextBackgroundColor.clicked.connect(
            lambda _checked=False: self.getThemeColor(
                "Foreground/Color"
            )
        )
        for widget, key in [
            (
                self.spnThemeTextBackgroundOpacity,
                "Foreground/Opacity",
            ),
            (self.spnThemeTextMargins, "Foreground/Margin"),
            (self.spnThemeTextPadding, "Foreground/Padding"),
            (self.cmbThemeTextPosition, "Foreground/Position"),
            (self.spnThemeTextRadius, "Foreground/Rounding"),
            (self.spnThemeTextWidth, "Foreground/Width"),
            (
                self.spnThemeLineSpacing,
                "Spacings/LineSpacing",
            ),
            (self.spnThemeParaAbove, "Spacings/ParagraphAbove"),
            (self.spnThemeParaBelow, "Spacings/ParagraphBelow"),
            (self.spnThemeTabWidth, "Spacings/TabWidth"),
        ]:
            widget_value_changed = (
                widget.valueChanged
                if hasattr(widget, "valueChanged")
                else widget.currentIndexChanged
            )
            widget_value_changed.connect(
                lambda value, setting_key=key: self.setSetting(
                    setting_key,
                    value,
                )
            )

        # Text Options
        self.btnThemeTextColor.clicked.connect(
            lambda _checked=False: self.getThemeColor("Text/Color")
        )
        self.cmbThemeFont.currentFontChanged.connect(
            self.updateThemeFont
        )
        self.cmbThemeFontSize.currentIndexChanged.connect(
            self.updateThemeFont
        )
        self.btnThemeMisspelledColor.clicked.connect(
            lambda _checked=False: self.getThemeColor(
                "Text/Misspelled"
            )
        )

        # Paragraph Options
        self.chkThemeIndent.stateChanged.connect(
            lambda value: self.setSetting(
                "Spacings/IndentFirstLine",
                value != 0,
            )
        )
        self.cmbThemeAlignment.currentIndexChanged.connect(
            lambda index: self.setSetting(
                "Spacings/Alignment",
                index,
            )
        )
        self.cmbThemeLineSpacing.currentIndexChanged.connect(
            self.updateLineSpacing
        )

    def loadTheme(self, theme):
        self.themeEditor.start(
            theme,
            self.themeRepository.load(theme),
        )
        self._loadingTheme = True
        try:
            self.populatesCmbBackgrounds(
                self.cmbThemeBackgroundImage
            )
            self.populatesFontSize()
            self.updateUIFromTheme()
        finally:
            self._loadingTheme = False

        self.updatePreview()

    def setSetting(self, key, val):
        self.themeEditor.update(key, val)
        if not self._loadingTheme:
            self.timerUpdateFSPreview.start()

    def updateUIFromTheme(self):
        self.txtThemeName.setText(self.themeEditor.data["Name"])

        # Window Background
        self.setButtonColor(self.btnThemWindowBackgroundColor, self.themeEditor.data["Background/Color"])
        i = self.cmbThemeBackgroundImage.findData(self.themeEditor.data["Background/ImageFile"], flags=Qt.MatchContains)
        if i != -1:
            self.cmbThemeBackgroundImage.setCurrentIndex(i)
        self.cmbThemBackgroundType.setCurrentIndex(self.themeEditor.data["Background/Type"])

        # Text background
        self.setButtonColor(self.btnThemeTextBackgroundColor, self.themeEditor.data["Foreground/Color"])
        self.spnThemeTextBackgroundOpacity.setValue(self.themeEditor.data["Foreground/Opacity"])
        self.spnThemeTextMargins.setValue(self.themeEditor.data["Foreground/Margin"])
        self.spnThemeTextPadding.setValue(self.themeEditor.data["Foreground/Padding"])
        self.cmbThemeTextPosition.setCurrentIndex(self.themeEditor.data["Foreground/Position"])
        self.spnThemeTextRadius.setValue(self.themeEditor.data["Foreground/Rounding"])
        self.spnThemeTextWidth.setValue(self.themeEditor.data["Foreground/Width"])

        # Text Options
        self.setButtonColor(self.btnThemeTextColor, self.themeEditor.data["Text/Color"])
        f = QFont()
        f.fromString(self.themeEditor.data["Text/Font"])
        self.cmbThemeFont.setCurrentFont(f)
        i = self.cmbThemeFontSize.findText(str(f.pointSize()))
        if i != -1:
            self.cmbThemeFontSize.setCurrentIndex(i)
        else:
            self.cmbThemeFontSize.addItem(str(f.pointSize()))
            self.cmbThemeFontSize.setCurrentIndex(self.cmbThemeFontSize.count() - 1)
        self.setButtonColor(self.btnThemeMisspelledColor, self.themeEditor.data["Text/Misspelled"])

        # Paragraph Options
        self.chkThemeIndent.setCheckState(Qt.Checked if self.themeEditor.data["Spacings/IndentFirstLine"] else Qt.Unchecked)
        self.spnThemeLineSpacing.setEnabled(False)
        self.cmbThemeAlignment.setCurrentIndex(self.themeEditor.data["Spacings/Alignment"])
        if self.themeEditor.data["Spacings/LineSpacing"] == 100:
            self.cmbThemeLineSpacing.setCurrentIndex(0)
        elif self.themeEditor.data["Spacings/LineSpacing"] == 150:
            self.cmbThemeLineSpacing.setCurrentIndex(1)
        elif self.themeEditor.data["Spacings/LineSpacing"] == 200:
            self.cmbThemeLineSpacing.setCurrentIndex(2)
        else:
            self.cmbThemeLineSpacing.setCurrentIndex(3)
            self.spnThemeLineSpacing.setEnabled(True)
            self.spnThemeLineSpacing.setValue(self.themeEditor.data["Spacings/LineSpacing"])
        self.spnThemeParaAbove.setValue(self.themeEditor.data["Spacings/ParagraphAbove"])
        self.spnThemeParaBelow.setValue(self.themeEditor.data["Spacings/ParagraphBelow"])
        self.spnThemeTabWidth.setValue(self.themeEditor.data["Spacings/TabWidth"])

    def populatesFontSize(self):
        self.cmbThemeFontSize.clear()
        s = list(range(6, 13)) + list(range(14, 29, 2)) + [36, 48, 72]
        for i in s:
            self.cmbThemeFontSize.addItem(str(i))

    def updateThemeFont(self, v):
        f = self.cmbThemeFont.currentFont()
        s = self.cmbThemeFontSize.itemText(self.cmbThemeFontSize.currentIndex())
        if s:
            f.setPointSize(int(s))

        self.themeEditor.update("Text/Font", f.toString())
        if not self._loadingTheme:
            self.timerUpdateFSPreview.start()

    def updateLineSpacing(self, i):
        if i == 0:
            self.themeEditor.data["Spacings/LineSpacing"] = 100
        elif i == 1:
            self.themeEditor.data["Spacings/LineSpacing"] = 150
        elif i == 2:
            self.themeEditor.data["Spacings/LineSpacing"] = 200
        elif i == 3:
            self.themeEditor.data["Spacings/LineSpacing"] = self.spnThemeLineSpacing.value()
        self.spnThemeLineSpacing.setEnabled(i == 3)
        if not self._loadingTheme:
            self.timerUpdateFSPreview.start()

    def updateThemeBackground(self, i):
        # Check if combobox was reset
        if i == -1:
            return

        img = self.cmbThemeBackgroundImage.itemData(i)

        if img:
            self.themeEditor.data["Background/ImageFile"] = os.path.split(img)[1]
        else:
            txt = self.cmbThemeBackgroundImage.itemText(i)
            if txt == "":
                self.themeEditor.data["Background/ImageFile"] = ""
            else:
                img = self.addBackgroundImage()
                if img:
                    self.populatesCmbBackgrounds(self.cmbThemeBackgroundImage)
                    self.themeEditor.data["Background/ImageFile"] = img
                i = self.cmbThemeBackgroundImage.findData(self.themeEditor.data["Background/ImageFile"], flags=Qt.MatchContains)
                if i != -1:
                    self.cmbThemeBackgroundImage.setCurrentIndex(i)
        self.updatePreview()

    def getThemeColor(self, key):
        color = self.themeEditor.data[key]
        self.colorDialog = QColorDialog(QColor(color), self)
        color = self.colorDialog.getColor(QColor(color))
        if color.isValid():
            self.themeEditor.data[key] = color.name()
            self.updateUIFromTheme()
            self.updatePreview()

    def updatePreview(self):
        if self._loadingTheme or not self.themeEditor.is_editing:
            return

        currentScreen = qApp.desktop().screenNumber(self)
        screen = qApp.desktop().screenGeometry(currentScreen)

        px = self.themePreviewRenderer.render(
            self.themeEditor.data,
            screen,
            self.lblPreview.size(),
        )
        self.lblPreview.setPixmap(px)

    def setButtonColor(self, btn, color):
        btn.setStyleSheet("background:{};".format(color))

    def saveTheme(self):
        self.themeEditor.data["Name"] = self.txtThemeName.text()
        self.themeRepository.save(
            self.themeEditor.path,
            self.themeEditor.data,
        )
        self.populatesThemesList()
        self.themeStack.setCurrentIndex(0)
        self.timerUpdateFSPreview.stop()
        self.themeEditor.finish()

    def cancelEdit(self):
        self.themeStack.setCurrentIndex(0)
        self.timerUpdateFSPreview.stop()
        self.themeEditor.cancel()

    def resizeEvent(self, event):
        QWidget.resizeEvent(self, event)
        if self.themeEditor.is_editing:
            self.updatePreview()

        ####################################################################################################
        #                                           STYLE                                                  #
        ####################################################################################################

    def chooseTooltipTextColor(self):
        color = self.settings.tooltipStyle["textColor"]
        self.colorDialog = QColorDialog(QColor(color), self)
        color = self.colorDialog.getColor(QColor(color))
        if color.isValid():
            self.settings.tooltipStyle["textColor"] = color.name()
            self.setButtonColor(self.btnTooltipTextColor, color.name())
            self.updateTooltipStyle()

    def chooseTooltipBackgroundColor(self):
        color = self.settings.tooltipStyle["backgroundColor"]
        self.colorDialog = QColorDialog(QColor(color), self)
        color = self.colorDialog.getColor(QColor(color))
        if color.isValid():
            self.settings.tooltipStyle["backgroundColor"] = color.name()
            self.setButtonColor(self.btnTooltipBackgroundColor, color.name())
            self.updateTooltipStyle()

    def chooseTooltipBorderColor(self):
        color = self.settings.tooltipStyle["borderColor"]
        self.colorDialog = QColorDialog(QColor(color), self)
        color = self.colorDialog.getColor(QColor(color))
        if color.isValid():
            self.settings.tooltipStyle["borderColor"] = color.name()
            self.setButtonColor(self.btnTooltipBorderColor, color.name())
            self.updateTooltipStyle()

    def toggleTooltipCustomization(self):
        self.settings.tooltipStyle["useSystemDefaultsForTooltips"] = self.chkUseSystemTooltips.isChecked()
        self.updateTooltipControlsState()
        self.updateTooltipStyle()

    def updateTooltipControlsState(self):
        visible = not self.settings.tooltipStyle["useSystemDefaultsForTooltips"]
        self.lblTooltipTextColor.setVisible(visible)
        self.btnTooltipTextColor.setVisible(visible)
        self.lblTooltipBackgroundColor.setVisible(visible)
        self.btnTooltipBackgroundColor.setVisible(visible)
        self.lblTooltipBorderColor.setVisible(visible)
        self.btnTooltipBorderColor.setVisible(visible)
        
        # Adjust layout spacing when controls are hidden/shown
        if visible:
            self.formLayout_tooltips.setContentsMargins(9, 9, 9, 9)
        else:
            self.formLayout_tooltips.setContentsMargins(9, 9, 9, 0)

    def updateTooltipStyle(self):
        self.settings.applyTooltipStyle()
