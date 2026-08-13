"""Language- and transport-neutral facts about the draft Plugin API.

This module contains no plugin implementation objects and must remain safe to
load without Qt.  It is the small piece both an in-process driver and an RPC
driver can use to negotiate what the host actually supports.

API 1 is not stable yet.  The integer names the contract being designed; it
does not promise compatibility with earlier development snapshots that also
used the number 1.
"""

from dataclasses import dataclass
from enum import Enum


PLUGIN_API_VERSION = 1
PLUGIN_API_STABILITY = "draft"
PLUGIN_PROTOCOL_VERSION = 1


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
    PAGE_RENDERER = "page_renderer"
    MARKUP = "markup"
    TRANSFORM = "transform"
    CONVERSION_AUGMENTATION = "conversion_augmentation"
    COMMAND = "command"


@dataclass(frozen=True)
class ContributionContract:
    kind: ContributionKind
    portability: ContractPortability
    reason: str


#: The inventory is code because runtime negotiation and the plugin manager
#: must eventually read the same answer as the developer documentation.
CONTRIBUTION_CONTRACTS = (
    ContributionContract(
        ContributionKind.EXPORTER,
        ContractPortability.PORTABLE,
        "Bounded request and content response.",
    ),
    ContributionContract(
        ContributionKind.IMPORTER,
        ContractPortability.PORTABLE,
        "Bounded source and declarative import tree.",
    ),
    ContributionContract(
        ContributionKind.CONVERTER,
        ContractPortability.PORTABLE,
        "Content and media types cross the transport as values.",
    ),
    ContributionContract(
        ContributionKind.PROJECT_PANEL,
        ContractPortability.PORTABLE,
        "Core renders a bounded declarative UI document and events.",
    ),
    ContributionContract(
        ContributionKind.SETTINGS_PANEL,
        ContractPortability.PORTABLE,
        "Core renders a bounded declarative settings document and events.",
    ),
    ContributionContract(
        ContributionKind.INDEX_CARD_STYLE,
        ContractPortability.NATIVE,
        "The current contract returns a live Qt painter/style object.",
    ),
    ContributionContract(
        ContributionKind.EDITOR_WORKSPACE,
        ContractPortability.NATIVE,
        "The current contract returns a QWidget and consumes Qt signals.",
    ),
    ContributionContract(
        ContributionKind.PAGE_TYPE,
        ContractPortability.PORTABLE,
        "Detection, parsing, and rendering can be bounded value calls.",
    ),
    ContributionContract(
        ContributionKind.PAGE_RENDERER,
        ContractPortability.PORTABLE,
        "A page model and rendered content cross as values.",
    ),
    ContributionContract(
        ContributionKind.MARKUP,
        ContractPortability.NATIVE,
        "The current contract exposes Qt highlighters and key behaviour.",
    ),
    ContributionContract(
        ContributionKind.TRANSFORM,
        ContractPortability.PORTABLE,
        "Content-in/content-out middleware is transport-neutral.",
    ),
    ContributionContract(
        ContributionKind.CONVERSION_AUGMENTATION,
        ContractPortability.NATIVE,
        "The current factory returns converter-specific Python objects.",
    ),
    ContributionContract(
        ContributionKind.COMMAND,
        ContractPortability.PORTABLE,
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
