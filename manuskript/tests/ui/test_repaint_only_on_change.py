"""Repainting a document is for when the painting would differ.

Rehighlighting walks every block of a document. Opening a project sets the
dictionary on every editor in the window, then toggles spellcheck on every
editor in the window -- 62 of each, measured, and almost always to the value
they already had -- and each setter repainted unconditionally. Two hundred
and seventy full repaints per open, to arrive at what was already on screen.

The guard is the one this code already used in setSearched: compare, and
return when there is nothing to show differently. No new state, nothing to
invalidate -- every comparison is against a value the object already held.
"""

from unittest.mock import MagicMock, patch

from PyQt5.QtGui import QTextBlockFormat, QTextCharFormat

from manuskript.ui.highlighters.basicHighlighter import BasicHighlighter
from manuskript.ui.views.textEditView import textEditView


def an_editor(spellcheck=False, dictionary=""):
    editor = textEditView(spellcheck=spellcheck, dict=dictionary)
    editor.highlighter = MagicMock()
    return editor


# ------------------------------------------------------- the dictionary

def test_setting_the_dictionary_it_already_has_repaints_nothing():
    editor = an_editor(dictionary="en_GB")
    editor._dict = object()

    editor.setDict("en_GB")

    editor.highlighter.rehighlight.assert_not_called()
    assert editor.currentDict == "en_GB"


def test_a_different_dictionary_repaints():
    editor = an_editor(dictionary="en_GB")
    editor._dict = object()

    editor.setDict("")

    editor.highlighter.rehighlight.assert_called_once_with()
    assert editor.currentDict == ""


def test_the_same_name_with_no_dictionary_loaded_yet_still_repaints():
    """The name matching is not enough: an editor that never managed to
    load that dictionary has nothing on screen yet.
    """
    editor = an_editor(dictionary="en_GB")
    editor._dict = None

    editor.setDict("en_GB")

    editor.highlighter.rehighlight.assert_called_once_with()


# -------------------------------------------------------- spellchecking

def test_turning_spellcheck_off_when_it_is_already_off_repaints_nothing():
    editor = an_editor(spellcheck=False)

    editor.toggleSpellcheck(False)

    editor.highlighter.rehighlight.assert_not_called()
    assert editor.spellcheck is False


def test_asking_for_spellcheck_without_a_dictionary_repaints_nothing():
    """It does not get spellcheck, so nothing on screen changes. What
    decides is the state this leaves behind, not the state requested.
    """
    editor = an_editor(spellcheck=False)
    editor._dict = None

    with patch(
        "manuskript.ui.views.textEditView.Spellchecker.getDictionary",
        return_value=None,
    ):
        editor.toggleSpellcheck(True)

    assert editor.spellcheck is False
    editor.highlighter.rehighlight.assert_not_called()


def test_turning_spellcheck_on_with_a_dictionary_repaints():
    editor = an_editor(spellcheck=False)
    editor._dict = object()

    editor.toggleSpellcheck(True)

    assert editor.spellcheck is True
    editor.highlighter.rehighlight.assert_called_once_with()


def test_turning_spellcheck_off_when_it_was_on_repaints():
    editor = an_editor(spellcheck=False)
    editor._dict = object()
    editor.spellcheck = True

    editor.toggleSpellcheck(False)

    assert editor.spellcheck is False
    editor.highlighter.rehighlight.assert_called_once_with()


# ------------------------------------------------- the default formats

def a_highlighter():
    editor = textEditView(spellcheck=False)
    highlighter = BasicHighlighter(editor)
    highlighter.rehighlight = MagicMock()
    return highlighter


def test_the_same_block_format_repaints_nothing():
    highlighter = a_highlighter()
    fmt = QTextBlockFormat()
    fmt.setTextIndent(4)
    highlighter.setDefaultBlockFormat(fmt)
    highlighter.rehighlight.reset_mock()

    same = QTextBlockFormat()
    same.setTextIndent(4)
    highlighter.setDefaultBlockFormat(same)

    highlighter.rehighlight.assert_not_called()


def test_a_different_block_format_repaints():
    highlighter = a_highlighter()
    fmt = QTextBlockFormat()
    fmt.setTextIndent(4)
    highlighter.setDefaultBlockFormat(fmt)
    highlighter.rehighlight.reset_mock()

    other = QTextBlockFormat()
    other.setTextIndent(12)
    highlighter.setDefaultBlockFormat(other)

    highlighter.rehighlight.assert_called_once_with()
    assert highlighter._defaultBlockFormat.textIndent() == 12


def test_the_same_char_format_repaints_nothing():
    highlighter = a_highlighter()
    fmt = QTextCharFormat()
    fmt.setFontItalic(True)
    highlighter.setDefaultCharFormat(fmt)
    highlighter.rehighlight.reset_mock()

    same = QTextCharFormat()
    same.setFontItalic(True)
    highlighter.setDefaultCharFormat(same)

    highlighter.rehighlight.assert_not_called()


def test_a_different_char_format_repaints():
    highlighter = a_highlighter()
    highlighter.setDefaultCharFormat(QTextCharFormat())
    highlighter.rehighlight.reset_mock()

    other = QTextCharFormat()
    other.setFontItalic(True)
    highlighter.setDefaultCharFormat(other)

    highlighter.rehighlight.assert_called_once_with()
