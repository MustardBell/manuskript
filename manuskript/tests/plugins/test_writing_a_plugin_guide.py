"""The guide's first example is built and loaded, not just displayed.

A tutorial whose code does not run is worse than no tutorial: somebody
copies it, it fails, and they conclude the plugin system is broken. So the
example in ``docs/WRITING_A_PLUGIN.md`` is extracted from the document
itself and loaded through the real runtime. If the contract changes and
the guide is not updated, this fails.
"""

import pathlib
import re

from manuskript.plugins.runtime import PluginRuntime, PluginStatus
from manuskript.services.plugin_preferences import (
    InMemoryPluginPreferences,
)


GUIDE = (
    pathlib.Path(__file__).resolve().parents[3]
    / "docs"
    / "WRITING_A_PLUGIN.md"
)

PLUGIN_ID = "vendor.hello"


def fenced_blocks(text, language):
    """Every fenced code block of one language, in order."""
    return re.findall(
        r"```" + language + r"\n(.*?)```",
        text,
        re.S,
    )


def guide_example(tmp_path):
    """The guide's smallest-plugin example, written out as files.

    Taken from the document rather than duplicated here, so the thing
    tested is the thing somebody reads.
    """
    text = GUIDE.read_text(encoding="utf-8")
    manifests = fenced_blocks(text, "json")
    sources = fenced_blocks(text, "python")
    assert manifests, "the guide has no manifest example any more"
    assert sources, "the guide has no plugin source example any more"

    root = tmp_path / "plugins"
    root.mkdir()
    plugin = root / PLUGIN_ID
    plugin.mkdir()
    (plugin / "plugin.json").write_text(manifests[0], encoding="utf-8")
    (plugin / "plugin.py").write_text(sources[0], encoding="utf-8")
    return root


def test_the_guides_first_example_loads_and_contributes_a_panel(
        tmp_path):
    root = guide_example(tmp_path)
    runtime = PluginRuntime(
        [root],
        InMemoryPluginPreferences([PLUGIN_ID]),
    )

    runtime.discover()
    runtime.load_enabled()

    record = runtime.records[PLUGIN_ID]
    assert record.status is PluginStatus.LOADED, record.error
    panels = runtime.registry.plugin_records(PLUGIN_ID, "project_panel")
    assert [entry.id for entry in panels] == ["vendor.hello.panel"]


def test_the_guides_example_is_found_without_running_its_code(tmp_path):
    """The guide promises the manifest is read before any code runs, and
    that a plugin starts Disabled.
    """
    root = guide_example(tmp_path)
    runtime = PluginRuntime([root], InMemoryPluginPreferences())

    records = runtime.discover()

    assert [record.manifest.id for record in records] == [PLUGIN_ID]
    assert records[0].status is PluginStatus.DISABLED
    assert runtime.registry.records("project_panel") == ()


def test_the_guides_descriptor_id_would_be_refused_without_its_dot():
    """The guide states the rule; this is the rule refusing."""
    import pytest

    from manuskript.plugins import ExtensionDescriptor

    with pytest.raises(ValueError, match="Invalid extension ID"):
        ExtensionDescriptor(id="panel", name="Hello")
