"""Resolve persisted project references without consulting UI globals."""

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from manuskript.enums import Outline
from manuskript.models.reference_identity import (
    CHARACTER_REFERENCE_KIND,
    PLOT_REFERENCE_KIND,
    REFERENCE_PATTERN,
    REFERENCE_PATTERN_NON_CAPTURING,
    REFERENCE_SEARCH_PREFIX_TEMPLATE,
    REFERENCE_TEMPLATE,
    ReferenceIdentity,
    TEXT_REFERENCE_KIND,
    WORLD_REFERENCE_KIND,
    character_reference,
    plot_reference,
    text_reference,
    world_reference,
)


LOGGER = logging.getLogger(__name__)

# Compatibility names used by persisted projects and existing extensions.
RegEx = REFERENCE_PATTERN
RegExNonCapturing = REFERENCE_PATTERN_NON_CAPTURING
EmptyRef = REFERENCE_TEMPLATE
EmptyRefSearchable = REFERENCE_SEARCH_PREFIX_TEMPLATE
CharacterLetter = CHARACTER_REFERENCE_KIND
TextLetter = TEXT_REFERENCE_KIND
PlotLetter = PLOT_REFERENCE_KIND
WorldLetter = WORLD_REFERENCE_KIND


@dataclass(frozen=True)
class ReferenceModels:
    """Project models used to resolve references."""

    outline: object
    characters: object
    plots: object
    world: object
    statuses: object
    labels: object

    @classmethod
    def for_project(cls, models):
        return cls(
            outline=models.outline,
            characters=models.characters,
            plots=models.plots,
            world=models.world,
            statuses=models.statuses,
            labels=models.labels,
        )


@dataclass(frozen=True)
class ReferenceNavigation:
    """Commands available when following a resolved reference."""

    open_character: Callable[[str], bool]
    open_text: Callable[[str], bool]
    open_plot: Callable[[str], bool]
    open_world: Callable[[str], bool]


def plotReference(identifier, searchable=False):
    return plot_reference(identifier, searchable=searchable)


def characterReference(identifier, searchable=False):
    return character_reference(identifier, searchable=searchable)


def textReference(identifier, searchable=False):
    return text_reference(identifier, searchable=searchable)


def worldReference(identifier, searchable=False):
    return world_reference(identifier, searchable=searchable)


def shortInfos(ref, models):
    """Return resolved summary data, ``-1`` if malformed, or ``None`` if unknown."""
    identity = ReferenceIdentity.parse(ref)
    if identity is None:
        return -1

    kind = identity.kind
    identifier = identity.identifier
    result = {"ID": identifier}

    if kind == TextLetter:
        result["type"] = TextLetter
        index = models.outline.getIndexByID(identifier)
        if not index.isValid():
            return None
        item = index.internalPointer()
        result["text_type"] = "folder" if item.isFolder() else "text"
        result["title"] = item.title()
        result["path"] = item.path()
        return result

    if kind == CharacterLetter:
        result["type"] = CharacterLetter
        character = models.characters.getCharacterByID(identifier)
        if character:
            result["title"] = character.name()
            result["name"] = character.name()
            return result

    if kind == PlotLetter:
        result["type"] = PlotLetter
        name = models.plots.getPlotNameByID(identifier)
        if name:
            result["title"] = name
            return result

    if kind == WorldLetter:
        result["type"] = WorldLetter
        item = models.world.itemByID(identifier)
        if item:
            result["title"] = item.text()
            result["path"] = models.world.path(item)
            return result

    return None


def title(ref, models):
    summary = shortInfos(ref, models)
    if summary and summary != -1:
        return summary.get("title")
    return None


def type(ref, models):
    summary = shortInfos(ref, models)
    if summary and summary != -1:
        return summary["type"]
    return None


def ID(ref, models):
    summary = shortInfos(ref, models)
    if summary and summary != -1:
        return summary["ID"]
    return None


def findReferencesTo(ref, models, parent=None, recursive=True):
    """Return text item IDs whose notes contain ``ref``."""
    outline = models.outline
    if parent is None:
        parent = outline.rootItem

    # Search both the labelled prefix and the bare form.
    prefix = ref[:ref.index(":", ref.index(":") + 1) + 1]
    bare = prefix[:-1] + "}"
    found = parent.findItemsContaining(
        prefix,
        [Outline.notes],
        recursive=recursive,
    )
    found += parent.findItemsContaining(
        bare,
        [Outline.notes],
        recursive=recursive,
    )
    return found


def open(ref, navigation: ReferenceNavigation):
    """Follow ``ref`` through explicitly supplied navigation commands."""
    identity = ReferenceIdentity.parse(ref)
    if identity is None:
        return None

    routes = {
        CharacterLetter: ("Character", navigation.open_character),
        TextLetter: ("Text", navigation.open_text),
        PlotLetter: ("Plot", navigation.open_plot),
        WorldLetter: ("World", navigation.open_world),
    }
    route = routes.get(identity.kind)
    if route is None:
        LOGGER.error("Unable to identify reference type: %s.", ref)
        return False

    label, command = route
    if command(identity.identifier):
        return True
    LOGGER.error("%s reference %s not found.", label, ref)
    return False
