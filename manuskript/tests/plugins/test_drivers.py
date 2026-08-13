from manuskript.plugins.drivers import PluginDriver
from manuskript.plugins.runtime import PluginRuntime, PluginStatus
from manuskript.plugins.runtimes import RuntimeAvailability, RuntimeKind
from manuskript.services.plugin_preferences import InMemoryPluginPreferences
from manuskript.tests.plugins.test_runtime import create_plugin


class RecordingProcessDriver(PluginDriver):
    kind = RuntimeKind.PROCESS

    def __init__(self, available=True):
        self.available = available
        self.events = []

    def availability(self, manifest):
        self.events.append(("available", manifest.id))
        return RuntimeAvailability(
            self.available,
            error="runtime is deliberately absent" if not self.available else "",
        )

    def load(self, manifest, registrar, context=None):
        self.events.append(("load", manifest.id))
        return {"plugin": manifest.id}

    def activate(self, manifest, session, registrar):
        self.events.append(("activate", session["plugin"]))

    def deactivate(self, manifest, session):
        self.events.append(("deactivate", session["plugin"]))


PROCESS_MANIFEST = {"runtime": {
    "kind": "process",
    "protocol_version": 1,
    "commands": {"linux": ["unused-process"]},
}}


def test_runtime_delegates_process_lifecycle_without_importing_python(
    tmp_path,
):
    create_plugin(
        tmp_path,
        source="raise RuntimeError('must remain unimported')\n",
        manifest=PROCESS_MANIFEST,
    )
    driver = RecordingProcessDriver()
    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(["example.plugin"]),
        drivers=(driver,),
    )

    runtime.discover()
    runtime.load_enabled()
    runtime.disable("example.plugin")

    assert driver.events == [
        ("available", "example.plugin"),
        ("load", "example.plugin"),
        ("activate", "example.plugin"),
        ("deactivate", "example.plugin"),
    ]


def test_unavailable_driver_refuses_plugin_before_load(tmp_path):
    create_plugin(tmp_path, manifest=PROCESS_MANIFEST)
    driver = RecordingProcessDriver(available=False)
    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(["example.plugin"]),
        drivers=(driver,),
    )

    runtime.discover()
    runtime.load_enabled()

    record = runtime.records["example.plugin"]
    assert record.status is PluginStatus.UNSATISFIED
    assert record.error == "runtime is deliberately absent"
    assert driver.events == [("available", "example.plugin")]


def test_explicit_empty_driver_set_does_not_restore_python_implicitly(
    tmp_path,
):
    create_plugin(tmp_path)
    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(["example.plugin"]),
        drivers=(),
    )

    runtime.discover()
    runtime.load_enabled()

    assert runtime.records["example.plugin"].status is PluginStatus.UNSATISFIED


def test_runtime_rejects_ambiguous_driver_ownership(tmp_path):
    first = RecordingProcessDriver()
    second = RecordingProcessDriver()

    try:
        PluginRuntime(
            [tmp_path],
            InMemoryPluginPreferences(),
            drivers=(first, second),
        )
    except ValueError as error:
        assert "unique" in str(error)
    else:
        raise AssertionError("duplicate runtime driver kind was accepted")
