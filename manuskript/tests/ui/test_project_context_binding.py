"""Binding a project needs named views, not a window to search.

The binding used to take a window and fish out models, trees, the
editor, the metadata panel, search and plugin state. With one window
"the outline tree" was unambiguous; with two, it is a question, and
these tests are written the way the binding now works -- the answers are
given to it, so none of this needs a window at all.

It also used to be one class holding all of them. These tests are about
the coordinator: the two objects the areas share, and the order.
"""

from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pytest

from manuskript.panels.core import EDITOR, OUTLINE
from manuskript.ui import project_context_binding as binding_module
from manuskript.ui.project_contexts import editors as editors_module
from manuskript.ui.project_contexts import search as search_module
from manuskript.ui.project_context_binding import ProjectContextBinding
from manuskript.ui.project_view_set import (
    EditorViews,
    MetadataViews,
    ProjectViewSet,
    ReferencePanelViews,
    SearchViews,
)


def make_views(text_editor=None, completer=None, text_context=None):
    text_editor = text_editor or MagicMock()
    completer = completer or MagicMock()
    # Stable values, so an assertion about what was passed compares the
    # same object rather than a fresh mock per call.
    page_types = MagicMock()
    text_context = text_context or MagicMock()
    return ProjectViewSet(
        models=MagicMock(),
        navigation=MagicMock(),
        editors=EditorViews(
            project_tree=MagicMock(),
            text_editor_context=lambda: text_context,
            open_index=MagicMock(),
            open_indexes=MagicMock(),
            selection_changed=MagicMock(),
            show_status=MagicMock(),
            settings=MagicMock(),
            card_styles=MagicMock(),
            undo_stack=MagicMock(),
        ),
        metadata=MetadataViews(
            panel=MagicMock(),
            page_types=lambda: page_types,
        ),
        reference_panels=ReferencePanelViews(
            storyline=MagicMock(),
            cheat_sheet=MagicMock(),
        ),
        search=SearchViews(
            view=MagicMock(),
            result_views=lambda references: MagicMock(),
        ),
    )


def patched_contexts(reference_service=None, outline_context=None,
                     editor_context=None, search_context=None):
    """Patch each context type where the binding that builds it names it."""
    return (
        patch.object(
            binding_module,
            "ReferenceService",
            return_value=reference_service or MagicMock(),
        ),
        patch.object(
            editors_module,
            "OutlineViewContext",
            return_value=outline_context or MagicMock(),
        ),
        patch.object(
            editors_module,
            "EditorContext",
            return_value=editor_context or MagicMock(),
        ),
        patch.object(
            search_module.SearchContext,
            "from_models",
            return_value=search_context or MagicMock(),
        ),
    )


def test_project_context_binding_installs_and_releases_contexts():
    text_editor = MagicMock()
    completer = MagicMock()
    text_context = MagicMock()
    views = make_views(text_editor, completer, text_context)
    reference_service = MagicMock()
    outline_context = MagicMock()
    editor_context = MagicMock()
    search_context = MagicMock()
    connect = MagicMock()

    references, outlines, editors, searches = patched_contexts(
        reference_service, outline_context, editor_context, search_context,
    )
    editor_panel = MagicMock()
    editor_panel.findChildren.side_effect = lambda widget_type: (
        [text_editor]
        if widget_type.__name__ == "textEditView"
        else [completer]
    )
    editor_surface = SimpleNamespace(id=EDITOR, widget=editor_panel)
    outline_surface = SimpleNamespace(id=OUTLINE, widget=MagicMock())
    with references, outlines, editors, searches:
        binding = ProjectContextBinding(views)
        binding.bind(connect)
        binding.attach_surface(outline_surface)
        binding.attach_surface(editor_surface)

    assert binding.reference_service is reference_service
    assert binding.text_editor_context is text_context
    text_editor.set_text_editor_context.assert_called_once_with(
        text_context
    )
    editor_panel.editor.set_context.assert_called_once_with(
        editor_context
    )
    views.editors.project_tree.bind_project_model.assert_called_once_with(
        views.models.outline,
        outline_context,
    )
    (
        outline_surface.widget.treeOutlineOutline.bind_project_model
        .assert_called_once_with(views.models.outline, outline_context)
    )
    completer.setReferenceService.assert_called_once()
    views.search.view.setContext.assert_called_once_with(search_context)

    binding.unbind()

    text_editor.set_text_editor_context.assert_called_with(None)
    completer.setReferenceService.assert_called_with(None)
    views.editors.project_tree.unbind_project_model.assert_called_once_with()
    (
        outline_surface.widget.treeOutlineOutline.unbind_project_model
        .assert_called_once_with()
    )
    editor_panel.editor.clear_context.assert_called_once_with()
    views.search.view.clearContext.assert_called_once_with()
    assert binding.reference_service is None
    assert binding.text_editor_context is None


def test_the_binding_reads_its_models_from_the_set():
    """The models are the project's, so they arrive with the views
    rather than being looked up on a window.
    """
    views = make_views()
    connect = MagicMock()

    references, outlines, editors, searches = patched_contexts()
    with references, outlines, editors, searches:
        ProjectContextBinding(views).bind(connect)

    models = views.models
    views.metadata.panel.setModels.assert_called_once_with(
        models.outline,
        models.characters,
        models.labels,
        models.statuses,
        page_types=views.metadata.page_types(),
    )
    views.reference_panels.storyline.setModels.assert_called_once()
    views.reference_panels.cheat_sheet.setModels.assert_called_once()


def test_each_area_is_handed_only_its_own_views():
    """The whole point of the split. A binding that cannot name the
    metadata panel cannot come to depend on it -- and the coordinator is
    the only thing holding the set entire.
    """
    views = make_views()

    binding = ProjectContextBinding(views)

    assert binding.editors.views is views.editors
    assert binding.metadata.views is views.metadata
    assert binding.reference_panels.views is views.reference_panels
    assert binding.search.views is views.search
    # The models are the project's and every area reads them.
    for area in (
        binding.editors,
        binding.metadata,
        binding.reference_panels,
        binding.search,
    ):
        assert area.models is views.models


def test_the_reference_service_is_built_from_the_projects_models():
    """Made of models and shared by two of the areas, so the coordinator
    builds it rather than any one panel.
    """
    views = make_views()
    service = MagicMock()

    references, outlines, editors, searches = patched_contexts(service)
    with references, outlines, editors, searches:
        binding = ProjectContextBinding(views)
        binding.bind(MagicMock())

        reference_models = binding_module.ReferenceService.call_args[0][0]
        assert (
            binding_module.ReferenceService.call_args[0][1]
            is views.navigation
        )
        presentation = binding_module.ReferenceService.call_args[0][2]

    assert binding.reference_service is service
    assert reference_models.outline is views.models.outline
    assert reference_models.labels is views.models.labels
    assert presentation.models is reference_models
    # Both areas that resolve references got the one service.
    views.reference_panels.storyline.setModels.assert_called_once()
    assert service in (
        views.reference_panels.storyline.setModels.call_args[0]
    )


def test_project_context_binding_rejects_double_binding():
    binding = ProjectContextBinding(make_views())
    binding.reference_service = MagicMock()

    with pytest.raises(RuntimeError, match="released"):
        binding.bind(MagicMock())
