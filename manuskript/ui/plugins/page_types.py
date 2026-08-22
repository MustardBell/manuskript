import logging
import re

from PyQt5.QtCore import QObject, pyqtSignal

from manuskript.plugins.api import PageExportDocument
from manuskript.plugins.execution import (
    run_page_format_renderer,
    run_page_parser,
)
from manuskript.media_types import (
    MARKDOWN,
    MediaTypeError,
    core_registry,
)
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
    PresentationModeDefinition,
    contributed_presentation_view,
    core_presentation_modes,
)
from manuskript.plugins.contracts import (
    ContributionKind,
    ContributionScope,
)


LOGGER = logging.getLogger(__name__)

#: Bytes of head and of tail a callable detector may inspect.
RECOGNITION_WINDOW = 4096


def matches_signature(signature, text):
    """Whether ``text`` satisfies every part of a declared signature."""
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    checks = []
    if signature.starts_with:
        checks.append(signature.starts_with)
    if signature.ends_with:
        checks.append(signature.ends_with)
    checks.extend(signature.contains)
    for pattern in checks:
        try:
            if re.search(pattern, normalized, re.MULTILINE) is None:
                return False
        except re.error:
            LOGGER.exception(
                "Invalid page type signature pattern %r", pattern
            )
            return False
    return True


class PageTypeService(QObject):
    """Resolve plugin page capabilities against individual outline items."""

    contributionsChanged = pyqtSignal()

    SELECTION_PREFIX = "manuskript.page-renderers."

    def __init__(
            self, registry, option_store=None, report_error=None,
            source_provider=None, media_types=None, scope_grants=None,
            parent=None):
        super().__init__(parent)
        self.registry = registry
        self.option_store = option_store
        self.mediaTypes = (
            media_types if media_types is not None else core_registry()
        )
        self._report_error = report_error or (
            lambda _message, _duration=5000, _importance=2: None
        )
        self._source_provider = source_provider
        self.scopeGrants = scope_grants

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

    def presentation_modes_for(self, contribution, markup_base_id="markdown"):
        """Resolve one page owner's ordered selection from the catalogue.

        Core publishes its modes and every plugin declaration.  A page type
        can select core entries and entries installed by its own plugin; it
        cannot address another plugin directly.  Broader ``all`` reach is a
        grant surface and remains unavailable until that grant is present.
        """

        core = {definition.id: definition
                for definition in core_presentation_modes()}
        catalogue = dict(core)
        if contribution is None:
            owner = "core"
            selected = list(
                (mode.value for mode in MarkdownPresentationMode)
                if markup_base_id == "markdown"
                else [
                    MarkdownPresentationMode.SOURCE.value,
                    MarkdownPresentationMode.FORMATTED_SOURCE.value,
                ]
            )
        else:
            owner = self.registry.owner_of(
                ContributionKind.PAGE_TYPE,
                contribution.descriptor.id,
            )
            selected = list(
                contribution.presentation_modes
                or (MarkdownPresentationMode.SOURCE.value,)
            )
        for record in self.registry.records(
            ContributionKind.PRESENTATION_MODE
        ):
            if record.plugin_id != owner:
                continue
            mode = record.contribution
            catalogue[mode.descriptor.id] = PresentationModeDefinition(
                id=mode.descriptor.id,
                label=mode.descriptor.name,
                view_factory=contributed_presentation_view,
                owner_id=record.plugin_id,
                widget_factory=mode.view_factory,
                error_handler=(
                    lambda error, contribution=mode:
                    self.report_error(contribution, error)
                ),
            )
        missing = tuple(
            mode_id for mode_id in selected if mode_id not in catalogue
        )
        if missing and contribution is not None:
            LOGGER.error(
                "Page type %s selected unavailable presentation modes: %s",
                contribution.descriptor.id,
                ", ".join(missing),
            )
        definitions = [
            catalogue[mode_id]
            for mode_id in selected
            if mode_id in catalogue
        ]
        definitions = self._include_granted_global_modes(
            definitions, owner
        )
        return tuple(definitions)

    def _include_granted_global_modes(self, definitions, page_owner):
        """Add reader-granted modes from outside the page owner's policy."""

        existing = {definition.id for definition in definitions}
        additions = []
        for record in sorted(
            self.registry.records(ContributionKind.PRESENTATION_MODE),
            key=lambda value: (
                value.contribution.descriptor.name.casefold(),
                value.id,
            ),
        ):
            mode = record.contribution
            if (
                record.plugin_id == page_owner
                or record.id in existing
                or mode.scope is not ContributionScope.ALL
                or self.scopeGrants is None
                or not self.scopeGrants.scope_granted(
                    record.plugin_id,
                    ContributionKind.PRESENTATION_MODE,
                    record.id,
                    ContributionScope.ALL,
                )
            ):
                continue
            additions.append(PresentationModeDefinition(
                id=mode.descriptor.id,
                label=mode.descriptor.name,
                view_factory=contributed_presentation_view,
                owner_id=record.plugin_id,
                widget_factory=mode.view_factory,
                error_handler=(
                    lambda error, contribution=mode:
                    self.report_error(contribution, error)
                ),
            ))
        reading = next((
            index for index, definition in enumerate(definitions)
            if definition.key is MarkdownPresentationMode.READING
        ), len(definitions))
        return definitions[:reading] + additions + definitions[reading:]

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
            # Already decided for this item: recognition is a cold start
            # problem only, and the answer is recorded once it is known.
            return bool(item.pluginValue(contribution_id))
        if contribution.signature is not None:
            # Core matches the plugin's declared pattern, so plugin code is
            # never handed the text of a document that is not its own.
            return matches_signature(contribution.signature, item.text())
        if contribution.detector is None:
            return False
        try:
            return bool(contribution.detector(
                self.recognition_window(item.text())
            ))
        except Exception as error:
            self.report_error(contribution, error)
            return False

    @staticmethod
    def recognition_window(text):
        """The slice a callable detector may see.

        A signature is preferred precisely because it needs no window. For
        formats a signature cannot express, the head and tail are enough to
        spot a delimited document while keeping the body out of reach.
        """
        text = str(text or "")
        if len(text) <= 2 * RECOGNITION_WINDOW:
            return text
        return "{}\n{}".format(
            text[:RECOGNITION_WINDOW],
            text[-RECOGNITION_WINDOW:],
        )

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
            return PageExportDocument(source, MARKDOWN)
        resolved = self.resolve_renderer(
            page_type.descriptor.id,
            target_format,
            route_id=route_id,
        )
        if resolved is None:
            # Unassigned: nothing can render this page type into anything
            # this destination accepts. The source goes in as it stands
            # rather than the export failing outright.
            LOGGER.warning(
                "No renderer produces %s for page type %s; including the "
                "page source unrendered.",
                target_format,
                page_type.descriptor.id,
            )
            return PageExportDocument(source, MARKDOWN)
        renderer, render_format = resolved
        try:
            model = run_page_parser(page_type, source)
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

    def fallback_chain(self, target_format):
        """This media type, then everything that may stand in for it.

        Corrupted stored choices can describe a loop. That is worth
        reporting, not worth refusing to export over, so the exact type is
        used alone.
        """
        try:
            return self.mediaTypes.fallback_chain(target_format)
        except MediaTypeError as error:
            LOGGER.warning(
                "Ignoring media type fallbacks for %s: %s",
                target_format,
                error,
            )
            return (target_format,)

    def renderers_for(self, page_type_id, target_format):
        """Renderers able to produce this page type, best match first.

        An exact match ranks above anything standing in for the format, and
        each step of the fallback chain above the next. Which renderer that
        is has nothing to do with which plugin provides it: a second plugin
        offering the same format becomes selectable by being installed.
        """
        owned = [
            renderer
            for renderer in self.registry.page_renderers
            if renderer.page_type_id == page_type_id
        ]
        ranked = []
        for media_type in self.fallback_chain(target_format):
            matches = sorted(
                (
                    renderer
                    for renderer in owned
                    if media_type in renderer.target_formats
                    and renderer not in ranked
                ),
                key=lambda renderer: (
                    -renderer.priority,
                    renderer.descriptor.id,
                ),
            )
            ranked.extend(matches)
        return tuple(ranked)

    def resolve_renderer(
            self, page_type_id, target_format, route_id=None):
        """The renderer an export would use, or None when there is none.

        Nothing producing a format is a legal state, not an error. A plugin
        may promise to consume a format nothing provides yet, and the answer
        is that the route is unassigned.
        """
        candidates = self.renderers_for(page_type_id, target_format)
        if not candidates:
            return None
        selected = self.selected_renderer_id(
            page_type_id,
            route_id or target_format,
        )
        renderer = next((
            candidate
            for candidate in candidates
            if candidate.descriptor.id == selected
        ), candidates[0])
        render_format = next(
            (
                media_type
                for media_type in self.fallback_chain(target_format)
                if media_type in renderer.target_formats
            ),
            target_format,
        )
        return renderer, render_format

    def selected_renderer_id(self, page_type_id, target_format):
        if self.option_store is None:
            return ""
        values = self.option_store.load_values(
            self.SELECTION_PREFIX + page_type_id
        )
        return str(values.get(target_format, ""))

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
        if not renderer_id:
            # Choosing nothing is a choice: it hands the route back to
            # whichever renderer currently ranks highest.
            self._forget_renderer(page_type_id, route_id)
            return
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

    def _forget_renderer(self, page_type_id, route_id):
        if self.option_store is None:
            return
        key = self.SELECTION_PREFIX + page_type_id
        values = self.option_store.load_values(key)
        if values.pop(route_id, None) is None:
            return
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
        service.contributionsChanged.connect(self._service_changed)

    @property
    def item(self):
        return self._item

    @property
    def contribution(self):
        return self._contribution

    @property
    def is_active(self):
        return self._contribution is not None

    def presentation_modes(self, markup_base_id="markdown"):
        return self.service.presentation_modes_for(
            self._contribution,
            markup_base_id,
        )

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

    def _service_changed(self):
        # The active page type may be unchanged while the reader grants or
        # revokes a catalogue entry. Leaf owners still have to recompute.
        self.refresh(force=True)
