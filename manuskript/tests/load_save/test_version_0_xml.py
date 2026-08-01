from PyQt5.QtGui import QStandardItem, QStandardItemModel

from manuskript.load_save.version_0 import (
    loadStandardItemModelXML,
    saveStandardItemModelXML,
)


def make_model():
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels(["Name", "Value"])
    model.appendRow(
        [QStandardItem("Character"), QStandardItem("Alice")]
    )
    model.setVerticalHeaderLabels(["First"])
    return model


def test_legacy_standard_model_xml_loads_from_memory():
    xml = saveStandardItemModelXML(make_model())
    target = QStandardItemModel()

    assert loadStandardItemModelXML(
        target,
        xml,
        fromString=True,
    )
    assert target.item(0, 0).text() == "Character"
    assert target.item(0, 1).text() == "Alice"


def test_legacy_standard_model_xml_loads_from_file(tmp_path):
    xml_file = tmp_path / "model.xml"
    xml_file.write_bytes(saveStandardItemModelXML(make_model()))
    target = QStandardItemModel()

    assert loadStandardItemModelXML(target, str(xml_file))
    assert target.item(0, 1).text() == "Alice"


def test_legacy_standard_model_xml_rejects_malformed_input():
    target = QStandardItemModel()

    assert not loadStandardItemModelXML(
        target,
        b"<broken>",
        fromString=True,
    )
