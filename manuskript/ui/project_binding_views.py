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

    general_fields: Tuple[FieldBinding, ...]


@dataclass(frozen=True)
class OutlineSelectionBindingViews:
    """The two outline selections and the consumers they drive."""

    outline_tree: Any
    project_tree: Any
    outline_item_editor: Any
    metadata: Any
    document_area: Any
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

    @classmethod
    def for_window(cls, window):
        return cls(
            flat_data=FlatDataBindingViews(
                general_fields=(
                    (window.txtGeneralTitle, 0),
                    (window.txtGeneralSubtitle, 1),
                    (window.txtGeneralSerie, 2),
                    (window.txtGeneralVolume, 3),
                    (window.txtGeneralGenre, 4),
                    (window.txtGeneralLicense, 5),
                    (window.txtGeneralAuthor, 6),
                    (window.txtGeneralEmail, 7),
                ),
            ),
            outline_selection=OutlineSelectionBindingViews(
                outline_tree=window.treeOutlineOutline,
                project_tree=window.corePanels.project_tree.tree,
                outline_item_editor=window.outlineItemEditor,
                metadata=window.corePanels.metadata,
                document_area=window.mainEditor,
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
        )
