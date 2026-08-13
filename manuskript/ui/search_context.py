from dataclasses import dataclass
from functools import partial
from types import MappingProxyType
from typing import Any, Callable, Mapping

from manuskript.enums import (
    Character,
    FlatData,
    Model,
    Outline,
    Plot,
    World,
)
from manuskript.models.reference_identity import (
    character_reference,
    plot_reference,
    text_reference,
    world_reference,
)
from manuskript.models.flatDataModelWrapper import flatDataModelWrapper
from manuskript.panels.core import METADATA


@dataclass(frozen=True)
class SearchContext:
    """Project-scoped search models and result presentation."""

    outline: object
    characters: object
    flat_data: object
    world: object
    plots: object
    result_views: object

    @classmethod
    def from_models(
        cls,
        outline,
        characters,
        flat_data,
        world,
        plots,
        result_views,
    ):
        return cls(
            outline=outline,
            characters=characters,
            flat_data=flatDataModelWrapper(flat_data),
            world=world,
            plots=plots,
            result_views=result_views,
        )

    def sources(self):
        return (
            (self.outline, Model.Outline),
            (self.characters, Model.Character),
            (self.flat_data, Model.FlatData),
            (self.world, Model.World),
            (self.plots, Model.Plot),
        )


@dataclass(frozen=True)
class SearchResultViews:
    """Widgets search results may reveal or highlight in one workspace."""

    entity_workspace: Any
    metadata_fields: Mapping[int, Any]
    current_document_text: Callable[[], Any]
    show_metadata: Callable[[], None]

    @classmethod
    def for_window(cls, window):
        metadata = window.corePanels.metadata
        properties = metadata.properties
        main_editor = window.corePanels.editor.editor
        panel_host = window.panelHost
        return cls(
            entity_workspace=window.entityWorkspace,
            metadata_fields=MappingProxyType({
                Outline.title: properties.txtTitle,
                Outline.summarySentence: metadata.txtSummarySentence,
                Outline.summaryFull: metadata.txtSummaryFull,
                Outline.notes: metadata.txtNotes,
                Outline.POV: properties.lblPOV,
                Outline.status: properties.lblStatus,
                Outline.label: properties.lblLabel,
            }),
            current_document_text=lambda: (
                main_editor.currentEditor().txtRedacText
            ),
            show_metadata=partial(panel_host.set_visible, METADATA),
        )


class SearchResultViewAdapter:
    """Expose search-result UI operations without global window lookup."""

    def __init__(self, views, reference_service):
        self.views = views
        self.references = reference_service

    def open_result(self, result):
        handlers = {
            Model.Character: self._open_character,
            Model.FlatData: self._open_flat_data,
            Model.Outline: self._open_outline,
            Model.World: self._open_world,
            Model.Plot: self._open_plot,
            Model.PlotStep: self._open_plot,
        }
        handler = handlers.get(result.type())
        if handler is None:
            raise NotImplementedError(
                "Unsupported search result type: {}".format(result.type())
            )
        handler(result)

    def widgets_for(self, result):
        handlers = {
            Model.Character: self._character_widgets,
            Model.FlatData: self._flat_data_widgets,
            Model.Outline: self._outline_widgets,
            Model.World: self._world_widgets,
            Model.Plot: self._plot_widgets,
            Model.PlotStep: self._plot_step_widgets,
        }
        handler = handlers.get(result.type())
        if handler is None:
            raise NotImplementedError(
                "Unsupported search result type: {}".format(result.type())
            )
        widgets = handler(result)
        return widgets if isinstance(widgets, list) else [widgets]

    def _open_character(self, result):
        self.references.open(character_reference(result.id()))

    def _open_flat_data(self, _result):
        self.views.entity_workspace.open("project:summary")

    def _open_outline(self, result):
        self.references.open(text_reference(result.id()))

    def _open_world(self, result):
        self.references.open(world_reference(result.id()))

    def _open_plot(self, result):
        self.references.open(plot_reference(result.id()))

    def _character_widgets(self, result):
        editor = self._entity_editor()
        if result.column() == Character.name:
            return editor.titleEdit
        if result.column() == Character.notes:
            return editor.bodyEdit
        return editor.propertiesTable

    def _flat_data_widgets(self, result):
        editor = self._entity_editor()
        if result.column() == FlatData.summaryFull:
            return editor.bodyEdit
        return editor.propertiesTable

    def _outline_widgets(self, result):
        if result.column() != Outline.text:
            # Through the panel's own action, so the toolbar button that
            # mirrors it stays in agreement.
            self.views.show_metadata()
            return self.views.metadata_fields[result.column()]
        return self.views.current_document_text()

    def _world_widgets(self, result):
        editor = self._entity_editor()
        if result.column() == World.name:
            return editor.titleEdit
        if result.column() == World.description:
            return editor.bodyEdit
        return editor.propertiesTable

    def _plot_widgets(self, result):
        editor = self._entity_editor()
        if result.column() == Plot.name:
            return editor.titleEdit
        if result.column() == Plot.description:
            return editor.bodyEdit
        return editor.propertiesTable

    def _plot_step_widgets(self, result):
        return self._entity_editor().propertiesTable

    def _entity_editor(self):
        """The form the last opened entity is being edited in.

        Each browser edits in its own half, so which one that is depends
        on what was opened rather than on one editor everything shares.
        """
        editor = self.views.entity_workspace.current_editor()
        if editor is None:
            raise RuntimeError("Entity search result did not open an editor.")
        return editor
