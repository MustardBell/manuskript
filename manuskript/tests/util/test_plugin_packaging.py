import json
from pathlib import Path

from util.plugin_packaging import plugin_data_entries, rsync_filter_lines


def declare_submodule(root, path):
    gitmodules = root / ".gitmodules"
    gitmodules.write_text(
        '[submodule "{}"]\n\tpath = {}\n\turl = https://example.invalid\n'.format(
            path,
            path,
        ),
        encoding="utf-8",
    )
    return gitmodules


def test_packaging_includes_runtime_files_but_not_tests_or_docs(tmp_path):
    plugin = tmp_path / "example"
    plugin.mkdir()
    (plugin / "plugin.json").write_text(
        json.dumps({"id": "example"}),
        encoding="utf-8",
    )
    (plugin / "plugin.py").write_text("", encoding="utf-8")
    (plugin / "model.py").write_text("", encoding="utf-8")
    (plugin / "README.md").write_text("docs", encoding="utf-8")
    tests = plugin / "tests"
    tests.mkdir()
    (tests / "test_plugin.py").write_text("", encoding="utf-8")

    gitmodules = declare_submodule(tmp_path, "example")
    entries = plugin_data_entries(tmp_path, gitmodules)

    sources = {Path(source) for source, _destination in entries}
    assert plugin / "plugin.json" in sources
    assert plugin / "plugin.py" in sources
    assert plugin / "model.py" in sources
    assert plugin / "README.md" not in sources
    assert tests / "test_plugin.py" not in sources


def test_packaging_ignores_folders_without_manifests(tmp_path):
    (tmp_path / "internal_helpers").mkdir()
    gitmodules = declare_submodule(tmp_path, "internal_helpers")

    assert plugin_data_entries(tmp_path, gitmodules) == []


def test_packaging_ignores_undeclared_local_plugins(tmp_path):
    shipped = tmp_path / "shipped"
    shipped.mkdir()
    (shipped / "plugin.json").write_text("{}", encoding="utf-8")
    local = tmp_path / "private_local"
    local.mkdir()
    (local / "plugin.json").write_text("{}", encoding="utf-8")
    gitmodules = declare_submodule(tmp_path, "shipped")

    entries = plugin_data_entries(tmp_path, gitmodules)

    assert all("private_local" not in source for source, _target in entries)


def test_rsync_filter_excludes_undeclared_plugin_directories(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plugin_root = tmp_path / "manuskript" / "plugins"
    shipped = plugin_root / "shipped"
    shipped.mkdir(parents=True)
    (shipped / "plugin.json").write_text("{}", encoding="utf-8")
    gitmodules = declare_submodule(tmp_path, "manuskript/plugins/shipped")

    lines = rsync_filter_lines("manuskript/plugins", gitmodules)

    assert "+ /manuskript/plugins/shipped/***" in lines
    assert "- /manuskript/plugins/*/" in lines
    assert not any("private" in line for line in lines)
