"""Language- and transport-neutral facts about Plugin API 1.

This module contains no plugin implementation objects and must remain safe to
load without Qt.  It is the small piece both an in-process driver and an RPC
driver can use to negotiate what the host actually supports.

API 1 is the first stable contract.  Development snapshots that used the same
integer before this stability declaration were design artifacts, not earlier
releases of API 1 and therefore are not compatibility targets.
"""

from dataclasses import dataclass
from enum import Enum

from manuskript.plugins.specification import protocol_document

_PROTOCOL_SPECIFICATION = protocol_document()
PLUGIN_API_VERSION = int(_PROTOCOL_SPECIFICATION["api_version"])
PLUGIN_API_STABILITY = "stable"
PLUGIN_PROTOCOL_VERSION = int(_PROTOCOL_SPECIFICATION["protocol_version"])

#: A grant a plugin was holding has ended: it was disabled or reloaded, the
#: project was closed or replaced, or the grant was withdrawn by name.
#:
#: Published here rather than kept inside the authority because it is a wire
#: value. A plugin in another language receives this same string and must be
#: able to recognise it, which is also why a plugin naming the literal is
#: reading the protocol rather than duplicating an implementation detail.
CAPABILITY_REVOKED = "plugin.capability_revoked"


class ContractPortability(str, Enum):
    """How a contract can be supplied by a plugin runtime."""

    PORTABLE = "portable"
    DECLARATIVE = "declarative"
    NATIVE = "native"


class ContributionKind(str, Enum):
    EXPORTER = "exporter"
    IMPORTER = "importer"
    CONVERTER = "converter"
    PROJECT_PANEL = "project_panel"
    SETTINGS_PANEL = "settings_panel"
    INDEX_CARD_STYLE = "index_card_style"
    EDITOR_WORKSPACE = "editor_workspace"
    PAGE_TYPE = "page_type"
    PRESENTATION_MODE = "presentation_mode"
    PAGE_RENDERER = "page_renderer"
    MARKUP = "markup"
    NATIVE_MARKUP = "native_markup"
    TRANSFORM = "transform"
    CONVERSION_AUGMENTATION = "conversion_augmentation"
    COMMAND = "command"


class ContributionScope(str, Enum):
    """How far a contribution asks to reach.

    ``own`` is implicit authority over things the contributing plugin owns.
    ``all`` is a separately grantable request to reach things owned by core
    or another plugin.  The vocabulary is shared by contribution kinds even
    though presentation modes are its first user.
    """

    OWN = "own"
    ALL = "all"


@dataclass(frozen=True)
class ContributionContract:
    kind: ContributionKind
    portability: ContractPortability
    reason: str


def _declared_portability(kind):
    return ContractPortability(
        _PROTOCOL_SPECIFICATION["contributions"][kind.value]["portability"]
    )


#: Reasons remain binding documentation; portability comes from the canonical
#: protocol document used by every language and by runtime negotiation.
CONTRIBUTION_CONTRACTS = (
    ContributionContract(
        ContributionKind.EXPORTER,
        _declared_portability(ContributionKind.EXPORTER),
        "Bounded request and content response.",
    ),
    ContributionContract(
        ContributionKind.IMPORTER,
        _declared_portability(ContributionKind.IMPORTER),
        "Bounded source and declarative import tree.",
    ),
    ContributionContract(
        ContributionKind.CONVERTER,
        _declared_portability(ContributionKind.CONVERTER),
        "Content and media types cross the transport as values.",
    ),
    ContributionContract(
        ContributionKind.PROJECT_PANEL,
        _declared_portability(ContributionKind.PROJECT_PANEL),
        "Core renders a bounded declarative UI document and events.",
    ),
    ContributionContract(
        ContributionKind.SETTINGS_PANEL,
        _declared_portability(ContributionKind.SETTINGS_PANEL),
        "Core renders a bounded declarative settings document and events.",
    ),
    ContributionContract(
        ContributionKind.INDEX_CARD_STYLE,
        _declared_portability(ContributionKind.INDEX_CARD_STYLE),
        "The current contract returns a live Qt painter/style object.",
    ),
    ContributionContract(
        ContributionKind.EDITOR_WORKSPACE,
        _declared_portability(ContributionKind.EDITOR_WORKSPACE),
        "The current contract returns a QWidget and consumes Qt signals.",
    ),
    ContributionContract(
        ContributionKind.PAGE_TYPE,
        _declared_portability(ContributionKind.PAGE_TYPE),
        "Detection, parsing, and rendering can be bounded value calls.",
    ),
    ContributionContract(
        ContributionKind.PRESENTATION_MODE,
        _declared_portability(ContributionKind.PRESENTATION_MODE),
        "The current realization factory returns a live QWidget.",
    ),
    ContributionContract(
        ContributionKind.PAGE_RENDERER,
        _declared_portability(ContributionKind.PAGE_RENDERER),
        "A page model and rendered content cross as values.",
    ),
    ContributionContract(
        ContributionKind.MARKUP,
        _declared_portability(ContributionKind.MARKUP),
        "Plugins return revisioned semantic spans for bounded source ranges.",
    ),
    ContributionContract(
        ContributionKind.NATIVE_MARKUP,
        _declared_portability(ContributionKind.NATIVE_MARKUP),
        "This explicitly local contract exposes Qt highlighters and keys.",
    ),
    ContributionContract(
        ContributionKind.TRANSFORM,
        _declared_portability(ContributionKind.TRANSFORM),
        "Content-in/content-out middleware is transport-neutral.",
    ),
    ContributionContract(
        ContributionKind.CONVERSION_AUGMENTATION,
        _declared_portability(ContributionKind.CONVERSION_AUGMENTATION),
        "The current factory returns converter-specific Python objects.",
    ),
    ContributionContract(
        ContributionKind.COMMAND,
        _declared_portability(ContributionKind.COMMAND),
        "Core owns the action and invokes a bounded value operation.",
    ),
)


def contribution_contract(kind):
    """Return the declared contract for one contribution kind."""
    kind = ContributionKind(kind)
    return next(
        contract
        for contract in CONTRIBUTION_CONTRACTS
        if contract.kind is kind
    )
