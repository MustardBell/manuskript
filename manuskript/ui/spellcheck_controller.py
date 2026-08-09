"""Workspace-scoped spellcheck controls and dictionary selection."""

from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, Tuple

from PyQt5.QtWidgets import QAction, QActionGroup, QMenu, QStyle

from manuskript import functions as F
from manuskript.functions import Spellchecker
from manuskript.ui.connections import SignalConnectionRegistry
from manuskript.ui.views.textEditView import textEditView


@dataclass(frozen=True)
class SpellcheckViews:
    """The controls and editor operations spellcheck is allowed to use."""

    action: Any
    tools_menu: Any
    action_parent: Any
    translate: Callable[[str], str]
    warning_icon: Callable[[], Any]
    editors: Callable[[], Tuple[Any, ...]]
    open_url: Callable[[str], None]

    @classmethod
    def for_window(cls, window):
        style = window.style()
        return cls(
            action=window.actSpellcheck,
            tools_menu=window.menuTools,
            action_parent=window,
            translate=window.tr,
            warning_icon=lambda: style.standardIcon(
                QStyle.SP_MessageBoxWarning
            ),
            editors=lambda: tuple(window.findChildren(textEditView)),
            open_url=F.openURL,
        )


class SpellcheckController:
    """Own dictionary menus and apply spellcheck to one workspace."""

    def __init__(self, views, settings, spellchecker=Spellchecker):
        self.views = views
        self.settings = settings
        self.spellchecker = spellchecker
        self.menu = None
        self.group = None
        self._connections = SignalConnectionRegistry()
        self._dictionary_connections = SignalConnectionRegistry()
        self._compose()

    def _compose(self):
        if self.spellchecker.isInstalled():
            self.menu = QMenu(
                self.views.translate("Dictionary"),
                self.views.action_parent,
            )
            self.group = QActionGroup(self.views.action_parent)
            self.rebuild_dictionary_menu()
            self.views.tools_menu.addMenu(self.menu)
            self._connections.connect_weak(
                self.views.action.toggled,
                self.set_enabled,
                F.AUC,
            )
            return

        self.views.action.setVisible(False)
        for library, requirement in (
            self.spellchecker.supportedLibraries().items()
        ):
            action = QAction(
                self.views.translate(
                    "Install {}{} to use spellcheck"
                ).format(library, requirement or ""),
                self.views.action_parent,
            )
            action.setIcon(self.views.warning_icon())
            self._connections.connect_weak(
                action.triggered,
                partial(self.open_library, library),
                F.AUC,
            )
            self.views.tools_menu.addAction(action)

    def rebuild_dictionary_menu(self):
        if not self.spellchecker.isInstalled():
            return

        self._dictionary_connections.disconnect_all()
        self.menu.clear()
        dictionaries = self.spellchecker.availableDictionaries()

        if self.settings.dict is None:
            self.settings.dict = self.spellchecker.getDefaultDictionary()

        dictionary_available = any(
            self.spellchecker.normalizeDictName(library, dictionary)
            == self.settings.dict
            for library, dictionary_names in dictionaries.items()
            for dictionary in dictionary_names
        )
        if not dictionary_available:
            self.settings.dict = self.spellchecker.getDefaultDictionary()

        for action in self.group.actions():
            self.group.removeAction(action)
        for library, dictionary_names in dictionaries.items():
            title = (
                library
                if dictionary_names
                else self.views.translate(
                    "{} has no installed dictionaries"
                ).format(library)
            )
            heading = QAction(title, self.menu)
            heading.setEnabled(False)
            self.menu.addAction(heading)
            for dictionary in dictionary_names:
                action = QAction(dictionary, self.menu)
                action.setData(library)
                action.setCheckable(True)
                action.setChecked(
                    self.spellchecker.normalizeDictName(
                        library,
                        dictionary,
                    )
                    == self.settings.dict
                )
                self._dictionary_connections.connect_weak(
                    action.triggered,
                    self.apply_dictionary,
                    F.AUC,
                )
                self.group.addAction(action)
                self.menu.addAction(action)
            self.menu.addSeparator()

        if not dictionary_available:
            self.apply_dictionary()
            self.set_enabled(self.settings.spellcheck)

        for library, requirement in (
            self.spellchecker.supportedLibraries().items()
        ):
            if library in dictionaries:
                continue
            action = QAction(
                self.views.translate("{}{} is not installed").format(
                    library,
                    requirement or "",
                ),
                self.menu,
            )
            action.setEnabled(False)
            self.menu.addAction(action)
            self.menu.addSeparator()

    def apply_dictionary(self, _checked=False):
        if not self.spellchecker.isInstalled():
            return
        for action in self.group.actions():
            if not action.isChecked():
                continue
            self.settings.dict = self.spellchecker.normalizeDictName(
                action.data(),
                action.text().replace("&", ""),
            )
        for editor in self.views.editors():
            editor.setDict(self.settings.dict)

    def set_enabled(self, enabled):
        self.settings.spellcheck = enabled
        for editor in self.views.editors():
            editor.toggleSpellcheck(enabled)

    def open_library(self, library, _checked=False):
        self.views.open_url(
            self.spellchecker.getLibraryURL(library)
        )

    def dispose(self):
        self._dictionary_connections.disconnect_all()
        self._connections.disconnect_all()
        self.menu = None
        self.group = None
        self.views = None
        self.settings = None
        self.spellchecker = None
