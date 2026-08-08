"""The four workspace panels go through the registry like anything else.

They were wired straight into setupMoreUi for years; these tests pin
that the panel host now owns their toggles, so a second window can build
the same set from the same declarations.
"""

from dataclasses import fields

from manuskript.panels import PanelContext, PanelRegistry, SplitterSlot
from manuskript.panels.core import (
    BOOK_SUMMARY,
    METADATA,
    PROJECT_TREE,
    STORYLINE,
    register_core_panels,
)


def test_panel_factories_receive_no_main_window_escape_hatch():
    """New dependencies must be explicit rather than found on a window."""
    assert tuple(field.name for field in fields(PanelContext)) == (
        "translate",
        "show_status",
        "plugin_project",
    )
    assert not hasattr(PanelContext(), "window")


def test_the_four_workspace_panels_are_attached_via_the_registry(
        MWEmptyProject):
    window = MWEmptyProject
    views = window.corePanels
    for panel_id, widget in (
        (BOOK_SUMMARY, views.book_summary.panel),
        (PROJECT_TREE, views.project_tree.panel),
        (METADATA, views.metadata),
        (STORYLINE, views.storyline),
    ):
        assert panel_id in window.panelRegistry, panel_id
        instance = window.panelHost.instance(panel_id)
        assert instance is not None, panel_id
        assert instance.widget is widget
        assert instance.action is not None


def test_core_panel_views_replace_designer_era_window_aliases(
        MWEmptyProject):
    """Core widgets have one grouped API, not implicit window fields."""
    window = MWEmptyProject

    assert [field.name for field in fields(type(window.corePanels))] == [
        "book_summary",
        "project_tree",
        "metadata",
        "storyline",
    ]
    for old_name in (
        "grpPlotSummary",
        "comboBox_2",
        "stkPlotSummary",
        "txtPlotSummaryPara",
        "txtPlotSummaryPage",
        "txtPlotSummaryFull",
        "treeRedacWidget",
        "treeRedacOutline",
        "btnRedacAddFolder",
        "btnRedacAddText",
        "btnRedacRemoveItem",
        "redacMetadata",
        "storylineView",
    ):
        assert not hasattr(window, old_name), old_name


def test_toggling_the_action_shows_and_hides_the_widget(MWEmptyProject):
    window = MWEmptyProject
    instance = window.panelHost.instance(METADATA)
    was_checked = instance.action.isChecked()

    instance.action.setChecked(True)
    assert not window.corePanels.metadata.isHidden()
    instance.action.setChecked(False)
    assert window.corePanels.metadata.isHidden()

    instance.action.setChecked(was_checked)


def test_set_visible_drives_the_shared_action(MWEmptyProject):
    """Forcing a panel visible (the search jump does this) must go
    through the one action, or the toolbar button would disagree with
    what is on screen.
    """
    window = MWEmptyProject
    instance = window.panelHost.instance(METADATA)
    was_checked = instance.action.isChecked()

    window.panelHost.set_visible(METADATA)

    assert instance.action.isChecked()
    assert not window.corePanels.metadata.isHidden()

    instance.action.setChecked(was_checked)


def test_book_summary_is_built_by_its_factory(MWEmptyProject):
    """The panel no longer exists in the Designer file: the registry's
    factory builds it, into the splitter slot the .ui always used, with
    the objectNames saved layouts rely on.
    """
    window = MWEmptyProject
    views = window.corePanels.book_summary
    panel = views.panel

    assert window.splitterPlot.indexOf(panel) == 2
    assert panel.objectName() == "grpPlotSummary"
    assert window.panelHost.instance(BOOK_SUMMARY).widget is panel

    views.selector.setCurrentIndex(1)
    assert views.pages.currentIndex() == 1
    assert views.pages.currentWidget().findChild(
        type(views.page_editor), "txtPlotSummaryPage"
    ) is views.page_editor
    views.selector.setCurrentIndex(0)


def test_storyline_is_built_by_its_factory(MWEmptyProject):
    """Same contract as the book summary: factory-built, same slot,
    same objectName, and exposed through the typed view set.
    """
    window = MWEmptyProject
    view = window.corePanels.storyline

    assert window.splitterRedacV.indexOf(view) == 1
    assert view.objectName() == "storylineView"
    assert window.panelHost.instance(STORYLINE).widget is view


def test_metadata_is_built_by_its_factory_and_state_round_trips(
        MWEmptyProject):
    """The panel stays in its slot and keeps its save-state protocol.
    """
    window = MWEmptyProject
    view = window.corePanels.metadata

    assert window.splitterRedacH.indexOf(view) == 2
    assert view.objectName() == "redacMetadata"
    assert window.panelHost.instance(METADATA).widget is view

    state = view.saveState()
    view.restoreState(state)
    assert view.saveState() == state
    assert view.revisions is not None


def test_project_tree_is_built_by_its_factory(MWEmptyProject):
    """The tree is the most referenced widget of the four; the factory
    lands it in the first slot and the view set exposes its controls.
    """
    window = MWEmptyProject
    views = window.corePanels.project_tree
    panel = views.panel

    assert window.splitterRedacH.indexOf(panel) == 0
    assert window.splitterRedacH.indexOf(window.corePanels.metadata) == 2
    assert panel.objectName() == "treeRedacWidget"
    assert window.panelHost.instance(PROJECT_TREE).widget is panel

    tree = views.tree
    assert tree.parent() is panel
    assert not tree.header().isVisible()
    for button in (
        views.add_folder,
        views.add_text,
        views.remove_item,
    ):
        assert button.parent() is panel
        assert button.isFlat()


def test_declaring_core_panels_twice_is_harmless():
    """The registry outlives any window, so the second window finds the
    panels already declared and must not trip over them.
    """
    registry = PanelRegistry()
    register_core_panels(registry, 3, 6)
    register_core_panels(registry, 3, 6)

    assert [entry.id for entry in registry.descriptors()] == [
        BOOK_SUMMARY, PROJECT_TREE, METADATA, STORYLINE,
    ]
    slot = registry.descriptor(METADATA).slot
    assert slot == SplitterSlot("splitterRedacH", 2)
