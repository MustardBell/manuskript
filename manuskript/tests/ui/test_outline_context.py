from unittest.mock import MagicMock

from manuskript.ui.editors.editor_context import EditorContext
from manuskript.ui.views.outline_colors import OutlineColorResolver
from manuskript.ui.views.corkView import corkView
from manuskript.ui.views.outlineBasics import outlineBasics
from manuskript.ui.views.outline_context import OutlineViewContext


def make_outline_context():
    return OutlineViewContext(
        character_model=MagicMock(name="characters"),
        label_model=MagicMock(name="labels"),
        status_model=MagicMock(name="statuses"),
        color_resolver=OutlineColorResolver(),
        open_index=MagicMock(name="open_index"),
        open_indexes=MagicMock(name="open_indexes"),
        selection_changed=MagicMock(name="selection_changed"),
    )


def test_outline_view_context_supplies_models_and_open_callbacks():
    view = outlineBasics()
    context = make_outline_context()
    first = MagicMock(name="first_index")
    second = MagicMock(name="second_index")

    view.set_outline_context(context)
    view._indexesToOpen = [first, second]
    view.openItem()
    view.openItemsInNewTabs()

    assert view.modelCharacters is context.character_model
    assert view.modelLabels is context.label_model
    assert view.modelStatus is context.status_model
    context.open_index.assert_called_once_with(first)
    context.open_indexes.assert_called_once_with([first, second])


def test_cleared_outline_context_makes_open_commands_inert():
    view = outlineBasics()
    context = make_outline_context()
    view.set_outline_context(context)
    view.set_outline_context(None)
    view._indexesToOpen = [MagicMock()]

    assert view.modelCharacters is None
    assert view.modelLabels is None
    assert view.modelStatus is None
    view.openItem()
    view.openItemsInNewTabs()

    context.open_index.assert_not_called()
    context.open_indexes.assert_not_called()


def test_cork_delegate_receives_status_model_from_outline_context():
    view = corkView()
    context = make_outline_context()
    status_item = MagicMock()
    context.status_model.item.return_value = status_item

    view.set_outline_context(context)

    assert view.cork_delegate.status_model is context.status_model
    assert view.cork_delegate.color_resolver is context.color_resolver
    assert view.cork_delegate.status_item("2") is status_item
    context.status_model.item.assert_called_once_with(2, 0)

    view.set_outline_context(None)

    assert view.cork_delegate.status_model is None
    assert view.cork_delegate.status_item("2") is None


def test_editor_context_groups_outline_model_tree_and_view_dependencies():
    outline_views = make_outline_context()
    outline_model = MagicMock()
    outline_tree = MagicMock()

    context = EditorContext(
        outline_model=outline_model,
        outline_tree=outline_tree,
        outline_views=outline_views,
    )

    assert context.outline_model is outline_model
    assert context.outline_tree is outline_tree
    assert context.outline_views is outline_views
