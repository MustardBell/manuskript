"""Pure syntax and identity rules for project references.

References are persisted in project text, so recognizing and constructing them
must not depend on a running Qt application, a palette, or any particular view.
"""

import re
from dataclasses import dataclass
from typing import Optional


REFERENCE_PATTERN = r"{(\w):(\d+):?.*?}"
REFERENCE_PATTERN_NON_CAPTURING = r"{\w:\d+:?.*?}"
REFERENCE_TEMPLATE = "{{{}:{}:{}}}"
REFERENCE_SEARCH_PREFIX_TEMPLATE = "{{{}:{}:"

CHARACTER_REFERENCE_KIND = "C"
TEXT_REFERENCE_KIND = "T"
PLOT_REFERENCE_KIND = "P"
WORLD_REFERENCE_KIND = "W"


@dataclass(frozen=True)
class ReferenceIdentity:
    """The stable, presentation-independent identity encoded by a reference."""

    kind: str
    identifier: str

    @classmethod
    def parse(cls, value: str) -> Optional["ReferenceIdentity"]:
        match = re.fullmatch(REFERENCE_PATTERN, value)
        if match is None:
            return None
        return cls(match.group(1), match.group(2))

    def render(self, label: str = "") -> str:
        return REFERENCE_TEMPLATE.format(self.kind, self.identifier, label)

    def search_prefix(self) -> str:
        return REFERENCE_SEARCH_PREFIX_TEMPLATE.format(
            self.kind,
            self.identifier,
        )


def make_reference(kind, identifier, searchable=False, label=""):
    """Construct either a complete persisted reference or its search prefix."""
    identity = ReferenceIdentity(str(kind), str(identifier))
    if searchable:
        return identity.search_prefix()
    return identity.render(label)


def character_reference(identifier, searchable=False):
    return make_reference(
        CHARACTER_REFERENCE_KIND,
        identifier,
        searchable=searchable,
    )


def text_reference(identifier, searchable=False):
    return make_reference(TEXT_REFERENCE_KIND, identifier, searchable=searchable)


def plot_reference(identifier, searchable=False):
    return make_reference(PLOT_REFERENCE_KIND, identifier, searchable=searchable)


def world_reference(identifier, searchable=False):
    return make_reference(WORLD_REFERENCE_KIND, identifier, searchable=searchable)
