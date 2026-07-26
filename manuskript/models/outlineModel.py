#!/usr/bin/env python
# --!-- coding: utf8 --!--

from contextlib import contextmanager

from manuskript.models.abstractModel import abstractModel
from manuskript.models.searchableModel import searchableModel
from manuskript.models.outlineItem import outlineItem
from manuskript.models.outline_search_context import OutlineSearchContext
from manuskript.models.outline_settings import DefaultOutlineSettings


class outlineModel(abstractModel, searchableModel):
    def __init__(self, parent=None, search_context=None, settings=None):
        abstractModel.__init__(self, parent)
        self.search_context = search_context or OutlineSearchContext()
        self.settings = (
            settings
            if settings is not None
            else DefaultOutlineSettings()
        )
        self.rootItem = outlineItem(
            model=self,
            title="Root",
            ID="0",
            settings=self.settings,
        )
        self._word_count_batch_depth = 0
        self._word_count_dirty = False

    @property
    def wordCountUpdatesDeferred(self):
        return self._word_count_batch_depth > 0

    def deferWordCountUpdate(self):
        self._word_count_dirty = True

    @contextmanager
    def batchWordCountUpdates(self):
        """Defer aggregate word counts until a model mutation completes."""
        self._word_count_batch_depth += 1
        try:
            yield
        finally:
            self._word_count_batch_depth -= 1
            if (
                self._word_count_batch_depth == 0
                and self._word_count_dirty
            ):
                self._word_count_dirty = False
                self.rootItem.recalculateWordCount(recursive=True)


    def findItemsByPOV(self, POV):
        "Returns a list of IDs of all items whose POV is ``POV``."
        return self.rootItem.findItemsByPOV(POV)

    def searchableItems(self):
        result = []

        for child in self.rootItem.children():
            result += self._searchableItems(child)

        return result

    def _searchableItems(self, item):
        result = [item]

        for child in item.children():
            result += self._searchableItems(child)

        return result
