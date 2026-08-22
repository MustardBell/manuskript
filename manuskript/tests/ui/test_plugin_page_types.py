from PyQt5.QtWidgets import QCheckBox, QMessageBox, QWidget

from manuskript.enums import Outline
from manuskript.models.outlineItem import outlineItem
from manuskript.plugins import (
    ExtensionDescriptor,
    OptionField,
    PageExportDocument,
    PageRendererContribution,
    PageTypeContribution,
    PresentationModeContribution,
)
from manuskript.plugins.registry import PluginRegistry
from manuskript.services.plugin_options import InMemoryPluginOptionStore
from manuskript.media_types import BBCODE, HTML, MARKDOWN
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)
from manuskript.ui.plugins.page_types import PageTypeService
from manuskript.ui.views.propertiesView import propertiesView


class Parser:
    def parse(self, source):
        return "STRUCTURED:" + source


class Renderer:
    def render(self, model, target_format, options):
        return PageExportDocument(model, target_format)


def make_service(activation_warning=None, source_provider=None):
    contribution = PageTypeContribution(
        ExtensionDescriptor("example.structured", "Structured document"),
        "Structured page",
        detector=lambda source: source.startswith("BEGIN STRUCTURED"),
        parser_factory=Parser,
        renderer_factory=object,
        activation_warning=activation_warning,
        presentation_modes=(
            "source",
            "example.structured-editor",
            "reading",
        ),
    )
    renderer = PageRendererContribution(
        ExtensionDescriptor(
            "example.structured-renderer",
            "Structured renderer",
        ),
        page_type_id="example.structured",
        renderer_factory=Renderer,
        target_formats=(BBCODE, MARKDOWN),
    )
    registry = PluginRegistry()
    registrar = registry.registrar("example.plugin")
    registrar.register_presentation_mode(PresentationModeContribution(
        ExtensionDescriptor(
            "example.structured-editor",
            "Structured editor",
        ),
        view_factory=QWidget,
    ))
    registrar.register_page_type(contribution)
    registrar.register_page_renderer(renderer)
    registry.install("example.plugin", registrar.contributions)
    return (
        PageTypeService(
            registry,
            InMemoryPluginOptionStore(),
            source_provider=source_provider,
        ),
        contribution,
    )


def test_detected_page_type_can_be_explicitly_disabled():
    service, contribution = make_service()
    item = outlineItem(title="Structured", _type="md")
    item.setData(Outline.text, "BEGIN STRUCTURED\nEND STRUCTURED")

    assert service.is_enabled(item, contribution)

    service.set_enabled(item, contribution, False)

    assert not service.is_enabled(item, contribution)


def test_page_type_activation_warns_before_committing_checkbox(
        monkeypatch):
    seen_sources = []
    service, contribution = make_service(
        activation_warning=lambda source: (
            seen_sources.append(source)
            or "Existing body text will be reinterpreted."
        ),
        source_provider=lambda _item: "live unsaved body",
    )
    item = outlineItem(title="Ordinary", _type="md")
    item.setData(Outline.text, "stale submitted body")
    view = propertiesView()
    view.setPageTypeService(service)
    view._currentPropertyItems = (item,)
    view._syncPluginProperties()
    checkbox = view.findChild(
        QCheckBox,
        "pluginPropertyexample_structured",
    )
    answers = iter((QMessageBox.Cancel, QMessageBox.Yes))
    shown = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message, *_args: (
            shown.append((title, message))
            or next(answers)
        ),
    )

    checkbox.setChecked(True)

    assert not service.is_enabled(item, contribution)
    assert not checkbox.isChecked()

    checkbox.setChecked(True)

    assert service.is_enabled(item, contribution)
    assert checkbox.isChecked()
    assert seen_sources == ["live unsaved body", "live unsaved body"]
    assert shown == [
        (
            "Enable Structured page?",
            "Existing body text will be reinterpreted.",
        ),
        (
            "Enable Structured page?",
            "Existing body text will be reinterpreted.",
        ),
    ]


def test_rebuilding_page_type_properties_detaches_old_controls():
    service, _contribution = make_service()
    view = propertiesView()
    view.setPageTypeService(service)
    old_checkbox = view.findChild(
        QCheckBox,
        "pluginPropertyexample_structured",
    )

    view._rebuildPluginProperties()

    checkboxes = view.findChildren(
        QCheckBox,
        "pluginPropertyexample_structured",
    )
    assert len(checkboxes) == 1
    assert checkboxes[0] is not old_checkbox
    assert old_checkbox.parent() is None


def test_active_page_type_selects_core_and_owned_catalogue_modes():
    service, contribution = make_service()
    item = outlineItem(title="Structured", _type="md")
    item.setData(Outline.text, "ordinary source")
    service.set_enabled(item, contribution, True)
    state = service.create_state(item)

    assert tuple(
        definition.key for definition in state.presentation_modes()
    ) == (
        MarkdownPresentationMode.SOURCE,
        "example.structured-editor",
        MarkdownPresentationMode.READING,
    )
    assert service.export_document(item, BBCODE) == (
        PageExportDocument("STRUCTURED:ordinary source", BBCODE)
    )


def test_page_renderer_uses_fallback_until_an_exact_route_is_selected():
    service, contribution = make_service()
    item = outlineItem(title="Structured", _type="md")
    item.setData(Outline.text, "ordinary source")
    service.set_enabled(item, contribution, True)

    fallback = service.export_document(item, HTML)

    assert fallback == PageExportDocument(
        "STRUCTURED:ordinary source",
        MARKDOWN,
    )

    class HtmlRenderer:
        def render(self, model, target_format, options):
            return PageExportDocument(
                '<section data-style="{}">{}</section>'.format(
                    options["style"],
                    model,
                ),
                target_format,
            )

    html_renderer = PageRendererContribution(
        ExtensionDescriptor(
            "another.structured-html",
            "Alternate structured HTML",
        ),
        page_type_id="example.structured",
        renderer_factory=HtmlRenderer,
        target_formats=(HTML,),
        options=(OptionField("style", "Style", default="classic"),),
    )
    registrar = service.registry.registrar("another.plugin")
    registrar.register_page_renderer(html_renderer)
    service.registry.install("another.plugin", registrar.contributions)
    service.option_store.save(
        "another.structured-html",
        {"style": "custom"},
    )
    service.select_renderer(
        "example.structured",
        "html:html",
        "another.structured-html",
        representation_format=HTML,
    )

    rendered = service.export_document(
        item,
        HTML,
        route_id="html:html",
    )

    assert service.selected_renderer_id(
        "example.structured",
        "html:html",
    ) == "another.structured-html"
    assert rendered == PageExportDocument(
        '<section data-style="custom">STRUCTURED:ordinary source</section>',
        HTML,
    )
