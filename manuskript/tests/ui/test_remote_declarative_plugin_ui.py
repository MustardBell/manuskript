import json
import time

from PyQt5.QtWidgets import qApp

from manuskript.plugins.contracts import ContributionKind
from manuskript.plugins.runtime import PluginRuntime, PluginStatus
from manuskript.plugins.ui_contract import (
    UiControl,
    UiControlKind,
    UiDocument,
    UiResponse,
)
from manuskript.plugins.values import api_value_codec
from manuskript.services.plugin_preferences import InMemoryPluginPreferences
from manuskript.tests.plugins.test_process_driver import (
    create_process_plugin,
    declaration,
)


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline
        qApp.processEvents()
        time.sleep(0.005)


def response(revision, value):
    return UiResponse(UiDocument("example.remote.settings", revision, (
        UiControl(
            "name",
            UiControlKind.TEXT,
            "Display name",
            value=value,
        ),
    )))


def test_process_plugin_panel_is_rendered_and_updated_by_the_host(tmp_path):
    contribution = declaration(
        ContributionKind.SETTINGS_PANEL,
        "settings",
        {},
    )
    root = create_process_plugin(
        tmp_path,
        contributions=((
            contribution,
            ("ui_open", "ui_event", "ui_close"),
        ),),
    )
    data_path = root / "fixture_data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    codec = api_value_codec()
    data["results"]["ui_open"] = codec.encode(response(0, "Mara"))
    data["results"]["ui_event"] = codec.encode(response(1, "Mara Vale"))
    data_path.write_text(json.dumps(data), encoding="utf-8")

    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(["example.remote"]),
        project_format=2,
    )
    runtime.discover()
    runtime.load_enabled()
    record = runtime.records["example.remote"]
    assert record.status is PluginStatus.LOADED, record.error
    widget = runtime.registry.settings_panels[0].widget_factory(None)
    widget.show()
    try:
        wait_until(lambda: widget.document is not None)
        assert widget.controls["name"].text() == "Mara"
        assert widget.controls["name"].accessibleName() == "Display name"

        widget.controls["name"].setText("ignored by fixture")
        widget.controls["name"].editingFinished.emit()
        wait_until(lambda: widget.document.revision == 1)
        assert widget.controls["name"].text() == "Mara Vale"
    finally:
        widget.close()
        runtime.disable("example.remote")
