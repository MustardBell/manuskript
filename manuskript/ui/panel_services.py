"""What a feature panel needs from the application around it.

Panel controllers used to take the whole window, which made every one of
them able to reach anything: models, any widget, navigation history,
dialog parenting, translation. Two of those needs are shared by all of
them and have nothing to do with any particular panel, so they are named
here and passed in.

Neither hides a window from view for its own sake. The point is that a
controller given these can be read -- and tested -- without knowing what
else a window happens to have.
"""

from PyQt5.QtWidgets import QColorDialog, QDialog, QMessageBox


class PanelNavigation:
    """Records where the person just went, for the history.

    The two halves were always used together: push an entry, then say
    whether the selection it came from was empty, because that is what
    decides whether the entry replaces the last one or follows it.
    Separately they read as unrelated statements, and one was a private
    attribute reached across an object boundary.
    """

    def __init__(self, window):
        self._window = window

    def record(self, entry, selection_empty):
        self._window.pushHistory(entry)
        self._window._previousSelectionEmpty = selection_empty

    def note_selection(self, selection_empty):
        """Say what the selection is without recording a visit."""
        self._window._previousSelectionEmpty = selection_empty


class PanelDialogs:
    """Asks the person things, and translates what they are asked.

    A window appeared throughout the controllers as nothing more than
    something to parent a dialog to and something to call ``tr`` on.
    Naming that keeps a controller from being handed everything else a
    window can do.
    """

    def __init__(self, window):
        self._window = window

    @property
    def parent(self):
        """The widget dialogs belong to. Rarely what a caller wants."""
        return self._window

    def translate(self, text):
        return self._window.tr(text)

    def confirm(self, title, text, default_no=False):
        """Yes or no, defaulting to the safer answer where asked."""
        arguments = {}
        if default_no:
            arguments["defaultButton"] = QMessageBox.No
        return QMessageBox.warning(
            self._window,
            self.translate(title),
            self.translate(text),
            QMessageBox.Yes | QMessageBox.No,
            **arguments,
        ) == QMessageBox.Yes

    def warn(self, title, text):
        QMessageBox.warning(
            self._window,
            self.translate(title),
            self.translate(text),
        )

    def inform(self, title, text):
        QMessageBox.information(
            self._window,
            self.translate(title),
            self.translate(text),
        )

    def choose_color(self, initial):
        """A colour, or None when the person did not choose one."""
        color = QColorDialog.getColor(initial, self._window)
        return color if color.isValid() else None

    def ask_name_and_value(self):
        """A description and a value, or None if cancelled.

        The dialog is here rather than in a controller because what it
        needs from a window is only somewhere to belong.
        """
        from manuskript.ui import characterInfoDialog

        dialog = QDialog(self._window)
        fields = characterInfoDialog.Ui_characterInfoDialog()
        fields.setupUi(dialog)
        if dialog.exec_() != QDialog.Accepted:
            return None
        return (
            fields.descriptionLineEdit.text(),
            fields.valueLineEdit.text(),
        )
