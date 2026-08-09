from unittest.mock import MagicMock

import pytest

from manuskript.ui.summary_word_counts import (
    SummaryWordCountController,
    SummaryWordCountField,
    SummaryWordCountViews,
)


def _views(text="One two", estimate_pages=False):
    editor = MagicMock()
    editor.toPlainText.return_value = text
    label = MagicMock()
    return SummaryWordCountViews(
        fields=(
            SummaryWordCountField(
                editor,
                label,
                estimate_pages=estimate_pages,
            ),
        ),
        translate=lambda value: value,
    ), editor, label


def test_binding_connects_and_initializes_each_count():
    views, editor, label = _views("One two three")
    controller = SummaryWordCountController(views)

    controller.bind()

    editor.textChanged.connect.assert_called_once()
    label.setText.assert_called_once_with("Words: 3")


def test_long_summary_includes_the_existing_page_estimate():
    views, _editor, label = _views("word " * 251, estimate_pages=True)
    controller = SummaryWordCountController(views)

    controller.update(0)

    label.setText.assert_called_once_with("Words: 251 (~1.0 pages)")


def test_binding_twice_is_rejected():
    views, _editor, _label = _views()
    controller = SummaryWordCountController(views)
    controller.bind()

    with pytest.raises(RuntimeError, match="only be bound once"):
        controller.bind()


def test_dispose_releases_connections_and_views():
    views, editor, _label = _views()
    controller = SummaryWordCountController(views)
    controller.bind()
    slot = editor.textChanged.connect.call_args.args[0]

    controller.dispose()

    editor.textChanged.disconnect.assert_called_once_with(slot)
    assert controller._views is None


def test_real_summary_text_updates_its_count_label(MWEmptyProject):
    window = MWEmptyProject

    window.txtSummarySentence.setPlainText("One two three four")

    assert window.lblSummaryWCSentence.text() == window.tr(
        "Words: {}{}"
    ).format(4, "")
