from manuskript.enums import Outline
from manuskript.models import outlineItem
from manuskript.services.frequency_analysis import (
    phrase_frequencies,
    word_frequencies,
)


def make_outline():
    root = outlineItem(title="Root")
    first = outlineItem(
        title="One",
        _type="md",
        parent=root,
    )
    first.setData(Outline.text, "Blue sky, blue sea.")
    folder = outlineItem(title="Folder", parent=root)
    second = outlineItem(
        title="Two",
        _type="md",
        parent=folder,
    )
    second.setData(Outline.text, "Blue sky forever.")
    return root


def test_word_frequencies_walk_nested_outline_and_filter_words():
    frequencies = word_frequencies(
        make_outline(),
        minimum_length=4,
        excluded=["forever"],
    )

    assert frequencies == {
        "blue": 3,
    }


def test_phrase_frequencies_do_not_span_outline_items():
    frequencies = phrase_frequencies(
        make_outline(),
        minimum_words=2,
        maximum_words=2,
    )

    assert frequencies[("Blue", "sky")] == 2
    assert frequencies[("sea", "Blue")] == 0
