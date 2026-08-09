"""What a document file holds is what somebody wrote, not what follows.

A word count is derived from the text by definition: it cannot disagree
with the text without being wrong, and recomputing it costs less than the
save that would have stored it. Writing it down buys nothing and costs a
changed header line in the diff of every document anybody types in.

charCount was written to every file anyway, and it was never read. Loading
sets the metadata first and the text last, and setting text recomputes both
counts -- so the number from the file was overwritten before anything could
consult it. This pins that it stays out, and that its neighbours which were
already out stay out too.
"""

from manuskript.enums import Outline
from manuskript.load_save.version_1 import outlineToMMD
from manuskript.models.outlineItem import outlineItem
from manuskript.models.outline_settings import DefaultOutlineSettings


#: Every field that follows from the text rather than standing beside it.
DERIVED = (
    Outline.wordCount,
    Outline.charCount,
    Outline.goalPercentage,
)


def a_scene(text="Two words here, and several more after that."):
    item = outlineItem(
        title="Scene", _type="md", settings=DefaultOutlineSettings(),
    )
    item.setData(Outline.text, text)
    return item


def header_of(content):
    """The metadata block: everything before the blank line."""
    lines = []
    for line in content.splitlines():
        if not line.strip():
            break
        lines.append(line)
    return lines


def test_a_saved_document_carries_no_derived_field():
    item = a_scene()
    # Derived and non-zero, so their absence below is a decision rather
    # than an empty value being skipped.
    assert item.data(Outline.wordCount)
    assert item.data(Outline.charCount)

    header = header_of(outlineToMMD(item))

    for field in DERIVED:
        assert not any(
            line.startswith("{}:".format(field.name)) for line in header
        ), field.name


def test_a_saved_document_still_carries_what_somebody_chose():
    """The counterpart: this must not become a test that everything is
    excluded. Title, kind and compile are answers, not consequences.
    """
    item = a_scene()

    header = header_of(outlineToMMD(item))

    for field in ("title", "type", "compile"):
        assert any(
            line.startswith("{}:".format(field)) for line in header
        ), field


def test_the_text_survives_being_saved():
    item = a_scene("Two words here, and several more after that.")

    content = outlineToMMD(item)

    assert content.endswith("Two words here, and several more after that.")


def test_a_count_from_an_older_file_is_replaced_by_the_truth():
    """Projects written before this still carry charCount, and loading one
    sets it. It has to lose to the text, which is what already happens:
    metadata first, text last, text recomputes.
    """
    item = outlineItem(
        title="Scene", _type="md", settings=DefaultOutlineSettings(),
    )

    item.setData(Outline.charCount, "999999")
    item.setData(Outline.text, "Four words in total.")

    assert item.data(Outline.charCount) != "999999"
    assert int(item.data(Outline.charCount)) == len("Four words in total.")
    assert int(item.data(Outline.wordCount)) == 4
