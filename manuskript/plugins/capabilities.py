"""Services Manuskript offers plugins, and the names they are asked for by.

Core decides what appears here. A plugin cannot reach a service that is not
in this catalogue, and cannot reach one it did not declare in its manifest,
so the surface a plugin touches is always the intersection of what core
publishes and what the plugin asked for.

Adding an entry is a promise: the name and the shape of the object it yields
become part of the plugin contract for this ``api_version``.
"""

from dataclasses import dataclass
from typing import Callable


#: Markdown to forum BBCode conversion, extendable per plugin.
CAPABILITY_MARKUP_BBCODE = "markup.bbcode"


@dataclass(frozen=True)
class Capability:
    """One named service, and how to build the object plugins receive."""

    name: str
    summary: str
    factory: Callable[[], object]


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
)


def capability_catalogue():
    """Every capability core currently provides, keyed by name."""
    return {capability.name: capability for capability in CAPABILITIES}


def grant(names):
    """Build the objects for ``names``, and report the ones core lacks.

    Returns ``(granted, missing)``. Nothing is built for a name core does
    not have, so an unsatisfiable plugin costs nothing to refuse.
    """
    catalogue = capability_catalogue()
    missing = tuple(name for name in names if name not in catalogue)
    if missing:
        return {}, missing
    granted = {
        name: catalogue[name].factory()
        for name in names
    }
    return granted, ()
