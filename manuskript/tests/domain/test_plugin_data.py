import pytest

from manuskript.domain.plugin_data import ProjectPluginData


def test_plugin_namespaces_are_isolated_and_report_real_changes():
    changes = []
    store = ProjectPluginData()
    first = store.namespace(
        "example.archive",
        on_change=lambda: changes.append("changed"),
    )
    second = store.namespace("example.notes")

    assert first.write("documents/main.data", "raw document")
    assert not first.write("documents/main.data", "raw document")
    second.write("notes.txt", "separate")

    assert first.paths() == ("documents/main.data",)
    assert first.read("documents/main.data") == "raw document"
    assert second.read("documents/main.data") is None
    assert changes == ["changed"]
    assert store.project_files() == (
        ("plugins/example.archive/documents/main.data", "raw document"),
        ("plugins/example.notes/notes.txt", "separate"),
    )


@pytest.mark.parametrize(
    "plugin_id, path",
    [
        ("../other", "content.txt"),
        ("example.plugin", "../content.txt"),
        ("example.plugin", "/absolute.txt"),
        ("example.plugin", ""),
    ],
)
def test_plugin_namespace_rejects_paths_outside_its_owner(
        plugin_id, path):
    store = ProjectPluginData()

    if plugin_id == "../other":
        with pytest.raises(ValueError):
            store.namespace(plugin_id)
        return

    namespace = store.namespace(plugin_id)
    with pytest.raises(ValueError):
        namespace.write(path, "content")


def test_loading_project_files_keeps_absent_plugin_data_verbatim():
    store = ProjectPluginData()
    binary = b"\x00\x01raw"

    store.load_project_files({
        "settings.txt": "{}",
        "plugins/example.missing/data.bin": binary,
        "plugins\\example.text\\source.txt": "editable",
    })

    assert store.project_files() == (
        ("plugins/example.missing/data.bin", binary),
        ("plugins/example.text/source.txt", "editable"),
    )
