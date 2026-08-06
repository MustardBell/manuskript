"""What the text of a document is, in characters and nothing else.

Qt offers two ways to read a ``QTextDocument`` out, and neither is what a
manuscript wants. ``toPlainText()`` turns every non-breaking space into an
ordinary space, silently rewriting what was typed. ``toRawText()``
rewrites nothing, but leaves Qt's own paragraph and line separators
(U+2028, U+2029) and its internal object markers standing where a person
put a newline.

Hence the table below and one function over it. It lives here, under both
the editor that shows text and the service that holds it, because both
need the same answer. The editor owned it before, which left a project
service importing a widget class to find out what its own text said --
the layer beneath asking the layer above.

Nothing here imports Qt: a document is anything that can be asked for its
raw text.
"""

#: Mirrors the implementation of ``QTextDocument::toPlainText()``, minus
#: the part that destroys non-breaking spaces.
PLAIN_TRANSLATION_TABLE = {
    0x2028: "\n",
    0x2029: "\n",
    0xfdd0: "\n",
    0xfdd1: "\n",
}


def plain_text(document):
    """The document's text: Qt's separators as newlines, NBSP intact."""
    return document.toRawText().translate(PLAIN_TRANSLATION_TABLE)


def as_text(value):
    """A stored value as text, an absent one as no text at all.

    Item models answer with whatever was put in them -- a string, a
    number, nothing, or the string "None" left behind by an older
    Manuskript writing out a missing value. All three ways of having no
    text mean the same empty string here.
    """
    if value in [None, "None"]:
        return ""
    return str(value)
