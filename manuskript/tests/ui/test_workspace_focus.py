from unittest.mock import MagicMock

from manuskript.ui.views.MDEditView import MDEditView
from manuskript.ui.workspace_focus import (
    WorkspaceFocusController,
    WorkspaceFocusViews,
)


class _Widget:
    """Finite QWidget-shaped test double for parent traversal."""

    def __init__(self, parent=None, canonical_editor=None):
        self._parent = parent
        if canonical_editor is not None:
            self.canonicalEditor = canonical_editor

    def parent(self):
        return self._parent


def test_focus_selects_the_document_root_containing_the_widget():
    project_tree = _Widget()
    document_area = _Widget()
    child = _Widget(document_area)
    controller = WorkspaceFocusController(
        WorkspaceFocusViews((project_tree, document_area))
    )

    controller.focus_changed(None, child)

    assert controller.document_target is document_area


def test_unrelated_focus_keeps_the_last_document_command_target():
    document_area = _Widget()
    child = _Widget(document_area)
    controller = WorkspaceFocusController(
        WorkspaceFocusViews((document_area,))
    )
    controller.focus_changed(None, child)
    unrelated = _Widget()

    controller.focus_changed(child, unrelated)

    assert controller.document_target is document_area


def test_focus_selects_the_canonical_editor_of_a_projection():
    canonical = MagicMock(spec=MDEditView)
    projection = _Widget(canonical_editor=canonical)
    controller = WorkspaceFocusController(WorkspaceFocusViews(()))

    controller.focus_changed(None, projection)

    assert controller.markup_target is canonical


def test_leaving_markdown_clears_only_the_markup_target():
    canonical = MagicMock(spec=MDEditView)
    projection = _Widget(canonical_editor=canonical)
    controller = WorkspaceFocusController(WorkspaceFocusViews(()))
    controller.focus_changed(None, projection)
    unrelated = _Widget()

    controller.focus_changed(projection, unrelated)

    assert controller.markup_target is None


def test_dispose_releases_targets_and_view_roots():
    target = _Widget()
    controller = WorkspaceFocusController(
        WorkspaceFocusViews((target,))
    )
    controller._document_target = target
    controller._markup_target = target

    controller.dispose()

    assert controller.document_target is None
    assert controller.markup_target is None
    assert controller._views.document_targets == ()
