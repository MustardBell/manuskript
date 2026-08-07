"""Loading a book counts its words once, not once per document.

Adding a document to a folder makes that folder's total wrong, so the
correction walks up to the root emitting as it goes. Loading a book that
way recomputes the same ancestors once per document beneath them: 231,658
index lookups for 918 items, measured on a real project, to arrive at the
totals a single final pass computes anyway.

The model already had the mechanism -- ``batchWordCountUpdates``, used for
bulk compile changes -- and loading simply never asked for it. These tests
pin both halves: that loading asks, and that the totals are right anyway,
because a faster load that reports the wrong word count is not a faster
load.
"""

from unittest.mock import patch

from manuskript.enums import Outline
from manuskript.load_save import version_1
from manuskript.models.outlineItem import outlineItem
from manuskript.services.project_model_factory import ProjectModelFactory
from manuskript.services.project_persistence import (
    ProjectPersistenceContext,
)
from manuskript.settingsManager import SettingsManager

from PyQt5.QtCore import QObject


DOCUMENTS = {
    # folder -> {document: text}
    "0-Act_One": {
        "0-Opening.md": "One two three four five.",
        "1-Rising.md": "Six seven eight.",
    },
    "1-Act_Two": {
        "0-Middle.md": "Nine ten.",
    },
}


def write_project(root):
    """A project on disk, in the format version 1 actually reads.

    Written by hand rather than saved from a model, so the test states the
    shape it depends on instead of trusting the writer to agree with the
    reader.
    """
    project = root / "book.msk"
    project.write_text("1", encoding="utf-8")
    folder = root / "book"
    (folder / "outline").mkdir(parents=True)
    (folder / "MANUSKRIPT").write_text("1", encoding="utf-8")

    item_id = 1
    for index, (name, documents) in enumerate(DOCUMENTS.items()):
        directory = folder / "outline" / name
        directory.mkdir()
        item_id += 1
        (directory / "folder.txt").write_text(
            "title:          {}\nID:             {}\ntype:"
            "           folder\ncompile:        2\n".format(name, item_id),
            encoding="utf-8",
        )
        for document, text in documents.items():
            item_id += 1
            (directory / document).write_text(
                "title:          {}\nID:             {}\ntype:"
                "           md\ncompile:        2\n\n\n{}".format(
                    document[:-3], item_id, text,
                ),
                encoding="utf-8",
            )
    return project


def load(project):
    settings = SettingsManager()
    with patch.object(settings, "apply_loaded_settings_effects"):
        settings.reset_to_defaults()
    parent = QObject()
    models = ProjectModelFactory().create(parent, settings)
    result = version_1.loadProject(
        ProjectPersistenceContext(
            project_file=str(project),
            models=models,
            settings=settings,
        )
    )
    # The parent is returned so Qt does not delete the models under the
    # test the moment this function ends.
    return models, result, parent


def test_loading_asks_the_model_to_defer_its_word_counts(tmp_path):
    """One recursive pass at the end, rather than one walk per document."""
    project = write_project(tmp_path)
    passes = []
    original = outlineItem.recalculateWordCount

    def record(self, recursive=False):
        passes.append(recursive)
        return original(self, recursive=recursive)

    with patch.object(
        outlineItem, "recalculateWordCount", record,
    ):
        models, _result, _parent = load(project)

    # The batch closed dirty and settled the whole tree in one pass. The
    # count of passes is what matters: without deferral there are none,
    # because every insert had already walked its own ancestors.
    assert passes, "loading never deferred an aggregate word count"
    assert passes[0] is True
    assert models.outline.rootItem.data(Outline.wordCount)


def test_the_totals_are_right_after_a_deferred_load(tmp_path):
    """The half that makes the other half worth having."""
    project = write_project(tmp_path)

    models, _result, _parent = load(project)

    root = models.outline.rootItem
    expected_words = sum(
        len(text.split())
        for documents in DOCUMENTS.values()
        for text in documents.values()
    )
    assert int(root.data(Outline.wordCount)) == expected_words

    folders = {child.title(): child for child in root.children()}
    assert set(folders) == set(DOCUMENTS)
    for name, documents in DOCUMENTS.items():
        folder = folders[name]
        assert int(folder.data(Outline.wordCount)) == sum(
            len(text.split()) for text in documents.values()
        )
        # And each document counts its own text, not its neighbour's.
        counted = {
            child.title(): int(child.data(Outline.wordCount))
            for child in folder.children()
        }
        assert counted == {
            document[:-3]: len(text.split())
            for document, text in documents.items()
        }


def test_a_folder_total_still_follows_an_edit_after_loading(tmp_path):
    """The deferral is for the load. Once it is over, a folder must go
    back to following its children immediately -- otherwise the batch has
    leaked into the session.
    """
    project = write_project(tmp_path)
    models, _result, _parent = load(project)
    root = models.outline.rootItem
    folder = next(
        child for child in root.children() if child.title() == "1-Act_Two"
    )
    before = int(folder.data(Outline.wordCount))

    document = folder.children()[0]
    document.setData(Outline.text, "One two three four five six seven.")

    assert int(folder.data(Outline.wordCount)) == before + 5
    assert not models.outline.wordCountUpdatesDeferred
