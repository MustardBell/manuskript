"""What the text of a document says, read one way by everything.

Two spellings of "the text" is not an academic worry: the editor's and the
buffer's differed by exactly this table, so a document with more than one
paragraph never compared equal to the same text in the model, and every
save reloaded it -- taking the undo history with it.
"""

from PyQt5.QtGui import QTextDocument

from manuskript.domain.text import (
    PLAIN_TRANSLATION_TABLE,
    as_text,
    plain_text,
)


def test_paragraph_breaks_read_as_newlines():
    document = QTextDocument()
    document.setPlainText("First paragraph\nSecond paragraph")

    # U+2029 is what Qt actually stores between paragraphs, which is the
    # whole reason a table is needed to read the document back.
    assert "\u2029" in document.toRawText()
    assert plain_text(document) == "First paragraph\nSecond paragraph"


def test_a_non_breaking_space_survives_being_read():
    """The reason toPlainText is not used: it returns a plain space here,
    silently rewriting what was typed.
    """
    document = QTextDocument()
    document.setPlainText("Monsieur\u00a0Dupont")

    assert plain_text(document) == "Monsieur\u00a0Dupont"
    assert document.toPlainText() == "Monsieur Dupont"


def test_every_separator_qt_substitutes_is_covered():
    for code_point in (0x2028, 0x2029, 0xfdd0, 0xfdd1):
        assert PLAIN_TRANSLATION_TABLE[code_point] == "\n"


def test_the_ways_of_having_no_text_are_one_way():
    """Including the literal "None" an older Manuskript wrote out for a
    missing value.
    """
    assert as_text(None) == ""
    assert as_text("None") == ""
    assert as_text("") == ""
    assert as_text(0) == "0"
    assert as_text("Chapter One") == "Chapter One"
