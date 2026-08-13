from unittest.mock import MagicMock, call

import pytest

from manuskript.enums import Model
from manuskript.models import references
from manuskript.panels.core import CHARACTER_ENTITIES
from manuskript.ui.highlighters.searchResultHighlighters.searchResultHighlighter import (
    searchResultHighlighter,
)
from manuskript.ui.search_context import (
    SearchContext,
    SearchResultViewAdapter,
    SearchResultViews,
)


def search_result(model_type, model_id="7", positions=None):
    result = MagicMock()
    result.type.return_value = model_type
    result.id.return_value = model_id
    result.pos.return_value = positions or [(2, 5)]
    return result


def test_search_context_exposes_project_sources_in_search_order():
    models = [MagicMock() for _ in range(5)]
    context = SearchContext.from_models(
        outline=models[0],
        characters=models[1],
        flat_data=models[2],
        world=models[3],
        plots=models[4],
        result_views=MagicMock(),
    )

    sources = context.sources()

    assert [model_type for _, model_type in sources] == [
        Model.Outline,
        Model.Character,
        Model.FlatData,
        Model.World,
        Model.Plot,
    ]
    assert sources[0][0] is models[0]
    assert sources[1][0] is models[1]
    assert sources[2][0].qstandardItemModel is models[2]
    assert sources[3][0] is models[3]
    assert sources[4][0] is models[4]


@pytest.mark.parametrize(
    "model_type, expected_reference",
    [
        (Model.Character, references.characterReference("7")),
        (Model.Outline, references.textReference("7")),
        (Model.World, references.worldReference("7")),
        (Model.Plot, references.plotReference("7")),
        (Model.PlotStep, references.plotReference("7")),
    ],
)
def test_result_adapter_routes_reference_navigation(
    model_type,
    expected_reference,
):
    window = MagicMock()
    reference_service = MagicMock()
    adapter = SearchResultViewAdapter(
        SearchResultViews.for_window(window),
        reference_service,
    )

    adapter.open_result(search_result(model_type))

    reference_service.open.assert_called_once_with(expected_reference)


def test_result_adapter_opens_flat_data_without_reference_navigation():
    window = MagicMock()
    reference_service = MagicMock()
    adapter = SearchResultViewAdapter(
        SearchResultViews.for_window(window),
        reference_service,
    )

    adapter.open_result(search_result(Model.FlatData))

    window.entityWorkspace.open.assert_called_once_with("project:summary")
    reference_service.open.assert_not_called()


def test_result_adapter_has_no_main_window_escape_hatch():
    views = MagicMock()
    adapter = SearchResultViewAdapter(views, MagicMock())

    assert adapter.views is views
    assert not hasattr(adapter, "window")


def test_result_highlighter_uses_one_context_for_opening_and_selection():
    first_widget = MagicMock()
    second_widget = MagicMock()
    context = MagicMock()
    context.widgets_for.return_value = [first_widget, second_widget]
    result = search_result(
        Model.PlotStep,
        positions=[(1, 2), (8, 13)],
    )
    highlighter = searchResultHighlighter()
    highlighter.setContext(context)
    highlighter._selection = MagicMock()

    highlighter.highlightSearchResult(result)

    context.open_result.assert_called_once_with(result)
    context.widgets_for.assert_called_once_with(result)
    assert highlighter._selection.highlight_widget_selection.call_args_list == [
        call(first_widget, 1, 2, False),
        call(second_widget, 8, 13, True),
    ]


def test_result_highlighter_rejects_use_without_project_context():
    highlighter = searchResultHighlighter()

    with pytest.raises(RuntimeError, match="not been configured"):
        highlighter.highlightSearchResult(search_result(Model.Outline))


def test_project_search_context_opens_and_highlights_character(
    MWSampleProject,
):
    window = MWSampleProject
    search_widget = window.widget
    search_widget.searchTextInput.setText("Peter")

    search_widget.search()
    matches = [
        search_widget.result.item(row)
        for row in range(search_widget.result.count())
        if search_widget.result.item(row).text() == "Peter"
    ]
    assert matches

    search_widget.openItem(matches[0])

    # Search reaches the same browser-owned detail workflow as a list row.
    editor = window.entityWorkspace.current_editor()
    assert editor is not None
    assert editor.titleEdit.selectedText() == "Peter"
    assert not window.panelHost.instance(
        CHARACTER_ENTITIES
    ).container.isHidden()
