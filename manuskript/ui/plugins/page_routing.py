"""Per-plugin access to page renderer routing.

A plugin configures how *its own* page types are rendered. The renderers it
may choose between can come from any plugin, because a page type from one
plugin is legitimately rendered by another's renderer -- but the page type
being routed must belong to the caller. The gateway enforces that, so a
settings panel cannot reach a neighbouring plugin's routing even by mistake.
"""

from manuskript.plugins.errors import PluginScopeError
from manuskript.plugins.registry import ContributionKind


class PageRoutingGateway:
    """Route one plugin's page types, and refuse every other plugin's."""

    def __init__(
            self, plugin_id, registry, page_types,
            export_routes_provider=None, edit_options=None,
            show_status=None):
        self.plugin_id = plugin_id
        self._registry = registry
        self._pageTypes = page_types
        self._routesProvider = export_routes_provider
        self.edit_options = edit_options or (
            lambda _renderer, _parent=None: None
        )
        self.show_status = show_status or (
            lambda _message, _duration=5000, _importance=2: None
        )

    def fallback_chain(self, media_type):
        """What a format resolves to, for explaining a stand-in choice."""
        return self._pageTypes.fallback_chain(media_type)

    def label_for(self, media_type):
        """A displayable name for a media type."""
        return self._pageTypes.mediaTypes.label(media_type)

    def require_owned(self, page_type_id):
        """Public form of the ownership check, for building panels."""
        self._require_owned(page_type_id)

    @property
    def page_types(self):
        """Page types this plugin registered, sorted by display name."""
        return tuple(sorted(
            (
                record.contribution
                for record in self._registry.plugin_records(
                    self.plugin_id,
                    ContributionKind.PAGE_TYPE,
                )
            ),
            key=lambda value: value.descriptor.name,
        ))

    @property
    def export_routes(self):
        """Every export destination that consumes rendered pages."""
        if self._routesProvider is None:
            return ()
        return tuple(self._routesProvider())

    def owns(self, page_type_id):
        return any(
            contribution.descriptor.id == page_type_id
            for contribution in self.page_types
        )

    def candidates(self, page_type_id, representation_format):
        """Renderers able to render this page type, from any plugin."""
        self._require_owned(page_type_id)
        return self._pageTypes.renderers_for(
            page_type_id,
            representation_format,
        )

    def owner_of(self, renderer_id):
        """Plugin ID providing a renderer, so panels can attribute it."""
        return self._registry.owner_of(
            ContributionKind.PAGE_RENDERER,
            renderer_id,
        )

    def selected(self, page_type_id, route_id):
        """The saved renderer ID, or '' when the route was never chosen."""
        self._require_owned(page_type_id)
        return self._pageTypes.selected_renderer_id(page_type_id, route_id)

    def resolve(self, page_type_id, representation_format, route_id=None):
        """The renderer an export would really use, saved choice or not."""
        self._require_owned(page_type_id)
        return self._pageTypes.resolve_renderer(
            page_type_id,
            representation_format,
            route_id=route_id,
        )

    def select(
            self, page_type_id, route_id, renderer_id,
            representation_format=None):
        self._require_owned(page_type_id)
        self._pageTypes.select_renderer(
            page_type_id,
            route_id,
            renderer_id,
            representation_format=representation_format,
        )

    def _require_owned(self, page_type_id):
        if not self.owns(page_type_id):
            raise PluginScopeError(
                "Plugin {} cannot route page type {!r}, which it does "
                "not provide.".format(self.plugin_id, page_type_id)
            )
