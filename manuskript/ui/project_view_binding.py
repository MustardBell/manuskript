from manuskript import functions as F
from manuskript.enums import Character, Plot


class FlatDataProjectBinding:
    """Bind general-information and summary fields to flat project data."""

    def __init__(self, views, runtime):
        self.views = views
        self._runtime = runtime

    @property
    def models(self):
        """The project's models, from the runtime that owns them."""
        return self._runtime.models

    def bind(self, _connect):
        models = self.models
        for widget, column in self.views.summary_fields:
            widget.setModel(models.flat_data)
            widget.setColumn(column)
            widget.setCurrentModelIndex(
                models.flat_data.index(1, column)
            )

        for widget, column in self.views.general_fields:
            widget.setModel(models.flat_data)
            widget.setColumn(column)
            widget.setCurrentModelIndex(
                models.flat_data.index(0, column)
            )


class OutlineSelectionProjectBinding:
    """Route outline selections to their project-scoped consumers."""

    def __init__(self, views):
        self.views = views

    def bind(self, connect):
        views = self.views
        outline_selection = views.outline_tree.selectionModel()
        project_selection = views.project_tree.selectionModel()
        for signal, slot in [
            (
                outline_selection.selectionChanged,
                views.outline_changed,
            ),
            (
                outline_selection.selectionChanged,
                views.outline_item_editor.selectionChanged,
            ),
            (
                views.outline_tree.clicked,
                views.outline_item_editor.selectionChanged,
            ),
            (
                project_selection.selectionChanged,
                views.project_tree_changed,
            ),
            (
                project_selection.selectionChanged,
                views.metadata.selectionChanged,
            ),
            (
                views.project_tree.clicked,
                views.metadata.selectionChanged,
            ),
            (
                project_selection.selectionChanged,
                views.document_area.selectionChanged,
            ),
        ]:
            connect(signal, slot, F.AUC)


class DebugProjectBinding:
    """Bind the optional debug views to the active project models."""

    def __init__(self, views, runtime):
        self.views = views
        self._runtime = runtime

    @property
    def models(self):
        """The project's models, from the runtime that owns them."""
        return self._runtime.models

    def bind(self, connect):
        views = self.views
        models = self.models
        models.flat_data.setVerticalHeaderLabels(
            ["General info", "Summary"]
        )
        views.flat_data.setModel(models.flat_data)
        views.characters.setModel(models.characters)
        views.character_info.setModel(models.characters)
        connect(
            views.characters.selectionModel().currentChanged,
            self._show_current_character,
            F.AUC,
        )

        views.plots.setModel(models.plots)
        views.plot_characters.setModel(models.plots)
        views.plot_steps.setModel(models.plots)
        connect(
            views.plots.selectionModel().currentChanged,
            self._show_current_plot_characters,
            F.AUC,
        )
        connect(
            views.plots.selectionModel().currentChanged,
            self._show_current_plot_steps,
            F.AUC,
        )
        views.world.setModel(models.world)
        views.outline.setModel(models.outline)
        views.labels.setModel(models.labels)
        views.statuses.setModel(models.statuses)

    def _show_current_character(self, *_args):
        views = self.views
        models = self.models
        views.character_info.setRootIndex(
            models.characters.index(
                views.characters.selectionModel().currentIndex().row(),
                Character.name,
            )
        )

    def _show_current_plot_characters(self, *_args):
        views = self.views
        models = self.models
        views.plot_characters.setRootIndex(
            models.plots.index(
                views.plots.selectionModel().currentIndex().row(),
                Plot.characters,
            )
        )

    def _show_current_plot_steps(self, *_args):
        views = self.views
        models = self.models
        views.plot_steps.setRootIndex(
            models.plots.index(
                views.plots.selectionModel().currentIndex().row(),
                Plot.steps,
            )
        )
