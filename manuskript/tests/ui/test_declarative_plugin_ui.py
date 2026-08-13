import time

from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTreeWidget,
    qApp,
)

from manuskript.plugins.ui_contract import (
    UiControl,
    UiControlKind,
    UiColumn,
    UiDocument,
    UiItem,
)
from manuskript.ui.plugins.declarative_ui import (
    DeclarativeUiWidget,
    StaticUiController,
)


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline
        qApp.processEvents()
        time.sleep(0.005)


def document(revision=0, value="Mara"):
    return UiDocument("example.panel", revision, (
        UiControl(
            "name",
            UiControlKind.TEXT,
            "Character name",
            description="The name shown to readers.",
            value=value,
            required=True,
        ),
        UiControl(
            "save",
            UiControlKind.BUTTON,
            "Save character",
        ),
    ))


def test_host_renders_labels_accessible_names_and_native_focus_contract():
    widget = DeclarativeUiWidget(
        StaticUiController(document()), "settings"
    )
    widget.show()
    wait_until(lambda: widget.document is not None)

    editor = widget.controls["name"]
    button = widget.controls["save"]
    label = next(
        item for item in widget.findChildren(QLabel)
        if item.buddy() is editor
    )
    assert isinstance(editor, QLineEdit)
    assert isinstance(button, QPushButton)
    assert label.text() == "Character name *"
    assert editor.accessibleName() == "Character name"
    assert editor.accessibleDescription() == "The name shown to readers."
    assert editor.focusPolicy() != 0
    assert button.focusPolicy() != 0
    assert not widget.styleSheet()
    widget.close()


def test_text_is_committed_on_editing_finished_not_each_keystroke():
    controller = StaticUiController(document())
    widget = DeclarativeUiWidget(controller, "settings")
    widget.show()
    wait_until(lambda: widget.document is not None)
    editor = widget.controls["name"]

    editor.setText("Mara Vale")
    qApp.processEvents()
    assert controller.document.revision == 0
    editor.editingFinished.emit()
    wait_until(lambda: controller.document.revision == 1)

    assert controller.document.controls[0].value == "Mara Vale"
    widget.close()


def test_renderer_uses_application_palette_with_legible_base_text():
    widget = DeclarativeUiWidget(
        StaticUiController(document()), "settings"
    )
    widget.show()
    wait_until(lambda: widget.document is not None)
    palette = widget.controls["name"].palette()
    text = palette.color(QPalette.Text)
    base = palette.color(QPalette.Base)

    assert _contrast(text, base) >= 4.5
    widget.close()


def test_collections_validation_and_reordering_use_native_widgets():
    collections = UiDocument("example.collections", 0, (
        UiControl(
            "list",
            UiControlKind.LIST,
            "Scenes",
            items=(UiItem("one", "One"), UiItem("two", "Two")),
            reorderable=True,
        ),
        UiControl(
            "table",
            UiControlKind.TABLE,
            "Facts",
            columns=(UiColumn("fact", "Fact"),),
            items=(UiItem("fact-one", cells={"fact": "Known"}),),
        ),
        UiControl(
            "tree",
            UiControlKind.TREE,
            "Outline",
            items=(UiItem("root", "Root", children=(
                UiItem("child", "Child"),
            )),),
            reorderable=True,
        ),
        UiControl(
            "invalid",
            UiControlKind.TEXT,
            "Required value",
            error="Enter a value.",
        ),
    ))
    widget = DeclarativeUiWidget(
        StaticUiController(collections), "project"
    )
    widget.show()
    wait_until(lambda: widget.document is not None)

    assert isinstance(widget.controls["list"], QListWidget)
    assert isinstance(widget.controls["table"], QTableWidget)
    assert isinstance(widget.controls["tree"], QTreeWidget)
    assert widget.controls["list"].dragDropMode() == (
        QAbstractItemView.InternalMove
    )
    assert widget.controls["tree"].dragDropMode() == (
        QAbstractItemView.InternalMove
    )
    assert "Error: Enter a value." in (
        widget.controls["invalid"].accessibleDescription()
    )
    widget.close()


def _contrast(first, second):
    def luminance(color):
        values = []
        for component in (color.redF(), color.greenF(), color.blueF()):
            values.append(
                component / 12.92
                if component <= 0.03928
                else ((component + 0.055) / 1.055) ** 2.4
            )
        return (
            0.2126 * values[0]
            + 0.7152 * values[1]
            + 0.0722 * values[2]
        )

    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)
