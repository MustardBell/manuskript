"""Transport-neutral UI documents rendered and owned by Manuskript."""

import re

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional


CONTROL_ID = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")


class UiControlKind(str, Enum):
    GROUP = "group"
    TEXT = "text"
    CHECKBOX = "checkbox"
    INTEGER = "integer"
    NUMBER = "number"
    CHOICE = "choice"
    LIST = "list"
    TABLE = "table"
    TREE = "tree"
    BUTTON = "button"
    PROGRESS = "progress"
    MESSAGE = "message"


class UiEventKind(str, Enum):
    CHANGE = "change"
    ACTIVATE = "activate"
    SELECT = "select"
    REORDER = "reorder"


@dataclass(frozen=True)
class UiChoice:
    label: str
    value: Any

    def __post_init__(self):
        if not str(self.label).strip():
            raise ValueError("UI choices require a visible label.")


@dataclass(frozen=True)
class UiColumn:
    id: str
    label: str

    def __post_init__(self):
        if not CONTROL_ID.fullmatch(str(self.id)) or not str(self.label).strip():
            raise ValueError("UI columns require an ID and visible label.")


@dataclass(frozen=True)
class UiItem:
    id: str
    label: str = ""
    cells: Mapping[str, Any] = field(default_factory=dict)
    children: tuple["UiItem", ...] = ()
    enabled: bool = True

    def __post_init__(self):
        if not str(self.id):
            raise ValueError("UI items require an ID.")
        object.__setattr__(self, "cells", dict(self.cells))
        object.__setattr__(self, "children", tuple(self.children))


@dataclass(frozen=True)
class UiControl:
    id: str
    kind: UiControlKind
    label: str = ""
    description: str = ""
    error: str = ""
    accessible_name: str = ""
    value: Any = None
    choices: tuple[UiChoice, ...] = ()
    columns: tuple[UiColumn, ...] = ()
    items: tuple[UiItem, ...] = ()
    children: tuple["UiControl", ...] = ()
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    required: bool = False
    enabled: bool = True
    visible: bool = True
    reorderable: bool = False

    def __post_init__(self):
        kind = UiControlKind(self.kind)
        object.__setattr__(self, "kind", kind)
        if not CONTROL_ID.fullmatch(str(self.id)):
            raise ValueError("UI controls require a stable ID.")
        interactive = kind not in (
            UiControlKind.GROUP,
            UiControlKind.MESSAGE,
            UiControlKind.PROGRESS,
        )
        if interactive and not str(self.label).strip():
            raise ValueError(
                "Interactive UI controls require a visible label."
            )
        accessible_name = str(self.accessible_name or self.label).strip()
        if interactive and not accessible_name:
            raise ValueError(
                "Interactive UI controls require an accessible name."
            )
        object.__setattr__(self, "accessible_name", accessible_name)
        object.__setattr__(self, "choices", tuple(self.choices))
        object.__setattr__(self, "columns", tuple(self.columns))
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "children", tuple(self.children))
        if kind is UiControlKind.CHOICE and not self.choices:
            raise ValueError("Choice controls require choices.")
        if kind is UiControlKind.TABLE and not self.columns:
            raise ValueError("Table controls require columns.")
        if self.reorderable and kind not in (
            UiControlKind.LIST, UiControlKind.TREE
        ):
            raise ValueError("Only list and tree controls can be reordered.")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("UI control minimum cannot exceed maximum.")


@dataclass(frozen=True)
class UiDocument:
    id: str
    revision: int
    controls: tuple[UiControl, ...]

    def __post_init__(self):
        if not CONTROL_ID.fullmatch(str(self.id)):
            raise ValueError("UI documents require a stable ID.")
        if isinstance(self.revision, bool) or self.revision < 0:
            raise ValueError("UI document revisions are non-negative integers.")
        object.__setattr__(self, "controls", tuple(self.controls))
        identifiers = []

        def collect(controls):
            for control in controls:
                identifiers.append(control.id)
                collect(control.children)

        collect(self.controls)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("UI control IDs must be unique within a document.")


@dataclass(frozen=True)
class UiEvent:
    session_id: str
    document_revision: int
    control_id: str
    kind: UiEventKind
    value: Any = None

    def __post_init__(self):
        object.__setattr__(self, "kind", UiEventKind(self.kind))
        if not str(self.session_id) or not CONTROL_ID.fullmatch(
            str(self.control_id)
        ):
            raise ValueError("UI events require session and control IDs.")


@dataclass(frozen=True)
class UiResponse:
    document: UiDocument
    message: str = ""
    focus: str = ""

    def __post_init__(self):
        if not isinstance(self.document, UiDocument):
            raise TypeError("UI responses require a UI document.")

