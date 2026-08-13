import json
import os
import sys
import time

from pathlib import Path

from manuskript.plugins.api import (
    ContentSignature,
    ContributionDeclaration,
    EntitySnapshot,
    ExtensionDescriptor,
    ImportNode,
    ImportResult,
    MarkupAnalysisRequest,
    MarkupAnalysisResult,
    MarkupMode,
    PageExportDocument,
    RenderedDocument,
    TextRange,
)
from manuskript.plugins.contracts import ContributionKind
from manuskript.plugins.execution import (
    run_conversion,
    run_export,
    run_import,
    run_page_format_renderer,
    run_page_parser,
    run_page_renderer,
    run_transform,
)
from manuskript.plugins.runtime import PluginRuntime, PluginStatus
from manuskript.plugins.runtimes import current_platform
from manuskript.plugins.values import (
    ContentEnvelope,
    PortableArtifact,
    api_value_codec,
)
from manuskript.services.plugin_preferences import InMemoryPluginPreferences


PROCESS_PLUGIN = r'''
import json
import os
import sys


ROOT = os.path.dirname(__file__)
DATA = json.load(open(os.path.join(ROOT, "fixture_data.json"), encoding="utf-8"))


def read_message():
    header = bytearray()
    while not header.endswith(b"\r\n\r\n"):
        byte = sys.stdin.buffer.read(1)
        if not byte:
            return None
        header.extend(byte)
    length = None
    for line in bytes(header[:-4]).decode("ascii").split("\r\n"):
        name, value = line.split(":", 1)
        if name.lower() == "content-length":
            length = int(value.strip())
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def send(message):
    payload = json.dumps(
        message, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    sys.stdout.buffer.write(
        ("Content-Length: %d\r\n\r\n" % len(payload)).encode("ascii")
        + payload
    )
    sys.stdout.buffer.flush()


while True:
    message = read_message()
    if message is None:
        break
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        json.dump(
            message["params"],
            open(os.path.join(ROOT, "initialize_seen.json"), "w", encoding="utf-8"),
            ensure_ascii=False,
        )
        send({"jsonrpc": "2.0", "id": request_id, "result": {
            "plugin_id": DATA["plugin_id"],
            "api_version": 1,
            "protocol_version": 1,
            "contributions": DATA["contributions"],
        }})
    elif method == "initialized":
        open(os.path.join(ROOT, "initialized"), "w").close()
    elif method == "contribution/call":
        call = message["params"]
        operation = call["operation"]
        contribution_id = call["contribution_id"]
        if (
            operation == "detect"
            and call["arguments"]["items"][0] == "CALL CAPABILITY"
        ):
            send({"jsonrpc": "2.0", "id": "capability-1",
                  "method": "capability/call", "params": {
                "capability": "entities.read",
                "operation": "find",
                "arguments": {"$kind": "tuple",
                              "items": ["character:mara"]},
                "keyword_arguments": {"$kind": "map", "items": {}},
                "project_generation": 0,
                "expected_revision": None,
            }})
            host_response = read_message()
            result = (
                host_response["result"]["value"]["fields"]["title"]
                == "Mara"
            )
        elif operation == "analyze":
            request = call["arguments"]["items"][0]
            fields = request["fields"]
            result = {
                "$kind": "record",
                "name": "markup_analysis_result",
                "version": 1,
                "fields": {
                    "analysis_id": fields["analysis_id"],
                    "document_id": fields["document_id"],
                    "document_revision": fields["document_revision"],
                    "window": fields["window"],
                    "spans": {"$kind": "tuple", "items": []},
                },
            }
        elif operation == "transform":
            arguments = call["arguments"]["items"]
            result = arguments[0].upper()
        elif operation == "detect":
            result = "REMOTE" in call["arguments"]["items"][0]
        elif operation == "parse":
            result = DATA["results"]["parse"]
        elif operation == "render" and contribution_id.endswith("page-type"):
            result = DATA["results"]["rendered_document"]
        elif operation == "render":
            result = DATA["results"]["page_export"]
        else:
            result = DATA["results"][operation]
        send({"jsonrpc": "2.0", "id": request_id, "result": result})
    elif method == "contribution/notify":
        call = message["params"]
        if call["operation"] == "cancel_analysis":
            json.dump(
                call,
                open(os.path.join(ROOT, "cancel_seen.json"), "w", encoding="utf-8"),
                ensure_ascii=False,
            )
    elif method == "deactivate":
        send({"jsonrpc": "2.0", "id": request_id, "result": None})
    elif method == "shutdown":
        send({"jsonrpc": "2.0", "id": request_id, "result": None})
    elif method == "exit":
        break
'''


def declaration(kind, name, configuration):
    return ContributionDeclaration(
        kind,
        ExtensionDescriptor("example.remote." + name, name),
        configuration,
    )


def portable_contributions():
    return (
        (declaration(
            ContributionKind.EXPORTER,
            "exporter",
            {"options": (), "output_format": "text/plain"},
        ), ("export",)),
        (declaration(
            ContributionKind.IMPORTER,
            "importer",
            {
                "file_filter": "Text (*.txt)",
                "source_kind": "file",
                "options": (),
            },
        ), ("import_document",)),
        (declaration(
            ContributionKind.CONVERTER,
            "converter",
            {
                "source_formats": ("text/plain",),
                "target_formats": ("text/html",),
                "options": (),
            },
        ), ("convert",)),
        (declaration(
            ContributionKind.TRANSFORM,
            "transform",
            {
                "media_type": "text/plain",
                "options": (),
                "priority": 0,
            },
        ), ("transform",)),
        (declaration(
            ContributionKind.PAGE_TYPE,
            "page-type",
            {
                "property_label": "Remote page",
                "signature": ContentSignature(starts_with="REMOTE"),
                "item_kinds": ("md",),
            },
        ), ("detect", "parse", "render")),
        (declaration(
            ContributionKind.PAGE_RENDERER,
            "page-renderer",
            {
                "page_type_id": "example.remote.page-type",
                "target_formats": ("text/html",),
                "options": (),
                "priority": 0,
            },
        ), ("render",)),
    )


def create_process_plugin(tmp_path, contributions=None, requires=()):
    codec = api_value_codec()
    plugin_root = tmp_path / "example.remote"
    plugin_root.mkdir()
    script = plugin_root / "plugin.py"
    script.write_text(PROCESS_PLUGIN, encoding="utf-8")
    platform = current_platform()
    python = Path(sys.executable).name
    manifest = {
        "id": "example.remote",
        "name": "Remote",
        "version": "1.0",
        "api_version": 1,
        "runtime": {
            "kind": "process",
            "protocol_version": 1,
            "commands": {platform: [python, "plugin.py"]},
        },
        "project_formats": {"minimum": 0, "tested_through": 2},
        "requires": list(requires),
        "media_types": ["text/plain", "text/html"],
        "produces": ["text/plain", "text/html"],
    }
    (plugin_root / "plugin.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    contributions = contributions or portable_contributions()
    data = {
        "plugin_id": "example.remote",
        "contributions": [
            {
                "declaration": codec.encode(item),
                "operations": list(operations),
            }
            for item, operations in contributions
        ],
        "results": {
            "export": codec.encode(PortableArtifact(
                ContentEnvelope("exported", "text/plain"),
                "story.txt",
            )),
            "import_document": codec.encode(ImportResult((
                ImportNode("Imported", text="source"),
            ),)),
            "convert": codec.encode(PortableArtifact(
                ContentEnvelope("<p>converted</p>", "text/html"),
                "story.html",
                ("converted remotely",),
            )),
            "parse": codec.encode({"parsed": True}),
            "rendered_document": codec.encode(
                RenderedDocument("<p>remote page</p>")
            ),
            "page_export": codec.encode(
                PageExportDocument("<p>page export</p>", "text/html")
            ),
            "invoke": codec.encode("Remote command completed"),
        },
    }
    (plugin_root / "fixture_data.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    return plugin_root


def load_process_plugin(tmp_path, project_capability_resolver=None, **kwargs):
    plugin_root = create_process_plugin(tmp_path, **kwargs)
    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(["example.remote"]),
        project_format=2,
        project_capability_resolver=project_capability_resolver,
    )
    runtime.discover()
    runtime.load_enabled()
    return plugin_root, runtime


def test_process_driver_negotiates_and_installs_atomically(tmp_path):
    plugin_root, runtime = load_process_plugin(tmp_path)

    record = runtime.records["example.remote"]
    assert record.status is PluginStatus.LOADED, record.error
    assert len(runtime.registry.plugin_records("example.remote")) == 6
    seen = json.loads(
        (plugin_root / "initialize_seen.json").read_text(encoding="utf-8")
    )
    assert seen["host"] == {
        "api_version": 1,
        "protocol_version": 1,
        "project_format": 2,
        "project_generation": 0,
    }
    assert seen["capabilities"] == {}
    assert seen["contribution_kinds"]["exporter"] == "portable"
    assert seen["contribution_kinds"]["project_panel"] == "portable"
    assert seen["value_schema"]["api_version"] == 1
    assert (plugin_root / "initialized").exists()

    runtime.disable("example.remote")
    assert not record.session


def test_all_first_release_computational_contributions_execute(tmp_path):
    _root, runtime = load_process_plugin(tmp_path)
    registry = runtime.registry
    try:
        exported = run_export(registry.exporters[0], {"project": True})
        imported = run_import(registry.importers[0], "source")
        converted = run_conversion(
            registry.converters[0],
            "source",
            "text/plain",
            "text/html",
        )
        transformed = run_transform(registry.transforms[0], "mixed Case")
        page_type = registry.page_types[0]
        detected = page_type.detector("REMOTE source")
        parsed = run_page_parser(page_type, "REMOTE source")
        rendered = run_page_renderer(page_type, "REMOTE source")
        page_export = run_page_format_renderer(
            registry.page_renderers[0],
            parsed,
            "text/html",
        )
    finally:
        runtime.disable("example.remote")

    assert exported.content == "exported"
    assert imported.nodes[0].title == "Imported"
    assert converted.content == "<p>converted</p>"
    assert converted.warnings == ("converted remotely",)
    assert transformed == "MIXED CASE"
    assert detected is True
    assert parsed == {"parsed": True}
    assert rendered.html == "<p>remote page</p>"
    assert page_export.content == "<p>page export</p>"


def test_remote_markup_analysis_uses_values_and_cancellation_notification(
        tmp_path):
    markup = declaration(
        ContributionKind.MARKUP,
        "markup",
        {"mode": MarkupMode.AUGMENT, "base_ids": ("markdown",)},
    )
    plugin_root, runtime = load_process_plugin(
        tmp_path,
        contributions=((markup, ("analyze", "cancel_analysis")),),
    )
    request = MarkupAnalysisRequest(
        "analysis-remote",
        "document-remote",
        3,
        TextRange(0, 4),
        "TODO",
        (TextRange(0, 4),),
    )
    try:
        contribution_value = runtime.registry.markup[0]
        value = contribution_value.analyze(request)
        contribution_value.cancel_analysis(request.analysis_id)
        deadline = time.monotonic() + 2
        cancel_file = plugin_root / "cancel_seen.json"
        while not cancel_file.exists():
            assert time.monotonic() < deadline
            time.sleep(0.005)
    finally:
        runtime.disable("example.remote")

    assert isinstance(value, MarkupAnalysisResult)
    assert value.document_revision == 3
    assert value.window == TextRange(0, 4)
    seen = json.loads(cancel_file.read_text(encoding="utf-8"))
    assert seen["arguments"]["items"] == ["analysis-remote"]


def test_remote_markup_must_support_cooperative_cancellation(tmp_path):
    markup = declaration(
        ContributionKind.MARKUP,
        "markup",
        {"mode": MarkupMode.AUGMENT, "base_ids": ("markdown",)},
    )
    _root, runtime = load_process_plugin(
        tmp_path,
        contributions=((markup, ("analyze",)),),
    )

    record = runtime.records["example.remote"]
    assert record.status is PluginStatus.FAILED
    assert "missing cancel_analysis" in record.error


def test_remote_panel_without_ui_operations_refuses_the_whole_plugin(tmp_path):
    panel = declaration(
        ContributionKind.PROJECT_PANEL,
        "panel",
        {"default_file": "remote/panel.txt"},
    )
    _root, runtime = load_process_plugin(
        tmp_path,
        contributions=((panel, ()),),
    )

    record = runtime.records["example.remote"]
    assert record.status is PluginStatus.FAILED
    assert "missing ui_event, ui_open" in record.error
    assert runtime.registry.plugin_records("example.remote") == ()


def test_remote_plugin_cannot_register_native_qt_markup(tmp_path):
    native = declaration(
        ContributionKind.NATIVE_MARKUP,
        "native-markup",
        {"mode": MarkupMode.REPLACE, "base_ids": ("markdown",)},
    )
    _root, runtime = load_process_plugin(
        tmp_path,
        contributions=((native, ("highlighter_factory",)),),
    )

    record = runtime.records["example.remote"]
    assert record.status is PluginStatus.FAILED
    assert "cannot register native_markup" in record.error
    assert runtime.registry.plugin_records("example.remote") == ()


def test_portable_remote_capability_is_advertised_without_local_objects(
    tmp_path,
):
    root, runtime = load_process_plugin(
        tmp_path,
        requires=("entities.read",),
    )

    record = runtime.records["example.remote"]
    assert record.status is PluginStatus.LOADED, record.error
    seen = json.loads(
        (root / "initialize_seen.json").read_text(encoding="utf-8")
    )
    methods = seen["capabilities"]["entities.read"]
    assert [method["name"] for method in methods] == [
        "entities", "find", "exact_matches"
    ]
    assert methods[1] == {
        "name": "find",
        "positional": ["entity_id"],
        "optional": [],
        "keyword": [],
        "returns": "api_value",
        "mutates": False,
        "revision": "not_accepted",
    }
    runtime.disable("example.remote")


def test_required_nonportable_capability_is_refused_before_process_start(
    tmp_path,
):
    root, runtime = load_process_plugin(
        tmp_path,
        requires=("references.write",),
    )

    record = runtime.records["example.remote"]
    assert record.status is PluginStatus.UNSATISFIED
    assert "not available to process plugins" in record.error
    assert not (root / "initialize_seen.json").exists()


def test_remote_contribution_can_call_a_granted_host_capability(tmp_path):
    entity = EntitySnapshot(
        "character:mara",
        "character",
        "Mara",
        "entities/character/mara.md",
    )

    class EntityService:
        def find(self, entity_id):
            return entity if entity_id == entity.id else None

    _root, runtime = load_process_plugin(
        tmp_path,
        requires=("entities.read",),
        project_capability_resolver=(
            lambda _plugin_id, _name: EntityService()
        ),
    )
    try:
        assert runtime.registry.page_types[0].detector(
            "CALL CAPABILITY"
        ) is True
    finally:
        runtime.disable("example.remote")


def test_remote_command_uses_the_same_host_owned_action_contract(tmp_path):
    command = declaration(
        ContributionKind.COMMAND,
        "command",
        {"shortcut": "", "project_required": False},
    )
    _root, runtime = load_process_plugin(
        tmp_path,
        contributions=((command, ("invoke",)),),
    )
    try:
        assert runtime.registry.commands[0].invoke() == (
            "Remote command completed"
        )
    finally:
        runtime.disable("example.remote")
