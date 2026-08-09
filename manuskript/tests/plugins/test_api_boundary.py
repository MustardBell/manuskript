"""Plugins may only reach core through the published surface.

Documenting the boundary does not hold it. This walks the runtime modules of
every installed plugin and fails if one imports anything from Manuskript
outside the published modules.

Plugin *tests* are excluded: they legitimately use core test helpers and
fixtures, which are not part of the plugin contract.
"""

import ast
import os

import pytest

from manuskript.functions import appPath


#: What a plugin's runtime code may import from Manuskript.
PUBLISHED = (
    "manuskript.plugins",       # contracts a plugin constructs
    "manuskript.plugins.ui",    # bases a plugin subclasses
)

#: Directories inside a plugin that are not runtime code.
NON_RUNTIME = {"tests", "test", "__pycache__"}


def published(module):
    """Whether ``module`` is inside the plugin-facing surface."""
    return any(
        module == name or module.startswith(name + ".")
        for name in PUBLISHED
    )


def core_imports(path):
    """Every ``manuskript.*`` module name imported by one file."""
    with open(path, encoding="utf-8") as handle:
        try:
            tree = ast.parse(handle.read(), filename=path)
        except SyntaxError:
            pytest.fail("Cannot parse {}".format(path))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(
                alias.name for alias in node.names
                if alias.name.split(".")[0] == "manuskript"
            )
        elif isinstance(node, ast.ImportFrom):
            # Relative imports stay inside the plugin.
            if node.level or not node.module:
                continue
            if node.module.split(".")[0] == "manuskript":
                found.add(node.module)
    return found


#: The root PluginRuntime is given in main.py.
PLUGIN_ROOT = "manuskript/plugins"


def plugin_runtime_files():
    root = appPath(PLUGIN_ROOT)
    if not os.path.isdir(root):
        return []
    files = []
    for name in sorted(os.listdir(root)):
        directory = os.path.join(root, name)
        if not os.path.isdir(directory) or name in NON_RUNTIME:
            continue
        if not os.path.isfile(os.path.join(directory, "plugin.json")):
            continue
        for base, directories, filenames in os.walk(directory):
            directories[:] = [
                d for d in directories if d not in NON_RUNTIME
            ]
            files.extend(
                os.path.join(base, f)
                for f in sorted(filenames)
                if f.endswith(".py")
            )
    return files


def test_installed_plugins_import_only_the_published_surface():
    files = plugin_runtime_files()
    if not files:
        pytest.skip("no plugins installed in this checkout")

    offenders = {}
    for path in files:
        outside = sorted(
            module for module in core_imports(path)
            if not published(module)
        )
        if outside:
            offenders[
                os.path.relpath(path, appPath(PLUGIN_ROOT))
            ] = outside

    assert not offenders, (
        "Plugin runtime code may only import {}. Reaching into other core "
        "modules couples the plugin to internals that carry no stability "
        "promise; ask for a capability instead.\nOffenders: {}".format(
            " or ".join(PUBLISHED),
            offenders,
        )
    )


# ------------------------------------------------------- the guard itself

def test_the_guard_accepts_the_published_modules(tmp_path):
    module = tmp_path / "ok.py"
    module.write_text(
        "from manuskript.plugins import PageTypeContribution\n"
        "from manuskript.plugins.ui import IndexCardStyle\n"
        "from .local import helper\n"
        "import os\n",
        encoding="utf-8",
    )

    assert all(published(name) for name in core_imports(str(module)))


def test_the_guard_rejects_reaching_into_core(tmp_path):
    module = tmp_path / "bad.py"
    module.write_text(
        "from manuskript.converters.markdownToBBCode import "
        "markdown_to_bbcode\n",
        encoding="utf-8",
    )

    found = core_imports(str(module))

    assert found == {"manuskript.converters.markdownToBBCode"}
    assert not any(published(name) for name in found)


def test_the_guard_notices_plain_import_statements(tmp_path):
    module = tmp_path / "plain.py"
    module.write_text("import manuskript.settings\n", encoding="utf-8")

    assert core_imports(str(module)) == {"manuskript.settings"}
    assert not published("manuskript.settings")


def test_manuskript_plugins_prefix_is_not_matched_loosely():
    # A module that merely starts with the same characters is not published.
    assert not published("manuskript.pluginsomething")
    assert published("manuskript.plugins.ui")
