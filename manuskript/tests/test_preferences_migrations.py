"""A routing choice made before media types still selects its renderer.

Routing choices live in QSettings rather than in a project, so they need a
version marker of their own. These tests use a real QSettings on a temporary
ini file: the migration walks keys and rewrites JSON, and a stand-in would
mostly test the stand-in.
"""

import json

import pytest
from PyQt5.QtCore import QSettings

from manuskript.media_types import BBCODE, EPUB, HTML, MARKDOWN, PLAIN
from manuskript.preferences_migrations import (
    PREFERENCES_VERSION,
    ROUTE_KEY_PREFIX,
    VERSION_KEY,
    upgrade,
)


SAMPLE = ROUTE_KEY_PREFIX + "vendor.structured-page"


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat)


def store(settings, key, values):
    settings.setValue(key, json.dumps(values, sort_keys=True))


def load(settings, key):
    return json.loads(str(settings.value(key)))


# ------------------------------------------------------------- the version

def test_an_installation_with_no_marker_is_version_zero(settings):
    store(settings, SAMPLE, {"bbcode:bbcode": "sample.bbcode"})

    upgrade(settings)

    assert int(settings.value(VERSION_KEY)) == PREFERENCES_VERSION
    assert load(settings, SAMPLE) == {
        "text/x-bbcode|text/x-bbcode": "sample.bbcode",
    }


def test_upgrading_twice_changes_nothing(settings):
    store(settings, SAMPLE, {"plain:markdown": "sample.markdown"})

    upgrade(settings)
    once = load(settings, SAMPLE)
    upgrade(settings)

    assert load(settings, SAMPLE) == once


def test_preferences_from_a_newer_manuskript_are_left_alone(settings):
    settings.setValue(VERSION_KEY, PREFERENCES_VERSION + 5)
    store(settings, SAMPLE, {"bbcode:bbcode": "sample.bbcode"})

    upgrade(settings)

    # Not understood, so not touched -- and not destroyed either.
    assert load(settings, SAMPLE) == {"bbcode:bbcode": "sample.bbcode"}
    assert int(settings.value(VERSION_KEY)) == PREFERENCES_VERSION + 5


def test_an_unreadable_version_is_treated_as_zero(settings):
    settings.setValue(VERSION_KEY, "banana")
    store(settings, SAMPLE, {"bbcode:bbcode": "sample.bbcode"})

    upgrade(settings)

    assert load(settings, SAMPLE) == {
        "text/x-bbcode|text/x-bbcode": "sample.bbcode",
    }


# ------------------------------------------------------------- the rewrite

def test_every_legacy_route_pair_becomes_media_types(settings):
    store(settings, SAMPLE, {
        "plain:markdown": "sample.markdown",
        "bbcode:bbcode": "sample.bbcode",
        "epub:html": "other.html",
        "docx:markdown": "sample.markdown",
    })

    upgrade(settings)

    assert load(settings, SAMPLE) == {
        PLAIN + "|" + MARKDOWN: "sample.markdown",
        BBCODE + "|" + BBCODE: "sample.bbcode",
        EPUB + "|" + HTML: "other.html",
        "application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document|" + MARKDOWN: "sample.markdown",
    }


def test_the_oldest_shape_named_only_the_representation(settings):
    # Before routes carried a destination, the key was the representation
    # alone. That named the route where a format is both.
    store(settings, SAMPLE, {"bbcode": "sample.bbcode"})

    upgrade(settings)

    assert load(settings, SAMPLE) == {
        BBCODE + "|" + BBCODE: "sample.bbcode",
    }


def test_the_oldest_shape_cannot_reach_a_differing_destination(settings):
    # The deleted compatibility shim read a bare key for any route ending in
    # that representation, so a bare "html" also served epub. A migration
    # cannot reproduce that: it does not know which destinations exist. The
    # self-route is kept and an ePub route falls back to its default, which
    # is one re-pick of a choice made before routes had destinations.
    store(settings, SAMPLE, {"html": "vendor.html"})

    upgrade(settings)

    assert load(settings, SAMPLE) == {HTML + "|" + HTML: "vendor.html"}
    assert EPUB + "|" + HTML not in load(settings, SAMPLE)


def test_a_format_nothing_recognises_is_left_inert_not_dropped(settings):
    store(settings, SAMPLE, {"fictionbook:fictionbook": "vendor.fb2"})

    upgrade(settings)

    # Named by something that chose its own vocabulary. Guessing would be
    # worse than leaving it visible and inert.
    assert load(settings, SAMPLE) == {
        "fictionbook|fictionbook": "vendor.fb2",
    }


def test_choices_for_several_page_types_all_migrate(settings):
    other = ROUTE_KEY_PREFIX + "vendor.other-page"
    store(settings, SAMPLE, {"bbcode:bbcode": "sample.bbcode"})
    store(settings, other, {"html:html": "vendor.html"})

    upgrade(settings)

    assert load(settings, SAMPLE) == {BBCODE + "|" + BBCODE: "sample.bbcode"}
    assert load(settings, other) == {HTML + "|" + HTML: "vendor.html"}


# --------------------------------------------------------- what it leaves

def test_preferences_that_are_not_routes_are_untouched(settings):
    settings.setValue("applicationStyle", "Fusion")
    settings.setValue("plugins/options/vendor.thing", '{"colour": "blue"}')

    upgrade(settings)

    assert settings.value("applicationStyle") == "Fusion"
    assert json.loads(
        str(settings.value("plugins/options/vendor.thing"))
    ) == {"colour": "blue"}


def test_a_migrated_choice_reaches_the_resolver(settings):
    """The point of the whole exercise, end to end.

    PageTypeService now looks a route up exactly, having lost the shim that
    forgave the old spelling. So the migration is what keeps a choice made
    before media types working.
    """
    from manuskript.exporter.page_routes import page_renderer_route_id
    from manuskript.plugins import (
        ExtensionDescriptor,
        PageRendererContribution,
        PageTypeContribution,
    )
    from manuskript.plugins.registry import PluginRegistry
    from manuskript.services.plugin_options import PluginOptionStore
    from manuskript.ui.plugins.page_types import PageTypeService

    store(settings, SAMPLE, {"bbcode:bbcode": "vendor.bbcode"})
    upgrade(settings)

    registry = PluginRegistry()
    registrar = registry.registrar("vendor.plugin")
    registrar.register_page_type(PageTypeContribution(
        ExtensionDescriptor("vendor.structured-page", "SAMPLE page"),
        "SAMPLE page",
        parser_factory=object,
    ))
    registrar.register_page_renderer(PageRendererContribution(
        ExtensionDescriptor("vendor.bbcode", "Vendor BBCode"),
        page_type_id="vendor.structured-page",
        renderer_factory=object,
        target_formats=(BBCODE,),
    ))
    registry.install("vendor.plugin", registrar.contributions)
    service = PageTypeService(registry, PluginOptionStore(settings))

    assert service.selected_renderer_id(
        "vendor.structured-page",
        page_renderer_route_id(BBCODE, BBCODE),
    ) == "vendor.bbcode"


def test_unreadable_stored_values_do_not_stop_the_migration(settings):
    settings.setValue(ROUTE_KEY_PREFIX + "broken", "not json at all")
    store(settings, SAMPLE, {"bbcode:bbcode": "sample.bbcode"})

    upgrade(settings)

    assert load(settings, SAMPLE) == {BBCODE + "|" + BBCODE: "sample.bbcode"}
    assert int(settings.value(VERSION_KEY)) == PREFERENCES_VERSION


# ------------------------------------------------- window layout, v1 to v2

def test_a_layout_arranged_over_years_survives_the_move(settings):
    """One window's layout used to occupy eight fixed keys, which a
    second window would write straight over. Everything found there is
    filed under the primary window rather than discarded.
    """
    settings.setValue("geometry", b"saved-geometry")
    settings.setValue("windowState", b"saved-docks")
    settings.setValue("splitterRedacH", b"horizontal")
    settings.setValue("splitterRedacV", b"vertical")
    settings.setValue("metadataState", [True, False, True])
    settings.setValue("revisionsState", [False, True])

    upgrade(settings)

    assert settings.value(
        "workspace/windows/main/geometry"
    ) == b"saved-geometry"
    assert settings.value(
        "workspace/windows/main/windowState"
    ) == b"saved-docks"
    assert settings.value(
        "workspace/windows/main/splitters/splitterRedacH"
    ) == b"horizontal"
    assert settings.value(
        "workspace/windows/main/splitters/splitterRedacV"
    ) == b"vertical"
    assert settings.value(
        "workspace/windows/main/panelState/core.metadata"
    ) is not None
    assert settings.value(
        "workspace/windows/main/panelState/core.metadata.revisions"
    ) is not None
    # The old spelling is gone, so nothing downstream can read it by
    # accident and no second window can collide with it.
    for legacy in (
        "geometry", "windowState", "splitterRedacH", "splitterRedacV",
        "metadataState", "revisionsState",
    ):
        assert not settings.contains(legacy), legacy


def test_panel_visibility_stops_being_matched_by_button_text(settings):
    """Visibility was stored as (group, title, shown) and matched back
    by title, so renaming or translating a panel lost it. Titles are
    read one last time here and turned into panel ids.
    """
    settings.setValue("toolbar", [
        ("3", "Book summary", False),
        ("6", "Project tree", True),
        ("6", "&Metadata", False),
        ("6", "Story line", True),
    ])

    upgrade(settings)

    panels = "workspace/windows/main/panels"
    assert settings.value("{}/core.book-summary".format(panels)) in (
        False, "false",
    )
    assert settings.value("{}/core.project-tree".format(panels)) in (
        True, "true",
    )
    assert settings.value("{}/core.metadata".format(panels)) in (
        False, "false",
    )
    assert settings.value("{}/core.storyline".format(panels)) in (
        True, "true",
    )
    assert not settings.contains("toolbar")


def test_a_panel_this_manuskript_no_longer_has_is_dropped(settings):
    """Nothing could show it, so keeping the row would preserve only a
    name -- and an unrecognised title has no id to file it under.
    """
    settings.setValue("toolbar", [
        ("6", "Project tree", True),
        ("6", "Some removed panel", True),
    ])

    upgrade(settings)

    panels = "workspace/windows/main/panels"
    assert settings.contains("{}/core.project-tree".format(panels))
    assert "removed" not in " ".join(settings.allKeys()).lower()


def test_dock_visibility_becomes_one_entry_per_dock(settings):
    settings.setValue("docks", json.dumps({
        "dckNavigation": True,
        "dckSearch": False,
    }))

    upgrade(settings)

    docks = "workspace/windows/main/docks"
    assert settings.value("{}/dckNavigation".format(docks)) in (
        True, "true",
    )
    assert settings.value("{}/dckSearch".format(docks)) in (
        False, "false",
    )
    assert not settings.contains("docks")


def test_an_installation_with_no_layout_migrates_cleanly(settings):
    """Nothing saved is not an error; a fresh installation simply has
    no window state to move.
    """
    upgrade(settings)

    assert int(settings.value(VERSION_KEY)) == PREFERENCES_VERSION
    assert not settings.contains("workspace/windows/main/geometry")


def test_a_layout_is_not_moved_twice(settings):
    """Upgrading an already-upgraded installation must not overwrite
    per-window state with whatever the legacy keys no longer hold.
    """
    settings.setValue("geometry", b"original")
    upgrade(settings)
    settings.setValue(
        "workspace/windows/main/geometry", b"since-rearranged",
    )

    upgrade(settings)

    assert settings.value(
        "workspace/windows/main/geometry"
    ) == b"since-rearranged"
