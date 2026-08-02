"""Cork card styles are contributions, resolved by ID and never fatal."""

import pytest

from manuskript.plugins.errors import PluginRegistrationError
from manuskript.plugins.registry import ContributionKind, PluginRegistry
from manuskript.plugins.runtime import PluginRuntime
from manuskript.services.plugin_preferences import (
    InMemoryPluginPreferences,
)
from manuskript.tests.plugins.test_runtime import create_plugin
from manuskript.ui.plugins.index_card_styles import IndexCardStyleService
from manuskript.ui.views.cards import (
    IndexCardStyle,
    PlainCardStyle,
    RuledCardStyle,
)


PLAIN = "manuskript.card.plain"
RULED = "manuskript.card.ruled"

STYLE_PLUGIN_SOURCE = """
from PyQt5.QtCore import QSize

from manuskript.plugins import (
    ExtensionDescriptor, IndexCardStyleContribution)
from manuskript.ui.views.cards import IndexCardStyle


class PolaroidStyle(IndexCardStyle):
    def size_hint(self, factor):
        return QSize(320, 320) * factor

    def layout(self, ctx):
        raise AssertionError("not exercised")


def register(api):
    api.register_index_card_style(IndexCardStyleContribution(
        descriptor=ExtensionDescriptor(
            id='mustardbell.card.polaroid', name='Polaroid'),
        style_factory=PolaroidStyle,
    ))
"""

BROKEN_STYLE_SOURCE = """
from manuskript.plugins import (
    ExtensionDescriptor, IndexCardStyleContribution)


def register(api):
    api.register_index_card_style(IndexCardStyleContribution(
        descriptor=ExtensionDescriptor(id='bad.card', name='Bad'),
        style_factory=lambda: "not a style",
    ))
"""


def loaded_runtime(tmp_path, source):
    create_plugin(tmp_path, plugin_id="styles.plugin", source=source)
    runtime = PluginRuntime(
        [tmp_path], InMemoryPluginPreferences(["styles.plugin"]))
    runtime.discover()
    runtime.load_enabled()
    return runtime


def test_builtins_are_available_without_any_plugin_registry():
    service = IndexCardStyleService()

    ids = [style_id for style_id, _name in service.styles()]

    assert ids == [PLAIN, RULED]
    assert isinstance(service.resolve(PLAIN), PlainCardStyle)
    assert isinstance(service.resolve(RULED), RuledCardStyle)


def test_unknown_style_falls_back_to_the_default_instead_of_raising():
    service = IndexCardStyleService()

    # A project can name a style whose plugin is no longer installed.
    resolved = service.resolve("gone.away")

    assert isinstance(resolved, PlainCardStyle)
    assert isinstance(service.resolve(""), PlainCardStyle)
    assert isinstance(service.resolve(None), PlainCardStyle)


def test_plugin_styles_join_the_builtins(tmp_path):
    runtime = loaded_runtime(tmp_path, STYLE_PLUGIN_SOURCE)
    service = IndexCardStyleService(runtime.registry)

    listed = dict(service.styles())

    assert listed["mustardbell.card.polaroid"] == "Polaroid"
    assert PLAIN in listed and RULED in listed

    resolved = service.resolve("mustardbell.card.polaroid")

    assert isinstance(resolved, IndexCardStyle)
    assert resolved.id == "mustardbell.card.polaroid"
    assert resolved.name == "Polaroid"


def test_a_style_that_is_not_an_IndexCardStyle_is_refused(tmp_path):
    runtime = loaded_runtime(tmp_path, BROKEN_STYLE_SOURCE)
    reported = []
    service = IndexCardStyleService(
        runtime.registry,
        report_error=lambda message, *_a: reported.append(message),
    )

    resolved = service.resolve("bad.card")

    assert isinstance(resolved, PlainCardStyle)
    assert reported and "IndexCardStyle" in reported[0]


def test_disabling_the_owning_plugin_retires_its_style(tmp_path):
    runtime = loaded_runtime(tmp_path, STYLE_PLUGIN_SOURCE)
    service = IndexCardStyleService(runtime.registry)
    assert "mustardbell.card.polaroid" in dict(service.styles())

    runtime.disable("styles.plugin")

    assert "mustardbell.card.polaroid" not in dict(service.styles())
    assert isinstance(
        service.resolve("mustardbell.card.polaroid"), PlainCardStyle)


def test_two_plugins_cannot_claim_the_same_style_id():
    registry = PluginRegistry()
    from manuskript.plugins import (
        ExtensionDescriptor,
        IndexCardStyleContribution,
    )

    def contribution():
        return IndexCardStyleContribution(
            descriptor=ExtensionDescriptor(id="shared.card", name="Shared"),
            style_factory=PlainCardStyle,
        )

    first = registry.registrar("plugin.a")
    first.register_index_card_style(contribution())
    registry.install("plugin.a", first.contributions)

    second = registry.registrar("plugin.b")
    second.register_index_card_style(contribution())

    with pytest.raises(PluginRegistrationError) as failure:
        registry.install("plugin.b", second.contributions)

    assert "plugin.a" in str(failure.value)
    assert registry.records(ContributionKind.INDEX_CARD_STYLE)[0].plugin_id \
        == "plugin.a"


def test_builtin_styles_disagree_about_card_size():
    # The two ship different geometry; sizeHint must follow the active style.
    assert PlainCardStyle().size_hint(1.0) != RuledCardStyle().size_hint(1.0)
    assert PlainCardStyle().size_hint(2.0).width() == (
        2 * PlainCardStyle().size_hint(1.0).width())


def test_cork_view_follows_the_project_setting(MWEmptyProject):
    """The delegate paints whichever style the project names."""
    from PyQt5.QtWidgets import qApp
    from manuskript.models.outlineItem import outlineItem

    window = MWEmptyProject
    folder = outlineItem(window.mdlOutline, title="Act", _type="folder")
    window.mdlOutline.appendItem(folder)
    scene = outlineItem(window.mdlOutline, title="Scene", _type="md")
    window.mdlOutline.appendItem(
        scene, window.mdlOutline.indexFromItem(folder))
    window.mainEditor.setCurrentModelIndex(
        window.mdlOutline.indexFromItem(folder), newTab=True)
    editor = window.mainEditor.currentEditor()
    editor.setFolderView("cork")
    previous = window.settingsManager.indexCardStyle

    try:
        window.settingsManager.indexCardStyle = RULED
        editor.corkView.updateCardStyle()
        qApp.processEvents()
        assert isinstance(
            editor.corkView.cork_delegate.style, RuledCardStyle)

        window.settingsManager.indexCardStyle = PLAIN
        editor.corkView.updateCardStyle()
        qApp.processEvents()
        assert isinstance(
            editor.corkView.cork_delegate.style, PlainCardStyle)

        # An uninstalled style must not break the view.
        window.settingsManager.indexCardStyle = "gone.away"
        editor.corkView.updateCardStyle()
        qApp.processEvents()
        assert isinstance(
            editor.corkView.cork_delegate.style, PlainCardStyle)
    finally:
        window.settingsManager.indexCardStyle = previous
        window.mainEditor.closeAllTabs()
