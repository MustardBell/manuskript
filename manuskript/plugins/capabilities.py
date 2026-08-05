"""Services Manuskript offers plugins, and the names they are asked for by.

Core decides what appears here. A plugin cannot reach a service that is not
in this catalogue, and cannot reach one it did not declare in its manifest,
so the surface a plugin touches is always the intersection of what core
publishes and what the plugin asked for.

Adding an entry is a promise: the name and the shape of the object it yields
become part of the plugin contract for this ``api_version``.
"""

from dataclasses import dataclass
from typing import Callable, Optional


#: Markdown to forum BBCode conversion, extendable per plugin.
CAPABILITY_MARKUP_BBCODE = "markup.bbcode"

#: Build the panel that routes a plugin's page types to export formats.
CAPABILITY_UI_EXPORT_ROUTING = "ui.export_routing"

#: Read what the shared media type vocabulary currently contains.
CAPABILITY_MEDIA_REGISTRY = "media.registry"


@dataclass(frozen=True)
class Capability:
    """One named service, and how to build the object plugins receive.

    ``factory`` is absent for services the UI host builds. Those need a
    running application and a plugin to be scoped to, neither of which
    exists while plugins are loading, so they are handed over later --
    through ``PluginSettingsContext.capability`` -- rather than at
    registration. The name still gates at load: a plugin requiring one core
    does not have is refused before its code runs, exactly as before.
    """

    name: str
    summary: str
    factory: Optional[Callable[[], object]] = None

    @property
    def deferred(self):
        return self.factory is None


def _bbcode_converter():
    # Imported lazily: the catalogue is consulted during plugin loading, and
    # nothing should pay for a converter it never asks for.
    from manuskript.converters.markdownToBBCode import BBCodeConverter

    return BBCodeConverter()


CAPABILITIES = (
    Capability(
        name=CAPABILITY_MARKUP_BBCODE,
        summary=(
            "Convert Manuskript Markdown to forum BBCode. Call convert(), "
            "or extended(*rules) for a converter with extra rules of your "
            "own that does not affect anyone else."
        ),
        factory=_bbcode_converter,
    ),
    Capability(
        name=CAPABILITY_UI_EXPORT_ROUTING,
        summary=(
            "Build the panel that chooses which renderer produces each "
            "export format for one of your page types. Take it from your "
            "settings context and call panel(page_type_id, parent)."
        ),
    ),
    Capability(
        name=CAPABILITY_MEDIA_REGISTRY,
        summary=(
            "Read the shared media type vocabulary: labels, what stands "
            "in for a format, and who declared or promised what. Read "
            "only -- declaring is done in your manifest."
        ),
    ),
)


def capability_catalogue():
    """Every capability core currently provides, keyed by name."""
    return {capability.name: capability for capability in CAPABILITIES}


def grant(names):
    """Build the objects for ``names``, and report the ones core lacks.

    Returns ``(granted, missing)``. Nothing is built for a name core does
    not have, so an unsatisfiable plugin costs nothing to refuse. Deferred
    services are validated but not built: they are delivered later, by the
    UI host, which is the only thing that can scope them to a plugin.
    """
    catalogue = capability_catalogue()
    missing = tuple(name for name in names if name not in catalogue)
    if missing:
        return {}, missing
    granted = {
        name: catalogue[name].factory()
        for name in names
        if not catalogue[name].deferred
    }
    return granted, ()
