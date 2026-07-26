from manuskript.ui.highlighters.searchResultHighlighters.widgetSelectionHighlighter import (
    widgetSelectionHighlighter,
)


class searchResultHighlighter:
    def __init__(self):
        self._context = None
        self._selection = widgetSelectionHighlighter()

    def setContext(self, context):
        self._context = context

    def highlightSearchResult(self, searchResult):
        if self._context is None:
            raise RuntimeError("Search result context has not been configured.")

        self._context.open_result(searchResult)
        widgets = self._context.widgets_for(searchResult)
        for index, widget in enumerate(widgets):
            start, end = searchResult.pos()[index]
            self._selection.highlight_widget_selection(
                widget,
                start,
                end,
                index == len(widgets) - 1,
            )
