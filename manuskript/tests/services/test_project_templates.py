from unittest.mock import MagicMock

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItemModel

from manuskript.enums import Outline
from manuskript.models import outlineModel
from manuskript.services.project_templates import (
    ProjectTemplateInitializer,
    ProjectTemplateModels,
)


def test_project_template_initializer_populates_models():
    settings = MagicMock()
    flat_data = QStandardItemModel()
    labels = QStandardItemModel()
    statuses = QStandardItemModel()
    outline = outlineModel()
    load_empty_project = MagicMock()
    models = ProjectTemplateModels(
        flat_data=flat_data,
        labels=labels,
        statuses=statuses,
        outline=outline,
    )
    initializer = ProjectTemplateInitializer(
        settings,
        load_empty_project,
        lambda: models,
    )

    initializer.initialize(
        ("Novel", [(2, "Chapter"), (500, None)], "Fiction"),
        non_fiction=False,
        labels=[(Qt.yellow, "Idea")],
        statuses=["", "Draft"],
    )

    settings.reset_to_defaults.assert_called_once_with()
    load_empty_project.assert_called_once_with()
    assert flat_data.rowCount() == 2
    assert flat_data.columnCount() == 8
    assert labels.item(0, 0).text() == "Idea"
    assert statuses.rowCount() == 2
    assert outline.rootItem.childCount() == 2
    assert outline.rootItem.child(0).title() == "Chapter 1"
    assert outline.rootItem.child(0).data(Outline.setGoal) == 500


def test_non_fiction_template_selects_simple_view_mode():
    settings = MagicMock()
    models = ProjectTemplateModels(
        flat_data=QStandardItemModel(),
        labels=QStandardItemModel(),
        statuses=QStandardItemModel(),
        outline=outlineModel(),
    )
    initializer = ProjectTemplateInitializer(
        settings,
        MagicMock(),
        lambda: models,
    )

    initializer.initialize(
        ("Empty", [], "Non-fiction"),
        non_fiction=True,
        labels=[],
        statuses=[],
    )

    assert settings.viewMode == "simple"
