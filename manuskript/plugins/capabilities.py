"""Services Manuskript offers plugins, and the names they are asked for by.

Core decides what appears here. A plugin cannot reach a service that is not
in this catalogue, and cannot reach one it did not declare in its manifest,
so the surface a plugin touches is always the intersection of what core
publishes and what the plugin asked for.

Adding an entry is a promise: the name and the shape of the object it yields
become part of the plugin contract for this ``api_version``.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional


#: Markdown to forum BBCode conversion, extendable per plugin.
CAPABILITY_MARKUP_BBCODE = "markup.bbcode"

#: Build the panel that routes a plugin's page types to export formats.
CAPABILITY_UI_EXPORT_ROUTING = "ui.export_routing"

#: Read what the shared media type vocabulary currently contains.
CAPABILITY_MEDIA_REGISTRY = "media.registry"

#: Convert one markup into another, with whatever plugins have added to it.
CAPABILITY_CONVERSION = "conversion"

#: Read the manuscript an editor workspace was opened over.
CAPABILITY_OUTLINE_READ = "outline.read"

#: Change the manuscript: text, titles, compile flags, new documents.
CAPABILITY_OUTLINE_WRITE = "outline.write"

#: Put editor panes on screen and drive them.
CAPABILITY_EDITOR_CONTROL = "editor.control"

CAPABILITY_ENTITIES_READ = "entities.read"
CAPABILITY_ENTITIES_WRITE = "entities.write"
CAPABILITY_REFERENCES_READ = "references.read"
CAPABILITY_REFERENCES_WRITE = "references.write"
CAPABILITY_ASSERTIONS_READ = "assertions.read"
CAPABILITY_ASSERTIONS_WRITE = "assertions.write"
CAPABILITY_TIMELINE_READ = "timeline.read"
CAPABILITY_QUERY_EXECUTE = "query.execute"
CAPABILITY_MORPHOLOGY_REGISTRY = "morphology.registry"


@dataclass(frozen=True)
class PluginCapabilityContext:
    """What a capability may be built from, beyond nothing at all.

    Some services cannot come from a plain factory because they have to see
    what other plugins contributed -- a conversion carries their additions --
    and reaching a runtime through a global to find that out would be the
    service locator this codebase has spent its recent history removing. So
    the runtime hands over what it has, and the catalogue says which
    capabilities want it.

    ``conversion_service`` is a callable rather than an object so that
    nothing is built for a plugin that never asked.
    """

    registry: Any = None
    conversion_service: Optional[Callable[[], object]] = None


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
    #: Built from what the runtime knows -- the plugin registry, a way to
    #: report -- rather than from nothing. A capability that has to see what
    #: other plugins contributed cannot be built by a plain factory, and
    #: making the runtime a global to reach it would be worse.
    builder: Optional[Callable[[Any], object]] = None

    @property
    def deferred(self):
        return self.factory is None and self.builder is None


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
    Capability(
        name=CAPABILITY_CONVERSION,
        summary=(
            "Convert markup between two media types: convert(text, "
            "source_format, target_format). What other plugins have added "
            "to that conversion is applied for you, so your rendering "
            "matches every other rendering of the same markup. Ask "
            "can_convert() first, or handle UnknownRoute."
        ),
        builder=lambda context: context.conversion_service(),
    ),
    Capability(
        name=CAPABILITY_OUTLINE_READ,
        summary=(
            "Read the manuscript your editor workspace was opened over: "
            "the selected items, every document, and word of it changing. "
            "Your workspace context's outline reads but cannot write."
        ),
    ),
    Capability(
        name=CAPABILITY_OUTLINE_WRITE,
        summary=(
            "Change the manuscript from an editor workspace: text, "
            "titles, compile flags, and new or duplicated documents. "
            "Includes everything outline.read offers, so asking for both "
            "is unnecessary."
        ),
    ),
    Capability(
        name=CAPABILITY_EDITOR_CONTROL,
        summary=(
            "Put editor panes in your workspace and drive them: cursor, "
            "selection, scrolling, presentation and the editing lock. "
            "Without it your workspace context has no editor factory."
        ),
    ),
    Capability(
        name=CAPABILITY_ENTITIES_READ,
        summary="Read stable snapshots of generic project entities.",
    ),
    Capability(
        name=CAPABILITY_ENTITIES_WRITE,
        summary=(
            "Create and update generic entities through project commands; "
            "includes entities.read."
        ),
    ),
    Capability(
        name=CAPABILITY_REFERENCES_READ,
        summary=(
            "Read explicit wikilink occurrences, backlinks, and completion."
        ),
    ),
    Capability(
        name=CAPABILITY_REFERENCES_WRITE,
        summary=(
            "Insert source-owned wikilinks through a guarded outline edit; "
            "includes references.read."
        ),
    ),
    Capability(
        name=CAPABILITY_ASSERTIONS_READ,
        summary="Read explicit assertions, provenance, and diagnostics.",
    ),
    Capability(
        name=CAPABILITY_ASSERTIONS_WRITE,
        summary=(
            "Append or remove fenced source-owned assertions through a "
            "guarded outline edit; includes assertions.read."
        ),
    ),
    Capability(
        name=CAPABILITY_TIMELINE_READ,
        summary=(
            "Read partial story chronology and evaluate explicit temporal "
            "assertions without treating unknown order as false."
        ),
    ),
    Capability(
        name=CAPABILITY_QUERY_EXECUTE,
        summary=(
            "Execute the stable typed query AST over entities, references, "
            "and explicit assertions."
        ),
    ),
    Capability(
        name=CAPABILITY_MORPHOLOGY_REGISTRY,
        summary=(
            "Register a namespaced deterministic morphology provider and "
            "inspect available providers."
        ),
    ),
)


def capability_catalogue():
    """Every capability core currently provides, keyed by name."""
    return {capability.name: capability for capability in CAPABILITIES}


def grant(names, context=None):
    """Build the objects for ``names``, and report the ones core lacks.

    Returns ``(granted, missing)``. Nothing is built for a name core does
    not have, so an unsatisfiable plugin costs nothing to refuse. Deferred
    services are validated but not built: they are delivered later, by the
    UI host, which is the only thing that can scope them to a plugin.

    ``context`` is what the runtime knows and a plain factory cannot: the
    plugin registry, chiefly, for a service that must see what other plugins
    contributed. A capability needing one and given none is treated as
    missing rather than half-built, so a plugin is refused honestly.
    """
    catalogue = capability_catalogue()
    missing = list(name for name in names if name not in catalogue)
    if not missing:
        missing = [
            name for name in names
            if catalogue[name].builder is not None and context is None
        ]
    if missing:
        return {}, tuple(missing)
    granted = {}
    for name in names:
        capability = catalogue[name]
        if capability.builder is not None:
            granted[name] = capability.builder(context)
        elif capability.factory is not None:
            granted[name] = capability.factory()
    return granted, ()
