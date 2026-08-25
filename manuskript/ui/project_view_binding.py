from manuskript import functions as F
from manuskript.enums import Character, Plot
from manuskript.panels.core import EDITOR, GENERAL, OUTLINE
from manuskript.ui.connections import SignalConnectionRegistry


class FlatDataProjectBinding:
    """Bind general publication fields to the compatibility model."""

    def __init__(self, views, runtime):
        self.views = views
        self._runtime = runtime
        self.bound = False

    @property
    def models(self):
        """The project's models, from the runtime that owns them."""
        return self._runtime.models

    def bind(self, _connect):
        self.bound = True

    def attach_surface(self, instance):
        if not self.bound or instance.id != GENERAL:
            return
        models = self.models
        for widget, column in self.views.fields_for_surface(instance):
            widget.setModel(models.flat_data)
            widget.setColumn(column)
            widget.setCurrentModelIndex(
                models.flat_data.index(0, column)
            )

    def detach_surface(self, instance):
        # These fields have no signal subscriptions of their own. The next
        # workspace/project binding points them at the authoritative model.
        pass

    def unbind(self):
        self.bound = False


class OutlineSelectionProjectBinding:
    """Route outline selections to their project-scoped consumers."""

    def __init__(self, views):
        self.views = views
        self.bound = False
        self._surface_connections = {}

    def bind(self, connect):
        views = self.views
        project_selection = views.outline_selection.selectionModel()
        connections = [(
            project_selection.selectionChanged,
            views.project_tree_changed,
        )]
        if views.metadata is not None:
            connections.extend((
                (
                    project_selection.selectionChanged,
                    views.metadata.selectionChanged,
                ),
            ))
            if views.project_tree_clicked is not None:
                connections.append((
                    views.project_tree_clicked,
                    views.metadata.selectionChanged,
                ))
        for signal, slot in connections:
            connect(signal, slot, F.AUC)
        self.bound = True

    def attach_surface(self, instance):
        if not self.bound or instance.id not in (OUTLINE, EDITOR):
            return
        connections = SignalConnectionRegistry()
        views = self.views
        if instance.id == OUTLINE:
            panel = instance.widget
            selection = panel.treeOutlineOutline.selectionModel()
            connections.connect(
                selection.selectionChanged,
                views.outline_changed,
                F.AUC,
            )
            connections.connect(
                selection.selectionChanged,
                panel.outlineItemEditor.selectionChanged,
                F.AUC,
            )
            connections.connect(
                panel.treeOutlineOutline.clicked,
                panel.outlineItemEditor.selectionChanged,
                F.AUC,
            )
        else:
            connections.connect(
                views.outline_selection.selectionModel().selectionChanged,
                instance.widget.editor.selectionChanged,
                F.AUC,
            )
        self._surface_connections[instance.id] = connections

    def detach_surface(self, instance):
        connections = self._surface_connections.pop(instance.id, None)
        if connections is not None:
            connections.disconnect_all()

    def unbind(self):
        for connections in self._surface_connections.values():
            connections.disconnect_all()
        self._surface_connections.clear()
        self.bound = False


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
