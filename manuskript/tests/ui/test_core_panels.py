"""The four workspace panels go through the registry like anything else.

They were wired straight into setupMoreUi for years; these tests pin
that the panel host now owns their toggles, so a second window can build
the same set from the same declarations.
"""

from manuskript.panels import PanelRegistry, SplitterSlot
from manuskript.panels.core import (
    BOOK_SUMMARY,
    METADATA,
    PROJECT_TREE,
    STORYLINE,
    register_core_panels,
)


def test_the_four_workspace_panels_are_attached_via_the_registry(
        MWEmptyProject):
    window = MWEmptyProject
    for panel_id, widget_name in (
        (BOOK_SUMMARY, "grpPlotSummary"),
        (PROJECT_TREE, "treeRedacWidget"),
        (METADATA, "redacMetadata"),
        (STORYLINE, "storylineView"),
    ):
        assert panel_id in window.panelRegistry, panel_id
        instance = window.panelHost.instance(panel_id)
        assert instance is not None, panel_id
        assert instance.widget is getattr(window, widget_name)
        assert instance.action is not None


def test_toggling_the_action_shows_and_hides_the_widget(MWEmptyProject):
    window = MWEmptyProject
    instance = window.panelHost.instance(METADATA)
    was_checked = instance.action.isChecked()

    instance.action.setChecked(True)
    assert not window.redacMetadata.isHidden()
    instance.action.setChecked(False)
    assert window.redacMetadata.isHidden()

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
    assert not window.redacMetadata.isHidden()

    instance.action.setChecked(was_checked)


def test_book_summary_is_built_by_its_factory(MWEmptyProject):
    """The panel no longer exists in the Designer file: the registry's
    factory builds it, into the splitter slot the .ui always used, with
    the objectNames saved layouts and callers rely on.
    """
    window = MWEmptyProject
    panel = window.grpPlotSummary

    assert window.splitterPlot.indexOf(panel) == 2
    assert panel.objectName() == "grpPlotSummary"
    assert window.panelHost.instance(BOOK_SUMMARY).widget is panel

    window.comboBox_2.setCurrentIndex(1)
    assert window.stkPlotSummary.currentIndex() == 1
    assert window.stkPlotSummary.currentWidget().findChild(
        type(window.txtPlotSummaryPage), "txtPlotSummaryPage"
    ) is window.txtPlotSummaryPage
    window.comboBox_2.setCurrentIndex(0)


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
