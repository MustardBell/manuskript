"""Word-count presentation for the project summary fields."""

from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, Tuple

from manuskript.functions import wordCount
from manuskript.ui.connections import SignalConnectionRegistry


@dataclass(frozen=True)
class SummaryWordCountField:
    editor: Any
    label: Any
    estimate_pages: bool = False


@dataclass(frozen=True)
class SummaryWordCountViews:
    fields: Tuple[SummaryWordCountField, ...]
    translate: Callable[[str], str]

    @classmethod
    def for_window(cls, window):
        return cls(
            fields=(
                SummaryWordCountField(
                    window.txtSummarySentence,
                    window.lblSummaryWCSentence,
                ),
                SummaryWordCountField(
                    window.txtSummaryPara,
                    window.lblSummaryWCPara,
                ),
                SummaryWordCountField(
                    window.txtSummaryPage,
                    window.lblSummaryWCPage,
                    estimate_pages=True,
                ),
                SummaryWordCountField(
                    window.txtSummaryFull,
                    window.lblSummaryWCFull,
                    estimate_pages=True,
                ),
            ),
            translate=window.tr,
        )


class SummaryWordCountController:
    """Keep each summary field's count label synchronized."""

    def __init__(self, views):
        self._views = views
        self._connections = SignalConnectionRegistry()
        self._bound = False

    def bind(self):
        if self._bound:
            raise RuntimeError("Summary word counts may only be bound once.")
        for index, field in enumerate(self._views.fields):
            self._connections.connect_weak(
                field.editor.textChanged,
                partial(self.update, index),
            )
            self.update(index)
        self._bound = True

    def update(self, index):
        field = self._views.fields[index]
        count = wordCount(field.editor.toPlainText())
        pages = (
            self._views.translate(" (~{} pages)").format(
                int(count / 25) / 10.0
            )
            if field.estimate_pages
            else ""
        )
        field.label.setText(
            self._views.translate("Words: {}{}").format(count, pages)
        )

    def dispose(self):
        self._connections.disconnect_all()
        self._views = None
        self._bound = False
