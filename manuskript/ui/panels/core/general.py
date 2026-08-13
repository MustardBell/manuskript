"""The project-level publication and author fields."""

from PyQt5.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QVBoxLayout,
    QWidget,
)

from manuskript.ui.views.lineEditView import lineEditView


class GeneralPanel(QWidget):
    """A narrow-safe form over the legacy flat-data model."""

    FIELD_SPECS = (
        ("title", "Title", "txtGeneralTitle"),
        ("subtitle", "Subtitle", "txtGeneralSubtitle"),
        ("series", "Series", "txtGeneralSerie"),
        ("volume", "Volume", "txtGeneralVolume"),
        ("genre", "Genre", "txtGeneralGenre"),
        ("license", "License", "txtGeneralLicense"),
        ("author", "Name", "txtGeneralAuthor"),
        ("email", "Email", "txtGeneralEmail"),
    )

    def __init__(self, translate, parent=None):
        super().__init__(parent)
        self.setObjectName("generalPanel")
        self._translate = translate

        book = QGroupBox(translate("Book information"), self)
        book.setObjectName("grpBookInfos")
        book_form = QFormLayout(book)
        book_form.setContentsMargins(6, 6, 6, 6)

        author = QGroupBox(translate("Author"), self)
        author.setObjectName("grpAuthor")
        author_form = QFormLayout(author)
        author_form.setContentsMargins(6, 6, 6, 6)

        self.fields = []
        for index, (attribute, label, object_name) in enumerate(
            self.FIELD_SPECS
        ):
            editor = lineEditView(self)
            editor.setObjectName(object_name)
            setattr(self, attribute, editor)
            self.fields.append(editor)
            form = book_form if index < 6 else author_form
            form.addRow(translate(label), editor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(book)
        layout.addWidget(author)
        layout.addStretch(1)


def build_general(context, parent):
    return GeneralPanel(context.translate, parent)
