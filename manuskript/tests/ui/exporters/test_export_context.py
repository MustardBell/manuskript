from unittest.mock import MagicMock, patch

import pytest
from PyQt5.QtGui import QStandardItem, QStandardItemModel

from manuskript import exporter
from manuskript.exporter.context import ExportContext
from manuskript.exporter.pandoc import pandocExporter


def make_context(project_file="/tmp/novel.msk"):
    tool_paths = MagicMock()
    tool_paths.get.return_value = ""
    return ExportContext(
        project_file=project_file,
        outline_model=MagicMock(),
        flat_data_model=QStandardItemModel(1, 8),
        label_model=MagicMock(),
        status_model=MagicMock(),
        parent=MagicMock(),
        tool_paths=tool_paths,
    )


def test_export_context_resolves_project_directory():
    context = make_context("/work/novel/manuscript.msk")

    assert context.project_path == "/work/novel"


def test_exporter_factory_builds_isolated_project_graphs():
    context = make_context()

    first = exporter.create_exporters(context)
    second = exporter.create_exporters(context)

    assert first[0] is not second[0]
    assert first[1] is not second[1]
    for first_exporter, second_exporter in zip(first, second):
        assert first_exporter.exportTo is not second_exporter.exportTo
        for first_format, second_format in zip(
            first_exporter.exportTo,
            second_exporter.exportTo,
        ):
            assert first_format is not second_format
            assert first_format.context is context
            assert second_format.context is context


def test_plain_text_output_uses_context_outline_root():
    context = make_context()
    context.outline_model.rootItem = object()
    plain_text = exporter.create_exporters(context)[0].getFormatByName(
        "Plain text"
    )
    settings_widget = MagicMock()
    settings = {"Content": {}}
    settings_widget.getSettings.return_value = settings

    with patch.object(
        plain_text,
        "concatenate",
        return_value="Rendered manuscript",
    ) as concatenate:
        output = plain_text.output(settings_widget)

    assert output == "Rendered manuscript"
    concatenate.assert_called_once_with(
        context.outline_model.rootItem,
        settings,
    )


def test_pandoc_metadata_comes_from_context_flat_data():
    context = make_context()
    context.flat_data_model.setItem(0, 0, QStandardItem("My Novel"))
    context.flat_data_model.setItem(0, 1, QStandardItem("A Subtitle"))
    context.flat_data_model.setItem(0, 6, QStandardItem("A. Writer"))
    pandoc = pandocExporter(context)

    assert pandoc.metadata_arguments() == [
        "--variable=title:My Novel",
        "--variable=subtitle:A Subtitle",
        "--variable=author:A. Writer",
        "--metadata=title:My Novel",
    ]


def test_pandoc_metadata_supplies_nonempty_default_title():
    pandoc = pandocExporter(make_context())

    assert pandoc.metadata_arguments() == ["--metadata=title:Untitled"]


def test_pandoc_restores_cursor_when_process_start_fails():
    pandoc = pandocExporter(make_context())

    with patch.object(pandoc, "isValid", return_value=2), patch(
        "manuskript.exporter.pandoc.subprocess.Popen",
        side_effect=OSError("pandoc failed"),
    ), patch("manuskript.exporter.pandoc.qApp") as application:
        with pytest.raises(OSError, match="pandoc failed"):
            pandoc.convert("content", [])

    application.setOverrideCursor.assert_called_once()
    application.restoreOverrideCursor.assert_called_once_with()
