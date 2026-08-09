from types import SimpleNamespace
from unittest.mock import MagicMock

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QMainWindow

from manuskript.ui.spellcheck_controller import (
    SpellcheckController,
    SpellcheckViews,
)


class FakeSpellchecker:
    installed = True
    dictionaries = {
        "enchant": ["en_US", "uk_UA"],
        "empty": [],
    }
    supported = {
        "enchant": "",
        "hunspell": " >= 1",
    }

    @classmethod
    def isInstalled(cls):
        return cls.installed

    @classmethod
    def availableDictionaries(cls):
        return {
            library: list(dictionaries)
            for library, dictionaries in cls.dictionaries.items()
        }

    @staticmethod
    def getDefaultDictionary():
        return "enchant:en_US"

    @staticmethod
    def normalizeDictName(library, dictionary):
        return "{}:{}".format(library, dictionary)

    @classmethod
    def supportedLibraries(cls):
        return dict(cls.supported)

    @staticmethod
    def getLibraryURL(library):
        return "https://example.invalid/{}".format(library)


def controller_fixture(dictionary=None, spellcheck=True, installed=True):
    FakeSpellchecker.installed = installed
    FakeSpellchecker.dictionaries = {
        "enchant": ["en_US", "uk_UA"],
        "empty": [],
    }
    window = QMainWindow()
    tools_menu = window.menuBar().addMenu("Tools")
    action = QAction("Spellcheck", window)
    action.setCheckable(True)
    action.setChecked(spellcheck)
    tools_menu.addAction(action)
    editor = MagicMock()
    opened = []
    views = SpellcheckViews(
        action=action,
        tools_menu=tools_menu,
        action_parent=window,
        translate=lambda text: text,
        warning_icon=QIcon,
        editors=lambda: (editor,),
        open_url=opened.append,
    )
    settings = SimpleNamespace(
        dict=dictionary,
        spellcheck=spellcheck,
    )
    controller = SpellcheckController(
        views,
        settings,
        spellchecker=FakeSpellchecker,
    )
    return controller, window, action, editor, settings, opened


def test_dictionary_menu_selects_and_applies_a_dictionary():
    controller, window, _action, editor, settings, _opened = (
        controller_fixture()
    )
    try:
        assert settings.dict == "enchant:en_US"
        assert [action.text() for action in controller.group.actions()] == [
            "en_US",
            "uk_UA",
        ]

        controller.group.actions()[1].trigger()

        assert settings.dict == "enchant:uk_UA"
        editor.setDict.assert_called_once_with("enchant:uk_UA")
    finally:
        controller.dispose()
        window.close()


def test_spellcheck_action_applies_to_every_workspace_editor():
    controller, window, action, editor, settings, _opened = (
        controller_fixture()
    )
    try:
        action.setChecked(False)

        assert settings.spellcheck is False
        editor.toggleSpellcheck.assert_called_once_with(False)
    finally:
        controller.dispose()
        window.close()


def test_unavailable_dictionary_falls_back_and_refreshes_editors():
    controller, window, _action, editor, settings, _opened = (
        controller_fixture(dictionary="missing:value")
    )
    try:
        assert settings.dict == "enchant:en_US"
        editor.setDict.assert_called_once_with("enchant:en_US")
        editor.toggleSpellcheck.assert_called_once_with(True)
    finally:
        controller.dispose()
        window.close()


def test_rebuilding_replaces_group_actions_instead_of_accumulating_them():
    controller, window, _action, _editor, _settings, _opened = (
        controller_fixture()
    )
    try:
        FakeSpellchecker.dictionaries = {"enchant": ["fr_FR"]}

        controller.rebuild_dictionary_menu()

        assert [action.text() for action in controller.group.actions()] == [
            "fr_FR"
        ]
    finally:
        controller.dispose()
        window.close()


def test_missing_spellchecker_offers_install_links():
    controller, window, action, _editor, _settings, opened = (
        controller_fixture(installed=False)
    )
    try:
        install_actions = [
            entry
            for entry in controller.views.tools_menu.actions()
            if entry.text().startswith("Install")
        ]
        assert not action.isVisible()
        assert len(install_actions) == 2

        install_actions[1].trigger()

        assert opened == ["https://example.invalid/hunspell"]
    finally:
        controller.dispose()
        window.close()


def test_main_window_exposes_one_spellcheck_capability(MW):
    assert MW.spellcheck.settings is MW.projectRuntime.settingsManager
    assert not hasattr(MW, "toggleSpellcheck")
    assert not hasattr(MW, "updateMenuDict")
    assert not hasattr(MW, "setDictionary")
    assert not hasattr(MW, "openSpellcheckWebPage")
