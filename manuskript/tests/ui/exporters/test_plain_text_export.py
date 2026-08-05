from types import SimpleNamespace
from unittest.mock import MagicMock

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItem, QStandardItemModel

from manuskript.enums import Outline
from manuskript.exporter.manuskript.plainText import plainText
from manuskript.exporter.pandoc.HTML import HTML as PandocHTML
from manuskript.exporter.pandoc.PDF import PDF as PandocPDF
from manuskript.exporter.pandoc.outputFormats import DocX, ePub
from manuskript.exporter.pandoc.plainText import latex as PandocLatex
from manuskript.models import outlineItem, outlineModel
from manuskript.plugins import PageExportDocument
from manuskript.media_types import (
    DOCX as DOCX_MEDIA_TYPE,
    HTML,
    LATEX,
    MARKDOWN,
)
from manuskript.ui.exporters.manuskript.plainTextSettings import (
    exporterSettings,
)


def make_settings():
    return {
        "Content": {
            "More": False,
            "FolderTitle": True,
            "TextTitle": True,
            "TextText": True,
            "IgnoreCompile": False,
            "Parent": False,
            "ParentID": "",
            "Labels": False,
            "LabelValues": [],
            "Status": False,
            "StatusValues": [],
        },
        "Separator": {
            "FF": "\n",
            "TT": "\n",
            "FT": "\n",
            "TF": "\n",
        },
        "Transform": {
            "Dash": False,
            "Ellipse": False,
            "Spaces": False,
            "DoubleQuotes": False,
            "SingleQuote": False,
            "Custom": [],
        },
    }


def make_outline():
    model = outlineModel()
    chapter = outlineItem(
        title="Chapter",
        parent=model.rootItem,
    )
    first = outlineItem(
        title="First",
        _type="md",
        parent=chapter,
    )
    first.setData(Outline.text, "One")
    first.setData(Outline.label, 0)
    first.setData(Outline.status, 1)
    second = outlineItem(
        title="Second",
        _type="md",
        parent=chapter,
    )
    second.setData(Outline.text, "Two")
    second.setData(Outline.label, 1)
    second.setData(Outline.status, 2)
    return model, chapter, first, second


def make_format(model):
    context = SimpleNamespace(
        outline_model=model,
        parent=None,
    )
    return plainText(context)


def test_plain_text_export_honors_compile_and_ignore_compile():
    model, chapter, first, second = make_outline()
    second.setData(Outline.compile, 0)
    settings = make_settings()
    export_format = make_format(model)

    compiled = export_format.concatenate(
        model.rootItem,
        settings,
    )
    settings["Content"]["IgnoreCompile"] = True
    all_items = export_format.concatenate(
        model.rootItem,
        settings,
    )

    assert "First" in compiled
    assert "Second" not in compiled
    assert "First" in all_items
    assert "Second" in all_items


def test_plain_text_export_honors_label_and_status_filters():
    model, chapter, first, second = make_outline()
    settings = make_settings()
    settings["Content"].update(
        {
            "Labels": True,
            "LabelValues": [1],
            "Status": True,
            "StatusValues": [2],
        }
    )

    output = make_format(model).concatenate(
        model.rootItem,
        settings,
    )

    assert "First" not in output
    assert "One" not in output
    assert "Second" in output
    assert "Two" in output


def test_plain_text_export_starts_below_selected_parent():
    model, chapter, first, second = make_outline()
    settings = make_settings()
    settings["Content"].update(
        {
            "Parent": True,
            "ParentID": chapter.ID(),
        }
    )
    settings_widget = MagicMock()
    settings_widget.getSettings.return_value = settings

    output = make_format(model).output(settings_widget)

    assert "Chapter" not in output
    assert "First" in output
    assert "Second" in output


def test_export_filter_settings_round_trip_selected_values():
    model, chapter, first, second = make_outline()
    labels = QStandardItemModel()
    labels.appendRow(QStandardItem("Idea"))
    labels.appendRow(QStandardItem("Conflict"))
    statuses = QStandardItemModel()
    statuses.appendRow(QStandardItem("Draft"))
    statuses.appendRow(QStandardItem("Final"))
    context = SimpleNamespace(
        outline_model=model,
        label_model=labels,
        status_model=statuses,
    )
    export_format = MagicMock()
    widget = exporterSettings(export_format, context)
    widget.chkContentParent.setChecked(True)
    widget.cmbContentParent.setCurrentIndex(chapter.row())
    widget.chkContentLabels.setChecked(True)
    widget.lstContentLabels.item(0).setCheckState(Qt.Unchecked)
    widget.chkContentStatus.setChecked(True)
    widget.lstContentStatus.item(1).setCheckState(Qt.Unchecked)

    settings = widget.getSettings()
    restored = exporterSettings(export_format, context)
    restored.settings = settings
    restored.updateFromSettings()

    assert settings["Content"]["ParentID"] == chapter.ID()
    assert settings["Content"]["LabelValues"] == [1]
    assert settings["Content"]["StatusValues"] == [0]
    assert restored.chkContentParent.isChecked()
    assert (
        restored.lstContentLabels.item(0).checkState()
        == Qt.Unchecked
    )
    assert (
        restored.lstContentStatus.item(1).checkState()
        == Qt.Unchecked
    )


def test_pandoc_embeds_exact_text_fragments_and_falls_back_for_binary_formats():
    class PageTypes:
        def __init__(self):
            self.targets = []

        def export_document(
                self, item, target_format, source=None,
                route_id=None):
            self.targets.append((target_format, route_id))
            if target_format == MARKDOWN:
                return PageExportDocument(
                    "semantic **Markdown**",
                    MARKDOWN,
                )
            return PageExportDocument(
                "<custom-{}>```</custom-{}>".format(
                    target_format,
                    target_format,
                ),
                target_format,
            )

    page_types = PageTypes()
    exporter = SimpleNamespace(
        context=SimpleNamespace(page_types=page_types)
    )
    item = outlineItem(title="Custom page", _type="md")
    item.setData(Outline.text, "raw plugin source")
    settings = make_settings()

    html = PandocHTML(exporter).processItemText(item, settings)
    latex = PandocLatex(exporter).processItemText(item, settings)
    pdf = PandocPDF(exporter).processItemText(item, settings)
    epub = ePub(exporter).processItemText(item, settings)
    docx = DocX(exporter).processItemText(item, settings)

    assert "````{=html}" in html
    assert "<custom-text/html>```</custom-text/html>" in html
    assert "````{=latex}" in latex
    assert "````{=latex}" in pdf
    assert "````{=html}" in epub
    assert docx == "semantic **Markdown**\n"
    assert page_types.targets == [
        (HTML, "text/html|text/html"),
        (LATEX, "application/x-latex|application/x-latex"),
        (LATEX, "application/pdf|application/x-latex"),
        (HTML, "application/epub+zip|text/html"),
        (MARKDOWN, DOCX_MEDIA_TYPE + "|text/markdown"),
    ]
