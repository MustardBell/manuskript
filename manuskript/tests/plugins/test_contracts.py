"""The stable API 1 boundary must remain explicit and transport-neutral."""

import ast
from dataclasses import fields
from pathlib import Path

from manuskript.plugins.capabilities import CAPABILITIES
from manuskript.plugins.contracts import (
    CONTRIBUTION_CONTRACTS,
    PLUGIN_API_STABILITY,
    PLUGIN_API_VERSION,
    PLUGIN_PROTOCOL_VERSION,
    ContractPortability,
    ContributionKind,
)
from manuskript.plugins.registry import (
    CONTRIBUTION_HANDLER_FIELDS,
    CONTRIBUTION_TYPES,
)


def test_api_and_protocol_are_independent_integer_contracts():
    assert PLUGIN_API_VERSION == 1
    assert PLUGIN_PROTOCOL_VERSION == 1
    assert PLUGIN_API_STABILITY == "stable"


def test_every_registered_contribution_has_one_portability_decision():
    inventoried = [contract.kind for contract in CONTRIBUTION_CONTRACTS]

    assert len(inventoried) == len(set(inventoried))
    assert set(inventoried) == set(ContributionKind)
    assert set(inventoried) == set(CONTRIBUTION_TYPES)


def test_every_contribution_kind_separates_its_executable_handlers():
    assert set(CONTRIBUTION_HANDLER_FIELDS) == set(CONTRIBUTION_TYPES)
    for kind, handler_names in CONTRIBUTION_HANDLER_FIELDS.items():
        declared_names = {
            field.name
            for field in fields(CONTRIBUTION_TYPES[kind])
        }
        assert set(handler_names) <= declared_names


def test_every_capability_has_an_explicit_portability_value():
    assert CAPABILITIES
    assert all(
        isinstance(capability.portability, ContractPortability)
        for capability in CAPABILITIES
    )


def test_portable_contract_modules_do_not_import_qt():
    plugin_root = Path(__file__).parents[2] / "plugins"

    for name in ("contracts.py", "runtimes.py", "values.py", "api.py"):
        tree = ast.parse(
            (plugin_root / name).read_text(encoding="utf-8"),
            filename=name,
        )
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        assert not any(
            module.startswith(("PyQt", "PySide"))
            for module in imports
        ), name


def test_the_api_offers_no_way_to_ask_for_a_navigator_row():
    """Removed rather than reserved for a contribution that may never come.

    It was the type ``ProjectPanelContribution.navigator`` took, and that
    field is gone: a project panel is a tool panel, and a navigator row
    says the writer goes there, which is a workspace surface. Nothing can
    consume this any more.

    The orphan was removed before the API 1 stability boundary. Keeping an
    unused wire record would have made an accidental development shape -- a
    label, an icon and an integer order -- into the shape a real surface
    contribution had to live with, while plugin ordering may want anchors or
    categories rather than unconstrained integers.
    """

    import manuskript.plugins as api
    from manuskript.plugins.specification import api_schema_document

    assert not hasattr(api, "UiNavigatorEntry")
    assert "UiNavigatorEntry" not in api.__all__
    assert "ui_navigator_entry" not in api_schema_document()["records"]
