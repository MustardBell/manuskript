"""Project models are the project's, not a window's.

A window that answers questions about things it does not own is a service
locator, and models were the largest example: nine modules read
``window.mdlOutline`` and friends because a window happened to have them
installed on it.

They no longer do, and this is what keeps it that way. It exists because
checking by hand got it wrong: a grep for ``window.mdl`` reported zero
while thirteen reads remained, spelled ``self.mw.mdl`` and
``window.projectPluginData``. Reading the syntax instead of the text does
not care what the variable was called.
"""

import ast
import pathlib


#: Names that mean "a main window" in this codebase.
WINDOW_NAMES = frozenset({
    "window", "mw", "MW", "_window", "mainWindow",
})

#: Where the window attributes are still deliberately written, until the
#: tests that read them are migrated too.
ALLOWED = ("project_model_factory.py",)

MODEL_ATTRIBUTES = ("mdl", "projectPluginData")


def production_modules():
    """Every module that ships, tests excluded."""
    root = pathlib.Path(__file__).resolve().parents[1]
    for path in sorted(root.rglob("*.py")):
        text = str(path)
        if "/tests/" in text or text.endswith(ALLOWED):
            continue
        yield path


def rooted_at(node):
    """The name a chain of attribute accesses starts from.

    ``self.mw.mdlLabels`` is rooted at ``mw``; ``window.mdlOutline`` at
    ``window``. Only the nearest name matters, which is what makes this
    indifferent to how deeply the window was reached through.
    """
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def model_reads_through_a_window(path):
    """Every place this module asks a window for a project model."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if not node.attr.startswith(MODEL_ATTRIBUTES):
            continue
        if rooted_at(node.value) in WINDOW_NAMES:
            found.append((node.lineno, node.attr))
    return found


def test_no_shipping_module_asks_a_window_for_a_project_model():
    """Ask the project runtime, which owns them.

    A window may hold widgets that show a model; it does not own the
    model. Reading one through a window is how a window came to be able
    to answer any question at all, and it is what stops two windows from
    being two views of one project rather than two half-projects.
    """
    offenders = {}
    for path in production_modules():
        found = model_reads_through_a_window(path)
        if found:
            offenders[str(path)] = found

    assert not offenders, (
        "These modules ask a window for project models. Take the models, "
        "or the project runtime that owns them, as a collaborator "
        "instead: {}".format(offenders)
    )


def test_the_check_can_see_a_read_when_there_is_one(tmp_path):
    """Proof the guard measures something.

    A passing result above has to be a fact about the code rather than a
    fact about this test being unable to notice anything.
    """
    module = tmp_path / "offender.py"
    module.write_text(
        "def paint(window):\n"
        "    return window.mdlOutline.rootItem\n"
        "\n"
        "class Panel:\n"
        "    def refresh(self):\n"
        "        return self.mw.mdlLabels.item(0)\n",
        encoding="utf-8",
    )

    found = model_reads_through_a_window(module)

    assert [attribute for _line, attribute in found] == [
        "mdlOutline", "mdlLabels",
    ]


def test_an_objects_own_model_field_is_not_a_window_read(tmp_path):
    """Plenty of objects hold a model in a field named ``mdlCharacter``.

    That is old naming, not a window being asked -- and counting it would
    report seventy-five failures that are nobody's bug.
    """
    module = tmp_path / "innocent.py"
    module.write_text(
        "class Delegate:\n"
        "    def paint(self):\n"
        "        return self.mdlCharacter.rowCount()\n",
        encoding="utf-8",
    )

    assert model_reads_through_a_window(module) == []
