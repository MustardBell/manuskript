"""Explicit widget contracts for the project binding lifecycle.

These are the stable widgets that survive project replacement.  Models are
deliberately absent: the runtime replaces its model set whenever another
project is opened, so bindings resolve models from the runtime at bind time.

Only :meth:`ProjectBindingViews.for_window` knows that the widgets happen to
live on a ``MainWindow``.  The binding objects receive the narrow group they
need and cannot reach unrelated actions, services, or plugin state.
"""

from dataclasses import dataclass
from typing import Any, Callable, Tuple


FieldBinding = Tuple[Any, int]


@dataclass(frozen=True)
class FlatDataBindingViews:
    """Project-level publication metadata fields."""

    fields_for_surface: Callable[[Any], Tuple[FieldBinding, ...]]


@dataclass(frozen=True)
class OutlineSelectionBindingViews:
    """The two outline selections and the consumers they drive."""

    outline_selection: Any
    project_tree_clicked: Any
    metadata: Any
    outline_changed: Callable[..., None]
    project_tree_changed: Callable[..., None]


@dataclass(frozen=True)
class DebugBindingViews:
    """Optional raw model views on the debug tab."""

    flat_data: Any
    characters: Any
    character_info: Any
    plots: Any
    plot_characters: Any
    plot_steps: Any
    world: Any
    outline: Any
    labels: Any
    statuses: Any


@dataclass(frozen=True)
class ProjectBindingViews:
    """One window's persistent views, grouped by project binding."""

    flat_data: FlatDataBindingViews
    outline_selection: OutlineSelectionBindingViews
    debug: DebugBindingViews
    surface_instances: Callable[[], Tuple[Any, ...]]

    @classmethod
    def for_window(cls, window):
        project_tree = window.corePanels.optional_tool("project_tree")
        def general_fields(instance):
            panel = instance.widget
            return (
                (panel.title, 0),
                (panel.subtitle, 1),
                (panel.series, 2),
                (panel.volume, 3),
                (panel.genre, 4),
                (panel.license, 5),
                (panel.author, 6),
                (panel.email, 7),
            )

        return cls(
            flat_data=FlatDataBindingViews(
                fields_for_surface=general_fields,
            ),
            outline_selection=OutlineSelectionBindingViews(
                outline_selection=window.outlineSelection,
                project_tree_clicked=(
                    project_tree.tree.clicked
                    if project_tree is not None else None
                ),
                metadata=window.corePanels.optional_tool("metadata"),
                outline_changed=(
                    window.workspaceSelection.outline_selection_changed
                ),
                project_tree_changed=(
                    window.workspaceSelection.project_selection_changed
                ),
            ),
            debug=DebugBindingViews(
                flat_data=window.tblDebugFlatData,
                characters=window.tblDebugPersos,
                character_info=window.tblDebugPersosInfos,
                plots=window.tblDebugPlots,
                plot_characters=window.tblDebugPlotsPersos,
                plot_steps=window.tblDebugSubPlots,
                world=window.treeDebugWorld,
                outline=window.treeDebugOutline,
                labels=window.lstDebugLabels,
                statuses=window.lstDebugStatus,
            ),
            surface_instances=lambda: tuple(
                window.surfaceHost.instances.values()
            ),
        )
