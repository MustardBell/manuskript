"""The project layer, independent of any window showing it.

A project outlives its windows. These tests pin the ownership that makes
that possible: models parented to the runtime rather than a window, one
undo history shared by every view, and a manager the runtime builds
around whatever view side it is given.
"""

from unittest.mock import MagicMock

from PyQt5.QtCore import QObject

from manuskript.services.project_runtime import ProjectRuntime


def test_models_are_parented_to_the_runtime_not_a_window():
    """Qt deletes children with their parent, and a window closing is
    not the project ending -- so the model parent has to be the
    runtime's, and it has to survive being asked for twice.
    """
    runtime = ProjectRuntime()

    parent = runtime.modelParent

    assert isinstance(parent, QObject)
    assert parent.parent() is runtime
    assert runtime.modelParent is parent


def test_one_undo_history_is_shared_by_every_view():
    runtime = ProjectRuntime()

    assert runtime.undoStack is not None
    assert runtime.undoStack.parent() is runtime


def test_attach_builds_the_manager_around_the_given_view_side():
    """The runtime is composed before any window exists, so the manager
    can only be built once a window offers its view side.
    """
    history = MagicMock()
    runtime = ProjectRuntime(project_history=history)
    assert runtime.projectManager is None

    view = MagicMock()
    manager = runtime.attach(view)

    assert runtime.projectManager is manager
    # The manager talks to the registry of views, not to one window, so
    # a second window can join without the manager changing.
    assert manager.ui is runtime.views
    # And it reports through that registry rather than through a reporter
    # taken from whichever window attached first.
    assert manager.status_reporter == runtime.views.show_status
    assert runtime.views.views == (view,)
    assert runtime.views.primary is view
    assert manager.last_project_store is history
    assert manager.revision_coordinator is runtime.revisionCoordinator

    # A second window joins the running project rather than replacing
    # its manager.
    second = MagicMock()
    assert runtime.attach(second) is manager
    assert runtime.views.views == (view, second)

    runtime.detach(view)
    assert runtime.views.primary is second
    assert runtime.projectManager is manager


def test_project_facts_read_through_to_the_manager():
    runtime = ProjectRuntime()

    # Before any manager exists, asking is answered rather than raising:
    # a runtime with no project open is a legal state.
    assert runtime.session is None
    assert runtime.models is None
    assert runtime.currentProject is None
    assert runtime.isOpen is False

    runtime.attach(MagicMock())
    runtime.projectManager.session.open("book.msk")

    assert runtime.currentProject == "book.msk"
    assert runtime.isOpen is True
    assert runtime.session is runtime.projectManager.session


def test_a_window_shares_the_runtime_it_is_given(MWEmptyProject):
    """Project services remain runtime-owned, not window aliases."""
    window = MWEmptyProject
    runtime = window.projectRuntime

    assert window.settingsManager is runtime.settingsManager
    assert window.projectManager is runtime.projectManager
    assert window.projectManager.model_parent is runtime.modelParent
    assert window.projectManager.settings is runtime.settingsManager
    for legacy_alias in (
        "undoStack",
        "revisionCoordinator",
        "mdlFlatData",
        "mdlCharacter",
        "mdlLabels",
        "mdlStatus",
        "mdlPlots",
        "mdlOutline",
        "mdlWorld",
        "projectPluginData",
    ):
        assert not hasattr(window, legacy_alias), legacy_alias
    # QObject.parent explicitly: an item model's own parent() takes an
    # index and answers about the tree, not about ownership.
    assert (
        QObject.parent(runtime.models.outline) is runtime.modelParent
    )
    assert (
        QObject.parent(runtime.models.characters) is runtime.modelParent
    )
