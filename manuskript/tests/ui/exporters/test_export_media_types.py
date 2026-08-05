"""Exporters name what they emit in the shared vocabulary.

Two facts are worth holding down. Every exporter's media type has to be one
core actually declares, or routing has nothing to match against. And pandoc
names its own writers, so the vocabulary must be translated at that boundary
rather than leaked into a raw block, where it would produce a fence pandoc
cannot read.
"""

from types import SimpleNamespace

import pytest

from manuskript.exporter.manuskript.BBCode import BBCode
from manuskript.exporter.manuskript.HTML import HTML as ManuskriptHTML
from manuskript.exporter.manuskript.markdown import markdown
from manuskript.exporter.manuskript.plainText import plainText
from manuskript.exporter.pandoc.HTML import HTML as PandocHTML
from manuskript.exporter.pandoc.PDF import PDF
from manuskript.exporter.pandoc.abstractPlainText import PANDOC_WRITERS
from manuskript.exporter.pandoc.outputFormats import DocX, OpenDocument, ePub
from manuskript.exporter.pandoc.plainText import (
    OPML as PandocOPML,
    BBCode as PandocBBCode,
    latex as PandocLatex,
    markdown as PandocMarkdown,
    reST as PandocReST,
)
from manuskript.exporter.page_routes import (
    ROUTE_SEPARATOR,
    page_renderer_route_id,
)
from manuskript.media_types import (
    BBCODE,
    DOCX,
    EPUB,
    HTML,
    LATEX,
    MARKDOWN,
    ODT,
    OPML,
    PDF as PDF_MEDIA_TYPE,
    PLAIN,
    RST,
    core_registry,
)


IN_MEMORY = (
    (plainText, PLAIN),
    (markdown, MARKDOWN),
    (BBCode, BBCODE),
    (ManuskriptHTML, HTML),
)

PROCESS_BACKED = (
    (PandocHTML, HTML, HTML),
    (PandocMarkdown, MARKDOWN, MARKDOWN),
    (PandocReST, RST, RST),
    (PandocLatex, LATEX, LATEX),
    (PandocBBCode, BBCODE, BBCODE),
    (PandocOPML, OPML, MARKDOWN),
    (PDF, PDF_MEDIA_TYPE, LATEX),
    (ePub, EPUB, HTML),
    (OpenDocument, ODT, MARKDOWN),
    (DocX, DOCX, MARKDOWN),
)


@pytest.mark.parametrize(
    "cls,media_type",
    IN_MEMORY + tuple((c, m) for c, m, _ in PROCESS_BACKED),
)
def test_every_exporter_names_a_format_core_declares(cls, media_type):
    assert cls.media_type == media_type
    assert core_registry().is_known(media_type)


@pytest.mark.parametrize("cls,_media_type", IN_MEMORY)
def test_in_memory_formats_can_feed_a_converter(cls, _media_type):
    assert cls.in_memory is True


@pytest.mark.parametrize("cls,_media,_repr", PROCESS_BACKED)
def test_process_backed_formats_cannot(cls, _media, _repr):
    # Pandoc shells out and may return bytes, so its output is not an
    # in-memory conversion source however textual the format is.
    assert cls.in_memory is False


@pytest.mark.parametrize("cls,_media_type,representation", PROCESS_BACKED)
def test_pages_are_composed_in_a_textual_representation(
        cls, _media_type, representation):
    registry = core_registry()

    assert cls(exporter()).pageRenderTarget() == representation
    # A destination may be binary; what pages are composed in may not.
    assert registry.get(representation).textual is True


def exporter():
    return SimpleNamespace(context=SimpleNamespace(page_types=None))


# ------------------------------------------------- pandoc's own vocabulary

def test_a_raw_block_is_labelled_with_pandocs_writer_name():
    rendered = PandocHTML(exporter()).processRenderedPageText(
        "<p>exact</p>", HTML, {},
    )

    # Not "{=text/html}", which pandoc would not recognise as a writer.
    assert "{=html}" in rendered
    assert "text/html" not in rendered


def test_every_writer_name_belongs_to_a_declared_media_type():
    registry = core_registry()

    for media_type in PANDOC_WRITERS:
        assert registry.is_known(media_type), media_type
        assert registry.get(media_type).textual is True


def test_a_format_pandoc_cannot_name_goes_in_as_ordinary_source():
    rendered = PandocHTML(exporter()).processRenderedPageText(
        "content", "application/x-fictionbook+xml", {},
    )

    # Better a plain fragment than a fence claiming a writer that does not
    # exist, which pandoc would fail on.
    assert rendered == "content\n"


# ------------------------------------------------------------ route naming

def test_routes_join_on_something_no_media_type_contains():
    route = page_renderer_route_id(EPUB, HTML)

    assert route == "application/epub+zip|text/html"
    assert route.split(ROUTE_SEPARATOR) == [EPUB, HTML]
    # Legacy keys used a colon, so old and new are told apart on sight.
    assert ":" not in route
