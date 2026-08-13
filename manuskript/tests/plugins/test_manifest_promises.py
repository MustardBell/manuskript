"""Declaring a format and promising something about it are separate acts.

Declaring says a name exists and this plugin has an interest in it. That is
free and carries no obligation. Promising says what the plugin does with the
format, and it is the promise that has to be backed: by a declaration in the
same manifest, and by contributions that stay inside it.
"""

import json

import pytest

from manuskript.media_types import (
    BBCODE,
    CONSUMES,
    MARKDOWN,
    PRODUCES,
    TRANSFORMS,
    core_registry,
)
from manuskript.plugins.errors import PluginManifestError
from manuskript.plugins.manifest import PluginManifest
from manuskript.plugins.runtime import PluginRuntime, PluginStatus
from manuskript.services.plugin_preferences import (
    InMemoryPluginPreferences,
)
from manuskript.tests.plugins.test_runtime import create_plugin


FB2 = "application/x-fictionbook+xml"


def manifest(tmp_path, **extra):
    root = tmp_path / "plugin"
    root.mkdir()
    declared = {
        "id": "vendor.thing",
        "name": "Thing",
        "version": "1.0",
        "api_version": 1,
        "entry_point": "plugin:register",
        "project_formats": {"minimum": 0, "tested_through": 2},
    }
    declared.update(extra)
    path = root / "plugin.json"
    path.write_text(json.dumps(declared), encoding="utf-8")
    return PluginManifest.load(path)


def test_project_format_contract_distinguishes_explicit_tentative_and_closed(
    tmp_path,
):
    loaded = manifest(
        tmp_path,
        project_formats={"minimum": 0, "tested_through": 2},
    )

    assert loaded.supports_project_format(0)
    assert loaded.project_formats.explicitly_supports(2)
    assert loaded.project_formats.is_tentative(3)
    assert loaded.project_formats.label == (
        "0–2; later formats tentative"
    )


def test_project_format_maximum_is_a_hard_stop(tmp_path):
    loaded = manifest(
        tmp_path,
        project_formats={
            "minimum": 0, "tested_through": 1, "maximum": 1,
        },
    )

    assert loaded.supports_project_format(1)
    assert not loaded.supports_project_format(2)
    assert loaded.project_formats.label == "0–1 only"


@pytest.mark.parametrize("declaration", [
    None,
    [],
    {},
    {"minimum": 0},
    {"minimum": 1, "tested_through": 0},
    {"minimum": 0, "tested_through": 2, "maximum": 1},
    {"minimum": 0, "tested_through": 1, "max": 1},
])
def test_invalid_project_format_contract_is_refused(tmp_path, declaration):
    with pytest.raises(PluginManifestError):
        manifest(tmp_path, project_formats=declaration)


def test_undeclared_project_formats_remain_tentative_for_api_1(tmp_path):
    root = tmp_path / "legacy-plugin"
    root.mkdir()
    path = root / "plugin.json"
    path.write_text(json.dumps({
        "id": "vendor.legacy",
        "name": "Legacy plugin",
        "version": "1.0",
        "api_version": 1,
        "entry_point": "plugin:register",
    }), encoding="utf-8")

    loaded = PluginManifest.load(path)

    assert loaded.supports_project_format(2)
    assert loaded.project_formats.is_tentative(2)
    assert loaded.project_formats.label == (
        "not declared; all formats tentative"
    )


# ------------------------------------------------------------- declaring

def test_a_bare_string_re_declares_a_format_somebody_else_names(tmp_path):
    loaded = manifest(tmp_path, media_types=[BBCODE, MARKDOWN])

    assert loaded.declared_media_type_ids == (BBCODE, MARKDOWN)
    # No attributes needed: SAMPLE did not invent BBCode, it just cares.
    assert all(not mt.named for mt in loaded.media_types)


def test_an_object_introduces_a_format(tmp_path):
    loaded = manifest(tmp_path, media_types=[
        {"id": FB2, "label": "FictionBook 2", "textual": False},
    ])

    introduced = loaded.media_types[0]
    assert introduced.id == FB2
    assert introduced.label == "FictionBook 2"
    assert introduced.textual is False


def test_the_two_forms_mix_in_one_list(tmp_path):
    loaded = manifest(tmp_path, media_types=[
        MARKDOWN,
        {"id": FB2, "label": "FictionBook 2"},
    ])

    assert loaded.declared_media_type_ids == (MARKDOWN, FB2)


def test_declaring_the_same_format_twice_is_not_an_error(tmp_path):
    loaded = manifest(tmp_path, media_types=[MARKDOWN, MARKDOWN])

    assert loaded.declared_media_type_ids == (MARKDOWN,)


def test_declaring_promises_nothing(tmp_path):
    loaded = manifest(tmp_path, media_types=[BBCODE])

    assert loaded.promised_media_types == ()
    assert loaded.produces == ()
    assert loaded.consumes == ()
    assert loaded.transforms == ()


@pytest.mark.parametrize("value", [
    "text/markdown",           # a bare string, not a list
    [None],
    [{"label": "no identifier"}],
    [{"id": "   "}],
    [42],
])
def test_a_malformed_declaration_is_refused(tmp_path, value):
    with pytest.raises(PluginManifestError):
        manifest(tmp_path, media_types=value)


def test_a_format_based_on_itself_is_refused(tmp_path):
    with pytest.raises(PluginManifestError):
        manifest(tmp_path, media_types=[
            {"id": MARKDOWN, "label": "Markdown", "base": MARKDOWN},
        ])


# -------------------------------------------------------------- promising

def test_the_three_promises_are_read_separately(tmp_path):
    loaded = manifest(
        tmp_path,
        media_types=[MARKDOWN, BBCODE],
        produces=[MARKDOWN],
        consumes=[BBCODE],
        transforms=[],
    )

    assert loaded.produces == (MARKDOWN,)
    assert loaded.consumes == (BBCODE,)
    assert loaded.transforms == ()
    assert loaded.promised_media_types == (MARKDOWN, BBCODE)


@pytest.mark.parametrize("key", ["produces", "consumes", "transforms"])
def test_promising_an_undeclared_format_refuses_the_manifest(tmp_path, key):
    with pytest.raises(PluginManifestError) as error:
        manifest(tmp_path, media_types=[MARKDOWN], **{key: [BBCODE]})

    # Names the format and what the plugin claimed to do with it.
    assert BBCODE in str(error.value)
    assert "media_types" in str(error.value)


@pytest.mark.parametrize("key", ["produces", "consumes", "transforms"])
def test_a_malformed_promise_is_refused(tmp_path, key):
    with pytest.raises(PluginManifestError):
        manifest(tmp_path, media_types=[MARKDOWN], **{key: MARKDOWN})


# ------------------------------------------- refusal precedes the import

EXPLODES_ON_IMPORT = "raise RuntimeError('the plugin was imported')\n"


def runtime(tmp_path, plugin_id="vendor.thing", **extra):
    create_plugin(
        tmp_path,
        plugin_id=plugin_id,
        source=extra.pop("source", EXPLODES_ON_IMPORT),
        manifest=extra,
    )
    started = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences([plugin_id]),
        media_types=core_registry(),
    )
    started.discover()
    started.load_enabled()
    return started


def test_a_promise_about_an_undeclared_format_never_imports_the_plugin(
        tmp_path):
    # The module raises on import, so reaching it at all fails loudly.
    started = runtime(
        tmp_path,
        media_types=[MARKDOWN],
        produces=[BBCODE],
    )

    assert started.records == {}
    assert len(started.discovery_issues) == 1
    assert BBCODE in started.discovery_issues[0].error


def test_a_declaration_with_no_promise_loads_fine(tmp_path):
    started = runtime(
        tmp_path,
        media_types=[BBCODE],
        source="def register(api):\n    return None\n",
    )

    record = started.records["vendor.thing"]
    assert record.status is PluginStatus.LOADED


# ------------------------------------ contributions stay inside the promise

RENDERER_SOURCE = """
from manuskript.plugins import (
    ExtensionDescriptor, PageRendererContribution, PageTypeContribution)


def register(api):
    api.register_page_type(PageTypeContribution(
        descriptor=ExtensionDescriptor(id='vendor.page', name='Page'),
        property_label='Page',
        parser_factory=object,
    ))
    api.register_page_renderer(PageRendererContribution(
        descriptor=ExtensionDescriptor(id='vendor.r', name='Renderer'),
        page_type_id='vendor.page',
        renderer_factory=object,
        target_formats=('{target}',),
    ))
"""


def test_a_contribution_may_name_a_promised_format(tmp_path):
    started = runtime(
        tmp_path,
        media_types=[BBCODE],
        consumes=[BBCODE],
        source=RENDERER_SOURCE.format(target=BBCODE),
    )

    assert started.records["vendor.thing"].status is PluginStatus.LOADED
    assert len(started.registry.page_renderers) == 1


def test_a_contribution_naming_an_unpromised_format_installs_nothing(
        tmp_path):
    started = runtime(
        tmp_path,
        media_types=[BBCODE, MARKDOWN],
        consumes=[BBCODE],
        source=RENDERER_SOURCE.format(target=MARKDOWN),
    )

    record = started.records["vendor.thing"]
    assert record.status is PluginStatus.FAILED
    assert MARKDOWN in record.error
    # Registration is atomic: the page type does not survive either.
    assert started.registry.page_renderers == ()
    assert started.registry.page_types == ()


# ------------------------------------------- the vocabulary reaches core

def test_a_declared_format_is_global_and_attributed(tmp_path):
    started = runtime(
        tmp_path,
        media_types=[{"id": FB2, "label": "FictionBook 2", "textual": False}],
        source="def register(api):\n    return None\n",
    )

    registry = started.mediaTypes
    assert registry.is_known(FB2)
    assert registry.label(FB2) == "FictionBook 2"
    assert "vendor.thing" in registry.declared_by(FB2)


def test_promises_are_recorded_against_the_format(tmp_path):
    started = runtime(
        tmp_path,
        media_types=[MARKDOWN, BBCODE],
        produces=[MARKDOWN],
        consumes=[BBCODE],
        source="def register(api):\n    return None\n",
    )

    registry = started.mediaTypes
    assert registry.promises(MARKDOWN)[PRODUCES] == ("vendor.thing",)
    assert registry.promises(BBCODE)[CONSUMES] == ("vendor.thing",)
    assert registry.promises(BBCODE)[TRANSFORMS] == ()
    # Core declared both first, so both are on record for each.
    assert registry.declared_by(BBCODE) == ("core", "vendor.thing")


def test_a_disabled_plugins_vocabulary_is_still_declared(tmp_path):
    create_plugin(
        tmp_path,
        plugin_id="vendor.thing",
        source=EXPLODES_ON_IMPORT,
        manifest={"media_types": [{"id": FB2, "label": "FictionBook 2"}]},
    )
    started = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences([]),
        media_types=core_registry(),
    )
    started.discover()

    # Never loaded, never imported, and the format exists anyway: load
    # order must not decide whether a name is in the vocabulary.
    assert started.records["vendor.thing"].status is PluginStatus.DISABLED
    assert started.mediaTypes.is_known(FB2)


def test_two_plugins_declaring_one_format_agree(tmp_path):
    for index in (0, 1):
        create_plugin(
            tmp_path,
            plugin_id="vendor.{}".format(index),
            source="def register(api):\n    return None\n",
            manifest={"media_types": [
                {"id": FB2, "label": "FictionBook {}".format(index)},
            ]},
        )
    started = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences([]),
        media_types=core_registry(),
    )
    started.discover()

    registry = started.mediaTypes
    assert registry.declared_by(FB2) == ("vendor.0", "vendor.1")
    # Not a collision, unlike a duplicate contribution ID. The first namer
    # supplies the attributes and the second is still on record.
    assert registry.label(FB2) == "FictionBook 0"
