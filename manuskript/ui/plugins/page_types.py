import logging

from PyQt5.QtCore import QObject, pyqtSignal

from manuskript.plugins.api import PageExportDocument
from manuskript.plugins.execution import (
    run_page_format_renderer,
    run_page_parser,
)
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)


LOGGER = logging.getLogger(__name__)


class PageTypeService(QObject):
    """Resolve plugin page capabilities against individual outline items."""

    contributionsChanged = pyqtSignal()

    SELECTION_PREFIX = "manuskript.page-renderers."

    def __init__(
            self, registry, option_store=None, report_error=None,
            source_provider=None, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.option_store = option_store
        self._report_error = report_error or (
            lambda _message, _duration=5000, _importance=2: None
        )
        self._source_provider = source_provider

    @property
    def contributions(self):
        return tuple(sorted(
            self.registry.page_types,
            key=lambda value: value.descriptor.id,
        ))

    def refresh(self):
        self.contributionsChanged.emit()

    def create_state(self, item=None, parent=None):
        return PageTypeState(self, item=item, parent=parent)

    def is_applicable(self, item, contribution):
        return (
            item is not None
            and item.type() in contribution.item_kinds
        )

    def is_enabled(self, item, contribution):
        if not self.is_applicable(item, contribution):
            return False
        contribution_id = contribution.descriptor.id
        if item.hasPluginValue(contribution_id):
            return bool(item.pluginValue(contribution_id))
        if contribution.detector is None:
            return False
        try:
            return bool(contribution.detector(item.text()))
        except Exception as error:
            self.report_error(contribution, error)
            return False

    def set_enabled(self, item, contribution, enabled):
        if not self.is_applicable(item, contribution):
            return False
        enabled = bool(enabled)
        if (
            item.hasPluginValue(contribution.descriptor.id)
            and bool(item.pluginValue(contribution.descriptor.id))
            is enabled
        ):
            return False
        item.setPluginValue(contribution.descriptor.id, enabled)
        return True

    def activation_warning(self, item, contribution):
        operation = contribution.activation_warning
        if operation is None or not self.is_applicable(item, contribution):
            return ""
        source = (
            self._source_provider(item)
            if self._source_provider is not None
            else item.text()
        )
        try:
            return str(operation(source) or "")
        except Exception as error:
            self.report_error(contribution, error)
            return (
                "The plugin could not inspect this page before "
                "activation. Enabling it may reinterpret existing text."
            )

    def active_for(self, item):
        matches = [
            contribution
            for contribution in self.contributions
            if self.is_enabled(item, contribution)
        ]
        if len(matches) > 1:
            LOGGER.warning(
                "Multiple page types apply to outline item %s; using %s.",
                item.ID(),
                matches[0].descriptor.id,
            )
        return matches[0] if matches else None

    def export_document(
            self, item, target_format, source=None,
            route_id=None):
        source = item.text() if source is None else source
        page_type = self.active_for(item)
        if page_type is None or page_type.parser_factory is None:
            return PageExportDocument(source, "markdown")
        try:
            model = run_page_parser(page_type, source)
            renderer, render_format = self.resolve_renderer(
                page_type.descriptor.id,
                target_format,
                route_id=route_id,
            )
            options = (
                self.option_store.load(
                    renderer.descriptor.id,
                    renderer.options,
                )
                if self.option_store is not None
                else None
            )
            return run_page_format_renderer(
                renderer,
                model,
                render_format,
                options,
            )
        except Exception as error:
            self.report_error(page_type, error)
            raise

    def renderers_for(self, page_type_id, target_format):
        exact = [
            renderer
            for renderer in self.registry.page_renderers
            if renderer.page_type_id == page_type_id
            and target_format in renderer.target_formats
        ]
        fallback = [
            renderer
            for renderer in self.registry.page_renderers
            if renderer.page_type_id == page_type_id
            and "markdown" in renderer.target_formats
            and renderer not in exact
        ]
        key = lambda renderer: (
            -renderer.priority,
            renderer.descriptor.id,
        )
        return tuple(sorted(exact, key=key) + sorted(fallback, key=key))

    def resolve_renderer(
            self, page_type_id, target_format, route_id=None):
        candidates = self.renderers_for(page_type_id, target_format)
        if not candidates:
            raise RuntimeError(
                "No renderer is available for page type {} as {} or "
                "Markdown.".format(page_type_id, target_format)
            )
        selected = self.selected_renderer_id(
            page_type_id,
            route_id or target_format,
        )
        renderer = next((
            candidate
            for candidate in candidates
            if candidate.descriptor.id == selected
        ), candidates[0])
        render_format = (
            target_format
            if target_format in renderer.target_formats
            else "markdown"
        )
        return renderer, render_format

    def selected_renderer_id(self, page_type_id, target_format):
        if self.option_store is None:
            return ""
        values = self.option_store.load_values(
            self.SELECTION_PREFIX + page_type_id
        )
        selected = values.get(target_format, "")
        if not selected and ":" in target_format:
            # Renderer routes used the representation itself before
            # exporters began publishing stable destination routes.
            selected = values.get(target_format.rsplit(":", 1)[-1], "")
        return str(selected)

    def select_renderer(
            self, page_type_id, route_id, renderer_id,
            representation_format=None):
        representation_format = (
            representation_format or route_id
        )
        candidates = self.renderers_for(
            page_type_id,
            representation_format,
        )
        if renderer_id not in {
            renderer.descriptor.id for renderer in candidates
        }:
            raise ValueError(
                "Renderer {!r} cannot render {} as {}.".format(
                    renderer_id,
                    page_type_id,
                    representation_format,
                )
            )
        if self.option_store is None:
            raise RuntimeError("Page renderer preferences are unavailable.")
        key = self.SELECTION_PREFIX + page_type_id
        values = self.option_store.load_values(key)
        values[route_id] = renderer_id
        self.option_store.save(key, values)
        self.contributionsChanged.emit()

    def report_error(self, contribution, error):
        message = "Page plugin {} failed: {}: {}".format(
            contribution.descriptor.name,
            type(error).__name__,
            error,
        )
        LOGGER.exception(message)
        self._report_error(message, 8000, 2)


class PageTypeState(QObject):
    """Active plugin page type for one canonical outline item."""

    changed = pyqtSignal()

    def __init__(self, service, item=None, parent=None):
        super().__init__(parent)
        self.service = service
        self._item = item
        self._contribution = service.active_for(item)
        service.contributionsChanged.connect(self.refresh)

    @property
    def item(self):
        return self._item

    @property
    def contribution(self):
        return self._contribution

    @property
    def is_active(self):
        return self._contribution is not None

    @property
    def allowed_presentation_modes(self):
        contribution = self._contribution
        if contribution is None or not any((
            contribution.renderer_factory,
            contribution.wizard_factory,
        )):
            return None
        modes = [MarkdownPresentationMode.SOURCE]
        if contribution.wizard_factory is not None:
            modes.append(MarkdownPresentationMode.LIVE_PREVIEW)
        if contribution.renderer_factory is not None:
            modes.append(MarkdownPresentationMode.READING)
        return tuple(modes)

    def set_item(self, item):
        if item is self._item:
            self.refresh()
            return
        self._item = item
        self.refresh(force=True)

    def refresh(self, force=False):
        contribution = self.service.active_for(self._item)
        if contribution is self._contribution and not force:
            return
        self._contribution = contribution
        self.changed.emit()
