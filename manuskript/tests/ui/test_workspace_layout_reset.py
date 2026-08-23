"""The canonical first-open arrangement is reproducible on demand."""

from PyQt5.QtWidgets import QLabel, qApp

from manuskript.panels import PanelContext, ToolPanelDescriptor
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
    project_tree = window.panelHost.instance(PROJECT_TREE).container
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
    # Qt drops a tab group when every member is hidden. The reset contract
    # therefore records these peers until the companion's first reveal.
    window.panelHost.reveal(METADATA)
    settle()
    assert metadata.isVisible()
    assert window.dockWidgetArea(metadata) == window.dockWidgetArea(
        project_tree
    )
    window.activatePanel(EDITOR)
    settle()
    assert metadata in window.tabifiedDockWidgets(project_tree)
    window.panelHost.reveal(STORYLINE)
    settle()
    assert storyline in window.tabifiedDockWidgets(project_tree)


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
