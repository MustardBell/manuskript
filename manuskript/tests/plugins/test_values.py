import json
import math

import pytest

from manuskript.plugins import (
    ApiValueCodec,
    ApiValueLimits,
    ContentEncoding,
    ContentEnvelope,
    ErrorEnvelope,
    OptionField,
    OptionKind,
    OutlineSnapshot,
    PluginValueError,
    ProjectSnapshot,
    api_value_codec,
)


def json_round_trip(value):
    codec = api_value_codec()
    wire = codec.encode(value)
    return codec.decode(json.loads(json.dumps(wire)))


def test_nested_snapshots_round_trip_through_plain_json():
    snapshot = ProjectSnapshot(
        project_file="Крила.msk",
        metadata={"language": "uk", "flags": ("чернетка", True)},
        outline=OutlineSnapshot(
            id="root",
            title="Розділ 🪶",
            kind="folder",
            text="",
            metadata={"order": 1},
            children=(
                OutlineSnapshot(
                    id="scene-1",
                    title="Сцена",
                    kind="md",
                    text="Миша — миші.",
                ),
            ),
        ),
    )

    assert json_round_trip(snapshot) == snapshot


def test_options_preserve_enums_tuples_and_json_defaults():
    option = OptionField(
        key="voice",
        label="Voice",
        kind=OptionKind.CHOICE,
        default={"person": 3},
        choices=(("First", "first"), ("Third", "third")),
    )

    assert json_round_trip(option) == option


def test_text_and_binary_content_have_one_explicit_envelope():
    text = ContentEnvelope.from_content("hello", "text/plain")
    binary = ContentEnvelope.from_content(b"\x00\xff", "application/data")

    assert text.encoding is ContentEncoding.UTF8
    assert json_round_trip(text).unpack() == "hello"
    assert binary.encoding is ContentEncoding.BASE64
    assert json_round_trip(binary).unpack() == b"\x00\xff"


def test_error_data_is_a_value_instead_of_an_exception_type():
    error = ErrorEnvelope(
        "project.conflict",
        "The document changed.",
        {"document_id": "scene-1", "expected": 4, "actual": 5},
    )

    assert json_round_trip(error) == error


def test_record_schema_names_and_fields_are_stable_data():
    schemas = {
        schema.name: schema
        for schema in api_value_codec().record_schemas
    }

    assert schemas["entity_snapshot"].version == 1
    assert schemas["entity_snapshot"].fields == (
        "id", "type", "title", "path", "aliases", "metadata"
    )
    assert schemas["content"].fields == (
        "content", "media_type", "encoding"
    )


def test_schema_document_describes_types_without_python_objects():
    schema = api_value_codec().schema_document
    entity_fields = {
        field["name"]: field
        for field in schema["records"]["entity_snapshot"]["fields"]
    }

    assert schema["api_version"] == 1
    assert schema["record_version"] == 1
    assert entity_fields["aliases"]["type"] == {"sequence": "string"}
    assert entity_fields["metadata"]["type"] == {"map": "value"}
    assert schema["enums"]["content_encoding"] == ["utf-8", "base64"]
    json.dumps(schema)


@pytest.mark.parametrize("value", [b"raw", object(), lambda: None])
def test_python_only_objects_are_not_accidental_wire_types(value):
    with pytest.raises(PluginValueError, match="portable|Raw bytes"):
        api_value_codec().encode(value)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_are_rejected_in_both_directions(value):
    with pytest.raises(PluginValueError, match="finite"):
        api_value_codec().encode(value)
    with pytest.raises(PluginValueError, match="finite"):
        api_value_codec().decode(value)


def test_maps_require_string_keys_and_are_encoded_deterministically():
    codec = api_value_codec()

    with pytest.raises(PluginValueError, match="string keys"):
        codec.encode({1: "one"})

    wire = codec.encode({"z": 1, "a": 2})
    assert list(wire["items"]) == ["a", "z"]


def test_unknown_or_changed_records_are_rejected():
    codec = api_value_codec()
    wire = codec.encode(ContentEnvelope("hello", "text/plain"))

    unknown = dict(wire, name="future_record")
    with pytest.raises(PluginValueError, match="Unknown.*record"):
        codec.decode(unknown)

    future = dict(wire, version=2)
    with pytest.raises(PluginValueError, match="Unsupported version"):
        codec.decode(future)

    extra = dict(wire)
    extra["fields"] = dict(wire["fields"], surprise=True)
    with pytest.raises(PluginValueError, match="Unknown fields"):
        codec.decode(extra)


def test_record_defaults_may_be_omitted_but_required_fields_may_not():
    codec = api_value_codec()
    wire = codec.encode(ContentEnvelope("hello"))
    minimal = dict(wire)
    minimal["fields"] = {"content": "hello"}

    assert codec.decode(minimal) == ContentEnvelope("hello")

    minimal["fields"] = {}
    with pytest.raises(PluginValueError, match="Missing fields"):
        codec.decode(minimal)


def test_structure_limits_apply_before_a_plugin_can_exhaust_the_host():
    depth_codec = ApiValueCodec(
        limits=ApiValueLimits(max_depth=2, max_items=100, max_string_bytes=100)
    )
    with pytest.raises(PluginValueError, match="nesting depth"):
        depth_codec.encode([[["too deep"]]])

    item_codec = ApiValueCodec(
        limits=ApiValueLimits(max_depth=10, max_items=2, max_string_bytes=100)
    )
    with pytest.raises(PluginValueError, match="item count"):
        item_codec.decode([1, 2, 3])

    string_codec = ApiValueCodec(
        limits=ApiValueLimits(max_depth=10, max_items=10, max_string_bytes=3)
    )
    with pytest.raises(PluginValueError, match="string.*size"):
        string_codec.encode("four")


def test_wire_objects_must_use_the_declared_tagged_shape():
    with pytest.raises(PluginValueError, match="tagged"):
        api_value_codec().decode({"ordinary": "object"})

    wire = api_value_codec().encode((1, 2))
    wire["extra"] = True
    with pytest.raises(PluginValueError, match="exactly"):
        api_value_codec().decode(wire)
