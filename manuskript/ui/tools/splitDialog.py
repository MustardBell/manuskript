#!/usr/bin/env python
# --!-- coding: utf8 --!--
from PyQt5.QtWidgets import QInputDialog


def item_for_index(index, root_item):
    if index.isValid():
        return index.internalPointer()
    return root_item


def decode_split_mark(mark):
    return mark.replace("\\n", "\n").replace("\\t", "\t")


def split_items(indexes, root_item, mark):
    for index in indexes:
        item_for_index(index, root_item).split(mark)


class SplitDialog(QInputDialog):
    """Collect the mark used to split one or more outline items."""

    def __init__(self, parent, indexes, root_item, mark=None):
        """
        @param parent:  a QWidget, for the dialog.
        @param indexes: a list of QModelIndex in the outlineModel
        @param root_item: the project outline root for an invalid root index
        @param mark: the default split mark
        """
        QInputDialog.__init__(self, parent)

        description = self.tr("""
            <p>Split selected item(s) at the given mark.</p>

            <p>If one of the selected item is a folder, it will be applied
            recursively to <i>all</i> of it's children items.</p>

            <p>The split mark can contain following escape sequences:
                <ul>
                    <li><b><code>\\n</code></b>: line break</li>
                    <li><b><code>\\t</code></b>: tab</li>
                </ul>
            </p>

            <p><b>Mark:</b></p>
            """)

        if not mark:
            mark = "\\n---\\n"
        mark = mark.replace("\n", "\\n")
        mark = mark.replace("\t", "\\t")

        self.setLabelText(description)
        self.setTextValue(mark)

        if len(indexes) == 0:
            return
        if len(indexes) == 1:
            idx = indexes[0]
            self.setWindowTitle(
                self.tr("Split '{}'").format(
                    item_for_index(idx, root_item).title()
                )
                )
        else:
            self.setWindowTitle(self.tr("Split items"))


def open_split_dialog(
        parent, indexes, root_item, mark=None, dialog_type=SplitDialog):
    """Collect a split mark and apply it to the requested outline items."""
    if not indexes:
        return False

    dialog = dialog_type(parent, indexes, root_item, mark)
    if not dialog.exec():
        return False

    mark = dialog.textValue()
    if not mark:
        return False

    split_items(indexes, root_item, decode_split_mark(mark))
    return True
