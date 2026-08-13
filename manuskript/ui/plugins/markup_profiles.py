import logging

from PyQt5.QtCore import QObject, pyqtSignal

from manuskript.plugins.api import MarkupMode
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)


LOGGER = logging.getLogger(__name__)
MARKDOWN_BASE_ID = "markdown"


class MarkupProfileService(QObject):
    """Resolve live registry contributions into editor-local profiles."""

    profilesChanged = pyqtSignal()

    def __init__(self, registry, report_error=None, parent=None):
        super().__init__(parent)
        self.registry = registry
        self._report_error = report_error or (
            lambda _message, _duration=5000, _importance=2: None
        )

    def refresh(self):
        self.profilesChanged.emit()

    def create_state(self, parent=None):
        return MarkupProfileState(self, parent=parent)

    def replacements(self):
        return {
            contribution.descriptor.id: contribution
            for contribution in self._contributions()
            if contribution.mode is MarkupMode.REPLACE
        }

    def augmentations(self):
        return {
            contribution.descriptor.id: contribution
            for contribution in self._contributions()
            if contribution.mode is MarkupMode.AUGMENT
        }

    def _contributions(self):
        return tuple(self.registry.markup) + tuple(
            self.registry.native_markup
        )

    def compatible_augmentations(self, base_id):
        return {
            contribution_id: contribution
            for contribution_id, contribution
            in self.augmentations().items()
            if base_id in contribution.base_ids
        }

    def report_error(self, contribution, error):
        message = "Editor plugin {} failed: {}: {}".format(
            contribution.descriptor.name,
            type(error).__name__,
            error,
        )
        LOGGER.exception(message)
        self._report_error(message, 8000, 2)


class MarkupProfileState(QObject):
    """Markup language selection owned by one editor leaf."""

    changed = pyqtSignal()

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self._base_id = MARKDOWN_BASE_ID
        self._additive_ids = ()
        service.profilesChanged.connect(self._registry_changed)

    @property
    def base_id(self):
        return self._base_id

    @property
    def additive_ids(self):
        return self._additive_ids

    @property
    def base_contribution(self):
        return self.service.replacements().get(self._base_id)

    @property
    def additive_contributions(self):
        available = self.service.compatible_augmentations(
            self._base_id
        )
        return tuple(
            available[contribution_id]
            for contribution_id in self._additive_ids
            if contribution_id in available
        )

    @property
    def allowed_presentation_modes(self):
        if self._base_id == MARKDOWN_BASE_ID:
            return tuple(MarkdownPresentationMode)
        return (
            MarkdownPresentationMode.SOURCE,
            MarkdownPresentationMode.FORMATTED_SOURCE,
        )

    def set_base(self, base_id):
        base_id = str(base_id)
        if (
            base_id != MARKDOWN_BASE_ID
            and base_id not in self.service.replacements()
        ):
            base_id = MARKDOWN_BASE_ID
        compatible = self.service.compatible_augmentations(base_id)
        additive_ids = tuple(
            value
            for value in self._additive_ids
            if value in compatible
        )
        if (
            base_id == self._base_id
            and additive_ids == self._additive_ids
        ):
            return
        self._base_id = base_id
        self._additive_ids = additive_ids
        self.changed.emit()

    def set_additive(self, contribution_id, enabled):
        contribution_id = str(contribution_id)
        compatible = self.service.compatible_augmentations(
            self._base_id
        )
        values = list(self._additive_ids)
        if enabled and contribution_id in compatible:
            if contribution_id not in values:
                values.append(contribution_id)
        else:
            values = [
                value
                for value in values
                if value != contribution_id
            ]
        updated = tuple(values)
        if updated == self._additive_ids:
            return
        self._additive_ids = updated
        self.changed.emit()

    def copy_selection_from(self, other):
        self._base_id = other.base_id
        self._additive_ids = tuple(other.additive_ids)
        self._registry_changed(force=True)

    def _registry_changed(self, force=False):
        base_id = self._base_id
        if (
            base_id != MARKDOWN_BASE_ID
            and base_id not in self.service.replacements()
        ):
            base_id = MARKDOWN_BASE_ID
        compatible = self.service.compatible_augmentations(base_id)
        additive_ids = tuple(
            value
            for value in self._additive_ids
            if value in compatible
        )
        changed = (
            base_id != self._base_id
            or additive_ids != self._additive_ids
        )
        self._base_id = base_id
        self._additive_ids = additive_ids
        if changed or force:
            self.changed.emit()
