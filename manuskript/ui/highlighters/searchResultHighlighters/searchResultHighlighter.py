#!/usr/bin/env python
# --!-- coding: utf8 --!--

from manuskript.ui.highlighters.searchResultHighlighters.abstractSearchResultHighlighter import abstractSearchResultHighlighter
from manuskript.ui.highlighters.searchResultHighlighters.characterSearchResultHighlighter import characterSearchResultHighlighter
from manuskript.ui.highlighters.searchResultHighlighters.flatDataSearchResultHighlighter import flatDataSearchResultHighlighter
from manuskript.ui.highlighters.searchResultHighlighters.outlineSearchResultHighlighter import outlineSearchResultHighlighter
from manuskript.ui.highlighters.searchResultHighlighters.worldSearchResultHighlighter import worldSearchResultHighlighter
from manuskript.ui.highlighters.searchResultHighlighters.plotSearchResultHighlighter import plotSearchResultHighlighter
from manuskript.ui.highlighters.searchResultHighlighters.plotStepSearchResultHighlighter import plotStepSearchResultHighlighter
from manuskript.enums import Model


class searchResultHighlighter(abstractSearchResultHighlighter):
    def __init__(self):
        super().__init__()
        self._reference_service = None

    def setReferenceService(self, reference_service):
        self._reference_service = reference_service

    def highlightSearchResult(self, searchResult):
        if searchResult.type() == Model.Character:
            highlighter = characterSearchResultHighlighter(
                self._reference_service
            )
        elif searchResult.type() == Model.FlatData:
            highlighter = flatDataSearchResultHighlighter()
        elif searchResult.type() == Model.Outline:
            highlighter = outlineSearchResultHighlighter(
                self._reference_service
            )
        elif searchResult.type() == Model.World:
            highlighter = worldSearchResultHighlighter(
                self._reference_service
            )
        elif searchResult.type() == Model.Plot:
            highlighter = plotSearchResultHighlighter(
                self._reference_service
            )
        elif searchResult.type() == Model.PlotStep:
            highlighter = plotStepSearchResultHighlighter(
                self._reference_service
            )
        else:
            raise NotImplementedError

        highlighter.highlightSearchResult(searchResult)
