from PyQt5.QtWidgets import QAction, QActionGroup, QMenu, QStyle

from manuskript.ui.editors.editorOverlayButton import (
    EditorOverlayToolButton,
    overlay_icon,
)
from manuskript.ui.plugins.markup_profiles import MARKDOWN_BASE_ID


class MarkupProfileToolButton(EditorOverlayToolButton):
    """Editor-local base markup and additive syntax selector."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.setObjectName("markupProfileToolButton")
        self.setPopupMode(self.InstantPopup)
        self.setIcon(overlay_icon(
            ("code-context", "text-x-script", "text-x-generic"),
            QStyle.SP_FileDialogListView,
        ))
        self.menu = QMenu(self)
        self.setMenu(self.menu)
        self.baseActions = {}
        self.additiveActions = {}
        self.state.changed.connect(self.rebuild)
        self.state.service.profilesChanged.connect(self.rebuild)
        self.rebuild()

    def rebuild(self):
        self.menu.clear()
        self.baseActions = {}
        self.additiveActions = {}

        base_group = QActionGroup(self)
        base_group.setExclusive(True)
        bases = [(MARKDOWN_BASE_ID, self.tr("Markdown"))]
        bases.extend(
            (
                contribution_id,
                contribution.descriptor.name,
            )
            for contribution_id, contribution in sorted(
                self.state.service.replacements().items(),
                key=lambda value: value[1].descriptor.name,
            )
        )
        for base_id, label in bases:
            action = QAction(label, self.menu)
            action.setCheckable(True)
            action.setActionGroup(base_group)
            action.setChecked(base_id == self.state.base_id)
            action.triggered.connect(
                lambda _checked=False, value=base_id:
                    self.state.set_base(value)
            )
            self.menu.addAction(action)
            self.baseActions[base_id] = action

        additions = self.state.service.compatible_augmentations(
            self.state.base_id
        )
        if additions:
            self.menu.addSeparator()
            heading = self.menu.addAction(self.tr("Add highlighting"))
            heading.setEnabled(False)
            for contribution_id, contribution in sorted(
                additions.items(),
                key=lambda value: value[1].descriptor.name,
            ):
                action = QAction(
                    contribution.descriptor.name,
                    self.menu,
                )
                action.setCheckable(True)
                action.setChecked(
                    contribution_id in self.state.additive_ids
                )
                action.toggled.connect(
                    lambda enabled, value=contribution_id:
                        self.state.set_additive(value, enabled)
                )
                self.menu.addAction(action)
                self.additiveActions[contribution_id] = action

        base = self.state.base_contribution
        base_name = (
            base.descriptor.name
            if base is not None
            else self.tr("Markdown")
        )
        additions_text = [
            value.descriptor.name
            for value in self.state.additive_contributions
        ]
        label = base_name
        if additions_text:
            label += " + " + ", ".join(additions_text)
        self.setToolTip(
            self.tr("Markup profile: {}").format(label)
        )
