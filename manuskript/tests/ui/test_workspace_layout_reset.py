"""The canonical first-open arrangement is reproducible on demand."""

from PyQt5.QtWidgets import QLabel, qApp

from manuskript.panels import (
    PanelContext,
    ToolPanelDescriptor,
    WorkspaceSurfaceDescriptor,
)
from manuskript.panels.core import (
    CORE_SURFACE_IDS,
    EDITOR,
    GENERAL,
    METADATA,
    OUTLINE,
    PROJECT_TREE,
    STORYLINE,
)


def settle():
    for _turn in range(5):
        qApp.processEvents()


def test_reset_reconstructs_the_upstream_shaped_first_open_frame(
        MWEmptyProject):
    window = MWEmptyProject
    window.show()

    window.resetWorkspaceLayout()
    settle()

    general = window.surfaceHost.instance(GENERAL).container
    editor = window.surfaceHost.instance(EDITOR).container
    outline = window.surfaceHost.instance(OUTLINE).container
    project_tree_instance = window.panelHost.instance(PROJECT_TREE)
    project_tree = project_tree_instance.container
    metadata = window.panelHost.instance(METADATA).container
    storyline = window.panelHost.instance(STORYLINE).container

    assert window.centralWidget() is None
    assert window.dckNavigation.isVisible()
    assert window.dckNavigation.width() == 200
    assert general.isVisible()
    assert all(
        window.surfaceHost.instance(surface_id).container.isHidden()
        for surface_id in CORE_SURFACE_IDS
        if surface_id != GENERAL
    )
    assert not project_tree.isVisible()
    assert not metadata.isVisible()
    assert not storyline.isVisible()
    assert editor in window.tabifiedDockWidgets(general)
    assert outline in window.tabifiedDockWidgets(general)
    assert all(
        window.surfaceHost.instance(surface_id).container
        in window.tabifiedDockWidgets(general)
        for surface_id in CORE_SURFACE_IDS
        if surface_id != GENERAL
    )
    # Inspectors belong on the far side of the writing surface. They must not
    # replace Project Tree merely because all three are tool panels.
    window.panelHost.reveal(METADATA)
    settle()
    assert metadata.isVisible()
    assert metadata.x() > general.x()
    window.activatePanel(EDITOR)
    settle()
    assert project_tree.isVisible()
    assert project_tree.x() < editor.x() < metadata.x()
    assert project_tree.width() >= (
        project_tree_instance.descriptor.preferred_extent - 10
    )
    window.panelHost.reveal(STORYLINE)
    settle()
    assert storyline in window.tabifiedDockWidgets(metadata)
    assert storyline not in window.tabifiedDockWidgets(project_tree)


def test_reset_rearranges_living_surfaces_without_rebuilding_them(
        MWEmptyProject):
    window = MWEmptyProject
    original_widgets = {
        surface_id: instance.widget
        for surface_id, instance in window.surfaceHost.instances.items()
    }
    assert window.activatePanel(EDITOR)
    window.panelHost.reveal(METADATA)
    window.panelHost.reveal(STORYLINE)

    window.resetWorkspaceLayout()
    settle()

    assert {
        surface_id: instance.widget
        for surface_id, instance in window.surfaceHost.instances.items()
    } == original_widgets
    assert window.surfaceHost.current() == GENERAL
    assert window._activePanelId == GENERAL
    assert window.surfaceHost.instance(GENERAL).container.isVisible()
    assert window.surfaceHost.instance(EDITOR).container.isHidden()
    assert window.panelHost.instance(METADATA).container.isHidden()
    assert window.panelHost.instance(STORYLINE).container.isHidden()


def test_reset_closes_contributed_panels_and_removes_their_toggle(
        MWEmptyProject):
    window = MWEmptyProject
    panel_id = "test.reset.contributed-panel"
    window.panelRegistry.register(ToolPanelDescriptor(
        id=panel_id,
        title="Contributed panel",
        widget_factory=lambda context, parent: QLabel("plugin", parent),
    ))
    try:
        window.panelHost.open(
            panel_id,
            PanelContext(translate=window.tr),
        )
        assert window.panelHost.instance(panel_id) is not None
        assert panel_id in window.toolbar._panelToggles

        window.resetWorkspaceLayout()
        settle()

        assert window.panelHost.instance(panel_id) is None
        assert panel_id not in window.toolbar._panelToggles
    finally:
        window.panelHost.close(panel_id)
        window.toolbar.removePanelToggle(panel_id)
        if panel_id in window.panelRegistry:
            window.panelRegistry.deregister(panel_id)


def test_view_menu_exposes_reset_as_an_explicit_command(MWEmptyProject):
    action = MWEmptyProject.actResetWorkspaceLayout

    assert action.objectName() == "actResetWorkspaceLayout"
    assert "first-open" in action.statusTip()


def test_reset_reunites_a_detached_editor_and_retires_its_wrapper(
        MWEmptyProject):
    primary = MWEmptyProject
    primary.show()
    primary.activatePanel(EDITOR)
    original = primary.surfaceHost.instance(EDITOR)
    widget = original.widget
    wrapper = primary.surfaceTransfer.move_to_new_workspace(EDITOR)
    assert wrapper is not None
    assert set(wrapper.surfaceHost.instances) == {EDITOR}

    # The command is application-scoped even when invoked from the
    # temporary window that it will retire.
    assert wrapper.resetWorkspaceLayout()
    settle()

    assert primary.windowRegistry.workspace_windows == (primary,)
    assert set(primary.surfaceHost.instances) >= set(CORE_SURFACE_IDS)
    assert primary.surfaceHost.instance(EDITOR) is original
    assert original.widget is widget
    assert original.host is primary.surfaceHost
    assert (
        original.widget.editor.editor_context.outline_tree
        is primary.outlineSelection
    )
    assert (
        primary.corePanels.project_tree.tree.selectionModel()
        is primary.outlineSelection.selectionModel()
    )
    assert primary.surfaceHost.current() == GENERAL
    assert primary.windowState.store.open_windows() == (primary.windowId,)


def test_reset_closes_a_contributed_workspace_surface(MWEmptyProject):
    window = MWEmptyProject
    surface_id = "test.reset.contributed-surface"
    window.panelRegistry.register(WorkspaceSurfaceDescriptor(
        id=surface_id,
        title="Contributed surface",
        widget_factory=lambda context, parent: QLabel("plugin", parent),
    ))
    try:
        window.surfaceHost.open(
            surface_id,
            PanelContext(translate=window.tr),
        )
        assert window.surfaceHost.contains(surface_id)
        assert surface_id in window.toolbar._panelToggles

        assert window.resetWorkspaceLayout()
        settle()

        assert not window.surfaceHost.contains(surface_id)
        assert surface_id not in window.toolbar._panelToggles
    finally:
        window.surfaceHost.close(surface_id)
        if surface_id in window.panelRegistry:
            window.panelRegistry.deregister(surface_id)


def test_failed_reset_returns_a_gathered_surface_to_its_wrapper(
        MWEmptyProject, monkeypatch):
    primary = MWEmptyProject
    primary.activatePanel(EDITOR)
    original = primary.surfaceHost.instance(EDITOR)
    wrapper = primary.surfaceTransfer.move_to_new_workspace(EDITOR)
    assert wrapper is not None

    def reject_layout():
        raise RuntimeError("layout probe")

    monkeypatch.setattr(primary, "_resetLocalWorkspaceLayout", reject_layout)
    try:
        assert not primary.resetWorkspaceLayout()

        assert wrapper.surfaceHost.instance(EDITOR) is original
        assert original.host is wrapper.surfaceHost
        assert not primary.surfaceHost.contains(EDITOR)
        assert wrapper in primary.windowRegistry.workspace_windows
    finally:
        if wrapper.surfaceHost.contains(EDITOR):
            instance = wrapper.surfaceHost.detach(EDITOR)
            primary.surfaceHost.attach(instance)
            primary.activatePanel(EDITOR)
        wrapper.close()
        settle()
