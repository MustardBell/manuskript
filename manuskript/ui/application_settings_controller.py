"""General application and project preference controls for settings UI."""

from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import QStyleFactory


TRANSLATIONS = (
    ("English", ""),
    ("Arabic (Saudi Arabia)", "manuskript_ar_SA.qm"),
    ("German", "manuskript_de.qm"),
    ("English (Great Britain)", "manuskript_en_GB.qm"),
    ("Spanish", "manuskript_es.qm"),
    ("Persian", "manuskript_fa.qm"),
    ("French", "manuskript_fr.qm"),
    ("Hungarian", "manuskript_hu.qm"),
    ("Indonesian", "manuskript_id.qm"),
    ("Italian", "manuskript_it.qm"),
    ("Japanese", "manuskript_ja.qm"),
    ("Korean", "manuskript_ko.qm"),
    ("Norwegian Bokmål", "manuskript_nb_NO.qm"),
    ("Dutch", "manuskript_nl.qm"),
    ("Polish", "manuskript_pl.qm"),
    ("Portuguese (Brazil)", "manuskript_pt_BR.qm"),
    ("Portuguese (Portugal)", "manuskript_pt_PT.qm"),
    ("Romanian", "manuskript_ro.qm"),
    ("Russian", "manuskript_ru.qm"),
    ("Svenska", "manuskript_sv.qm"),
    ("Turkish", "manuskript_tr.qm"),
    ("Ukrainian", "manuskript_uk.qm"),
    ("Chinese (Simplified)", "manuskript_zh_CN.qm"),
    ("Chinese (Traditional)", "manuskript_zh_HANT.qm"),
)


@dataclass(frozen=True)
class ApplicationSettingsViews:
    style: object
    translation: object
    font_size: object
    progress_characters: object
    autosave: object
    autosave_after_changes: object
    autosave_delay: object
    autosave_after_changes_delay: object
    save_on_quit: object
    save_to_zip: object
    auto_load: object

    @classmethod
    def for_dialog(cls, dialog):
        return cls(
            style=dialog.cmbStyle,
            translation=dialog.cmbTranslation,
            font_size=dialog.spnGeneralFontSize,
            progress_characters=dialog.chkProgressChars,
            autosave=dialog.chkAutoSave,
            autosave_after_changes=dialog.chkAutoSaveNoChanges,
            autosave_delay=dialog.txtAutoSave,
            autosave_after_changes_delay=dialog.txtAutoSaveNoChanges,
            save_on_quit=dialog.chkSaveOnQuit,
            save_to_zip=dialog.chkSaveToZip,
            auto_load=dialog.chkAutoLoad,
        )


class ApplicationSettingsController:
    """Own general settings behavior without discovering application globals."""

    def __init__(
        self,
        views: ApplicationSettingsViews,
        settings,
        preferences,
        application,
        *,
        auto_load_values: Callable[[], tuple],
        set_auto_load: Callable[[bool], None],
        reconfigure_autosave: Callable[[], None],
        apply_workspace_font: Callable[[object], None],
        update_stats: Callable[[], None],
    ):
        self.views = views
        self.settings = settings
        self.preferences = preferences
        self.application = application
        self.auto_load_values = auto_load_values
        self.set_auto_load = set_auto_load
        self.reconfigure_autosave = reconfigure_autosave
        self.apply_workspace_font = apply_workspace_font
        self.update_stats = update_stats
        self.translations = OrderedDict(TRANSLATIONS)

    def install(self):
        self._load_application_controls()
        self._load_project_controls()
        self._connect()

    def _load_application_controls(self):
        views = self.views
        style_names = list(QStyleFactory.keys())
        views.style.addItems(style_names)
        current_style = self.application.style().objectName().lower()
        lowered = [name.lower() for name in style_names]
        views.style.setCurrentIndex(
            lowered.index(current_style) if current_style in lowered else 0
        )

        views.translation.clear()
        for name, path in self.translations.items():
            views.translation.addItem(name, path)
        translation = self.preferences.translation
        if translation is not None and translation in self.translations.values():
            selected = next(
                name
                for name, path in self.translations.items()
                if path == translation
            )
            views.translation.setCurrentText(selected)

        views.font_size.setValue(self.application.font().pointSize())

    def _load_project_controls(self):
        views = self.views
        settings = self.settings
        views.progress_characters.setChecked(settings.progressChars)
        views.autosave_delay.setValidator(
            QIntValidator(0, 999, views.autosave_delay)
        )
        views.autosave_after_changes_delay.setValidator(
            QIntValidator(0, 999, views.autosave_after_changes_delay)
        )
        views.autosave.setChecked(settings.autoSave)
        views.autosave_after_changes.setChecked(settings.autoSaveNoChanges)
        views.autosave_delay.setText(str(settings.autoSaveDelay))
        views.autosave_after_changes_delay.setText(
            str(settings.autoSaveNoChangesDelay)
        )
        views.save_on_quit.setChecked(settings.saveOnQuit)
        views.save_to_zip.setChecked(settings.saveToZip)
        auto_load, _last_project = self.auto_load_values()
        views.auto_load.setChecked(auto_load)

    def _connect(self):
        views = self.views
        views.style.currentIndexChanged[str].connect(self.set_style)
        views.translation.currentIndexChanged.connect(self.set_translation)
        views.font_size.valueChanged.connect(self.set_font_size)
        views.progress_characters.stateChanged.connect(
            self.set_progress_characters
        )
        for signal in (
            views.autosave.stateChanged,
            views.autosave_after_changes.stateChanged,
            views.save_on_quit.stateChanged,
            views.save_to_zip.stateChanged,
            views.autosave_delay.textEdited,
            views.autosave_after_changes_delay.textEdited,
            views.auto_load.stateChanged,
        ):
            signal.connect(self.save_project_preferences)

    def set_style(self, style):
        self.preferences.style = style
        self.application.setStyle(style)
        self.settings.applyTooltipStyle()

    def set_translation(self, _index=None):
        self.preferences.translation = self.views.translation.currentData()

    def set_font_size(self, value):
        font = self.application.font()
        font.setPointSize(value)
        self.application.setFont(font)
        self.apply_workspace_font(font)
        self.preferences.font_size = value

    def set_progress_characters(self, _state=None):
        self.settings.progressChars = self.views.progress_characters.isChecked()
        self.update_stats()

    def save_project_preferences(self, *_args):
        views = self.views
        if views.autosave_delay.text() in ("", "0"):
            views.autosave_delay.setText("1")
        if views.autosave_after_changes_delay.text() in ("", "0"):
            views.autosave_after_changes_delay.setText("1")

        self.set_auto_load(views.auto_load.isChecked())
        self.settings.autoSave = views.autosave.isChecked()
        self.settings.autoSaveNoChanges = (
            views.autosave_after_changes.isChecked()
        )
        self.settings.saveOnQuit = views.save_on_quit.isChecked()
        self.settings.saveToZip = views.save_to_zip.isChecked()
        self.settings.autoSaveDelay = int(views.autosave_delay.text())
        self.settings.autoSaveNoChangesDelay = int(
            views.autosave_after_changes_delay.text()
        )
        self.reconfigure_autosave()
