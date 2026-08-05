"""Binding a project needs named views, not a window to search.

The binding used to take a window and fish out models, trees, the
editor, the metadata panel, search and plugin state. With one window
"the outline tree" was unambiguous; with two, it is a question, and
these tests are written the way the binding now works -- the answers are
given to it, so none of this needs a window at all.
"""

import importlib
from unittest.mock import MagicMock, patch

import pytest

from manuskript.ui.project_context_binding import ProjectContextBinding
from manuskript.ui.project_view_set import ProjectViewSet

binding_module = importlib.import_module(
    "manuskript.ui.project_context_binding"
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
        settings=MagicMock(),
        card_styles=MagicMock(),
        undo_stack=MagicMock(),
        show_status=MagicMock(),
        page_types=lambda: page_types,
        outline_trees=(MagicMock(), MagicMock()),
        document_area=MagicMock(),
        metadata_panel=MagicMock(),
        item_editor=MagicMock(),
        storyline=MagicMock(),
        cheat_sheet=MagicMock(),
        search_view=MagicMock(),
        selection_changed=MagicMock(),
        open_index=MagicMock(),
        open_indexes=MagicMock(),
        text_editors=lambda: [text_editor],
        completers=lambda: [completer],
        navigation=MagicMock(),
        text_editor_context=lambda: text_context,
        result_views=lambda references: MagicMock(),
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

    with patch.object(
        binding_module,
        "ReferenceService",
        return_value=reference_service,
    ), patch.object(
        binding_module,
        "OutlineViewContext",
        return_value=outline_context,
    ), patch.object(
        binding_module,
        "EditorContext",
        return_value=editor_context,
    ), patch.object(
        binding_module.SearchContext,
        "from_models",
        return_value=search_context,
    ):
        binding = ProjectContextBinding(views)
        binding.bind(connect)

    assert binding.reference_service is reference_service
    assert binding.text_editor_context is text_context
    text_editor.set_text_editor_context.assert_called_once_with(
        text_context
    )
    views.document_area.set_context.assert_called_once_with(
        editor_context
    )
    # Every tree the set names, rather than two the binding knew about.
    for tree in views.outline_trees:
        tree.bind_project_model.assert_called_once_with(
            views.models.outline,
            outline_context,
        )
    completer.setReferenceService.assert_called_once()
    views.search_view.setContext.assert_called_once_with(search_context)

    binding.unbind()

    text_editor.set_text_editor_context.assert_called_with(None)
    completer.setReferenceService.assert_called_with(None)
    for tree in views.outline_trees:
        tree.unbind_project_model.assert_called_once_with()
    views.document_area.clear_context.assert_called_once_with()
    views.search_view.clearContext.assert_called_once_with()
    assert binding.reference_service is None
    assert binding.text_editor_context is None


def test_the_binding_reads_its_models_from_the_set():
    """The models are the project's, so they arrive with the views
    rather than being looked up on a window.
    """
    views = make_views()
    connect = MagicMock()

    with patch.object(
        binding_module, "ReferenceService", return_value=MagicMock(),
    ), patch.object(
        binding_module, "OutlineViewContext", return_value=MagicMock(),
    ), patch.object(
        binding_module, "EditorContext", return_value=MagicMock(),
    ), patch.object(
        binding_module.SearchContext, "from_models",
        return_value=MagicMock(),
    ):
        ProjectContextBinding(views).bind(connect)

    models = views.models
    views.metadata_panel.setModels.assert_called_once_with(
        models.outline,
        models.characters,
        models.labels,
        models.statuses,
        page_types=views.page_types(),
    )
    views.storyline.setModels.assert_called_once()
    views.cheat_sheet.setModels.assert_called_once()


def test_project_context_binding_rejects_double_binding():
    binding = ProjectContextBinding(make_views())
    binding.reference_service = MagicMock()

    with pytest.raises(RuntimeError, match="released"):
        binding.bind(MagicMock())
