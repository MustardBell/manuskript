"""Core publishes a curated surface; plugins ask for what they need.

A requirement core cannot meet must stop the plugin before any of its code
runs, and say which capability was missing. A plugin must not be able to
reach a service it did not declare.
"""

import json

import pytest

from manuskript.plugins.capabilities import (
    CAPABILITY_EDITOR_CONTROL,
    CAPABILITY_MARKUP_BBCODE,
    CAPABILITY_OUTLINE_READ,
    CAPABILITY_OUTLINE_WRITE,
    capability_catalogue,
    grant,
)
from manuskript.plugins.errors import PluginManifestError, PluginScopeError
from manuskript.plugins.manifest import PluginManifest
from manuskript.plugins.registry import PluginRegistry
from manuskript.plugins.runtime import PluginRuntime, PluginStatus
from manuskript.services.plugin_preferences import (
    InMemoryPluginPreferences,
)


def write_plugin(root, plugin_id="needs.capability", requires=(), source=""):
    directory = root / plugin_id
    directory.mkdir()
    manifest = {
        "id": plugin_id,
        "name": "Needs a capability",
        "version": "1.0",
        "api_version": 1,
        "entry_point": "plugin:register",
    }
    if requires:
        manifest["requires"] = list(requires)
    (directory / "plugin.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (directory / "plugin.py").write_text(source, encoding="utf-8")
    return directory


EXPLODES_IF_IMPORTED = (
    "raise AssertionError('plugin code must not run when unsatisfied')\n"
)

CAPTURES_CAPABILITY = """
received = {}


def register(api):
    received["converter"] = api.capability("markup.bbcode")
"""

REACHES_TOO_FAR = """
def register(api):
    api.capability("markup.bbcode")
"""


def runtime_for(root, plugin_id):
    runtime = PluginRuntime(
        [root], InMemoryPluginPreferences([plugin_id])
    )
    runtime.discover()
    return runtime


# ------------------------------------------------------------- the catalogue

def test_the_catalogue_describes_what_it_offers():
    catalogue = capability_catalogue()

    assert CAPABILITY_MARKUP_BBCODE in catalogue
    entry = catalogue[CAPABILITY_MARKUP_BBCODE]
    assert entry.name == CAPABILITY_MARKUP_BBCODE
    assert entry.summary
    assert callable(entry.factory)


def test_a_workspace_can_declare_what_it_touches():
    """The three exist in the catalogue, or a plugin declaring one would be
    refused at load for asking for something core does not have.
    """
    catalogue = capability_catalogue()

    for name in (
        CAPABILITY_OUTLINE_READ,
        CAPABILITY_OUTLINE_WRITE,
        CAPABILITY_EDITOR_CONTROL,
    ):
        assert name in catalogue, name
        assert catalogue[name].summary
        # Handed over by the workspace host, which is the only thing that
        # can scope them to a window and a project.
        assert catalogue[name].deferred

    granted, missing = grant([CAPABILITY_OUTLINE_WRITE])

    assert missing == ()
    assert granted == {}


def test_the_runtime_answers_what_a_plugin_declared(tmp_path):
    """One place answers it: two hosts hand services over, and each used to
    read the manifest itself.
    """
    write_plugin(tmp_path, requires=[CAPABILITY_MARKUP_BBCODE])
    runtime = runtime_for(tmp_path, "needs.capability")

    assert runtime.declares("needs.capability", CAPABILITY_MARKUP_BBCODE)
    assert not runtime.declares(
        "needs.capability", CAPABILITY_OUTLINE_WRITE,
    )
    # A plugin core has no record of has declared nothing.
    assert not runtime.declares("never.heard.of.it", CAPABILITY_MARKUP_BBCODE)


def test_granting_reports_what_is_missing_and_builds_nothing():
    granted, missing = grant(["markup.bbcode", "does.not.exist"])

    assert missing == ("does.not.exist",)
    # Refusal is total: no half-granted set for the caller to misuse.
    assert granted == {}


def test_granting_a_known_name_yields_a_usable_object():
    granted, missing = grant([CAPABILITY_MARKUP_BBCODE])

    assert missing == ()
    assert granted[CAPABILITY_MARKUP_BBCODE].convert("**x**") == "[b]x[/b]"


# ---------------------------------------------------------------- manifests

def test_requires_defaults_to_nothing(tmp_path):
    directory = write_plugin(tmp_path)

    manifest = PluginManifest.load(directory / "plugin.json")

    assert manifest.requires == ()


def test_requires_is_read_and_deduplicated(tmp_path):
    directory = write_plugin(
        tmp_path, requires=["markup.bbcode", "markup.bbcode"]
    )

    manifest = PluginManifest.load(directory / "plugin.json")

    assert manifest.requires == ("markup.bbcode",)


@pytest.mark.parametrize("declared", ["markup.bbcode", 5, [1], [""], {}])
def test_a_malformed_requires_is_rejected_at_discovery(tmp_path, declared):
    directory = tmp_path / "bad"
    directory.mkdir()
    (directory / "plugin.json").write_text(json.dumps({
        "id": "bad.plugin",
        "name": "Bad",
        "version": "1.0",
        "api_version": 1,
        "entry_point": "plugin:register",
        "requires": declared,
    }), encoding="utf-8")

    with pytest.raises(PluginManifestError) as failure:
        PluginManifest.load(directory / "plugin.json")

    assert "requires" in str(failure.value)


# -------------------------------------------------------------- negotiation

def test_an_unmet_requirement_never_runs_the_plugin(tmp_path):
    """The refusal has to happen before the entry point is imported."""
    write_plugin(
        tmp_path,
        requires=["nothing.provides.this"],
        source=EXPLODES_IF_IMPORTED,
    )
    runtime = runtime_for(tmp_path, "needs.capability")

    record = runtime.load("needs.capability")

    assert record.status is PluginStatus.UNSATISFIED
    assert "nothing.provides.this" in record.error
    # If the module had been imported, the assertion inside it would have
    # turned this into a FAILED record instead.
    assert "AssertionError" not in record.error
    assert runtime.registry.plugin_records("needs.capability") == ()


def test_a_met_requirement_loads_and_hands_over_the_service(tmp_path):
    write_plugin(
        tmp_path,
        requires=[CAPABILITY_MARKUP_BBCODE],
        source=CAPTURES_CAPABILITY,
    )
    runtime = runtime_for(tmp_path, "needs.capability")

    record = runtime.load("needs.capability")

    assert record.status is PluginStatus.LOADED
    assert record.error == ""


def test_a_plugin_cannot_reach_an_undeclared_capability(tmp_path):
    write_plugin(tmp_path, requires=(), source=REACHES_TOO_FAR)
    runtime = runtime_for(tmp_path, "needs.capability")

    record = runtime.load("needs.capability")

    # Declaring nothing means receiving nothing, even for a name core has.
    assert record.status is PluginStatus.FAILED
    assert "did not declare" in record.error


def test_the_registrar_refuses_undeclared_names_directly():
    registrar = PluginRegistry().registrar(
        "some.plugin", capabilities={"a.granted": object()}
    )

    assert registrar.capability("a.granted") is not None
    with pytest.raises(PluginScopeError) as failure:
        registrar.capability("markup.bbcode")

    assert "some.plugin" in str(failure.value)
