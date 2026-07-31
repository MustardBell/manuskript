#!/usr/bin/env python
# --!-- coding: utf8 --!--
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QCheckBox, QLabel, QMessageBox, QWidget
from PyQt5.QtGui import QIntValidator

from manuskript.enums import Outline
from manuskript.ui.views.propertiesView_ui import Ui_propertiesView
from manuskript.models.characterPOVModel import characterPOVModel

import logging
LOGGER = logging.getLogger(__name__)

class propertiesView(QWidget, Ui_propertiesView):
    def __init__(self, parent=None):
        QWidget.__init__(self)
        self.setupUi(self)
        self.txtGoal.setColumn(Outline.setGoal)
        self._pageTypes = None
        self._pluginPropertyRows = []
        self._currentPropertyItems = ()
        self._syncingPluginProperties = False

    def setModels(
            self, mdlOutline, mdlCharacter, mdlLabels, mdlStatus,
            page_types=None):
        self.cmbPOV.setModels(characterPOVModel(mdlCharacter), mdlOutline)
        self.cmbLabel.setModels(mdlLabels, mdlOutline)
        self.cmbStatus.setModels(mdlStatus, mdlOutline)
        self.chkCompile.setModel(mdlOutline)
        self.txtTitle.setModel(mdlOutline)
        self.txtGoal.setModel(mdlOutline)
        self.txtGoal.setValidator(QIntValidator(0, 9999999))
        self.setPageTypeService(page_types)

    def setPageTypeService(self, service):
        if self._pageTypes is service:
            return
        if self._pageTypes is not None:
            try:
                self._pageTypes.contributionsChanged.disconnect(
                    self._rebuildPluginProperties
                )
            except (RuntimeError, TypeError):
                pass
        self._pageTypes = service
        if service is not None:
            service.contributionsChanged.connect(
                self._rebuildPluginProperties
            )
        self._rebuildPluginProperties()

    def _rebuildPluginProperties(self):
        for label, checkbox, multi_label, multi_checkbox, _value in (
                self._pluginPropertyRows):
            for layout, widget in (
                (self.formLayout, label),
                (self.formLayout, checkbox),
                (self.formLayout_2, multi_label),
                (self.formLayout_2, multi_checkbox),
            ):
                layout.removeWidget(widget)
                widget.deleteLater()
        self._pluginPropertyRows = []
        if self._pageTypes is None:
            return

        for offset, contribution in enumerate(
                self._pageTypes.contributions):
            label = QLabel(contribution.property_label, self.page)
            checkbox = QCheckBox(self.page)
            multi_label = QLabel(
                contribution.property_label,
                self.page_2,
            )
            multi_checkbox = QCheckBox(self.page_2)
            for value, suffix in (
                    (checkbox, ""),
                    (multi_checkbox, "Multi")):
                value.setObjectName(
                    "pluginProperty{}{}".format(
                        contribution.descriptor.id.replace(".", "_"),
                        suffix,
                    )
                )
                value.setToolTip(contribution.descriptor.description)
                value.stateChanged.connect(
                    lambda state, current=contribution:
                    self._pluginPropertyChanged(current, state)
                )
            self.formLayout.insertRow(3 + offset, label, checkbox)
            self.formLayout_2.insertRow(
                3 + offset,
                multi_label,
                multi_checkbox,
            )
            self._pluginPropertyRows.append((
                label,
                checkbox,
                multi_label,
                multi_checkbox,
                contribution,
            ))
        self._syncPluginProperties()

    def getIndexes(self, sourceView):
        """Returns a list of indexes from list of QItemSelectionRange"""
        indexes = []

        for i in sourceView.selection().indexes():
            if i.column() != 0:
                continue

            if i not in indexes:
                indexes.append(i)

        return indexes

    def selectionChanged(self, sourceView):

        indexes = self.getIndexes(sourceView)
        self._currentPropertyItems = tuple(
            index.internalPointer()
            for index in indexes
            if index.isValid()
        )
        # LOGGER.debug("selectionChanged indexes: %s", indexes)
        if len(indexes) == 0:
            self.setEnabled(False)

        elif len(indexes) == 1:
            self.setEnabled(True)
            self.setLabelsItalic(False)
            idx = indexes[0]
            self.cmbPOV.setCurrentModelIndex(idx)
            self.cmbLabel.setCurrentModelIndex(idx)
            self.cmbStatus.setCurrentModelIndex(idx)
            self.chkCompile.setCurrentModelIndex(idx)
            self.txtTitle.setCurrentModelIndex(idx)
            self.txtGoal.setCurrentModelIndex(idx)

        else:
            self.setEnabled(True)
            self.setLabelsItalic(True)
            self.txtTitle.setCurrentModelIndexes(indexes)
            self.txtGoal.setCurrentModelIndexes(indexes)
            self.chkCompile.setCurrentModelIndexes(indexes)
            self.cmbPOV.setCurrentModelIndexes(indexes)
            self.cmbLabel.setCurrentModelIndexes(indexes)
            self.cmbStatus.setCurrentModelIndexes(indexes)

        self._syncPluginProperties()

    def _pluginPropertyChanged(self, contribution, state):
        if (
            self._syncingPluginProperties
            or state == Qt.PartiallyChecked
            or self._pageTypes is None
        ):
            return
        enabled = state == Qt.Checked
        if enabled:
            warnings = []
            for item in self._currentPropertyItems:
                if self._pageTypes.is_enabled(item, contribution):
                    continue
                warning = self._pageTypes.activation_warning(
                    item,
                    contribution,
                )
                if warning and warning not in warnings:
                    warnings.append(warning)
            if warnings:
                answer = QMessageBox.warning(
                    self,
                    self.tr("Enable {}?").format(
                        contribution.property_label
                    ),
                    "\n\n".join(warnings),
                    QMessageBox.Yes | QMessageBox.Cancel,
                    QMessageBox.Cancel,
                )
                if answer != QMessageBox.Yes:
                    self._syncPluginProperties()
                    return
        for item in self._currentPropertyItems:
            self._pageTypes.set_enabled(
                item,
                contribution,
                enabled,
            )
        self._syncPluginProperties()

    def _syncPluginProperties(self):
        if self._pageTypes is None:
            return
        self._syncingPluginProperties = True
        try:
            multiple = len(self._currentPropertyItems) > 1
            for (
                    label, checkbox, multi_label, multi_checkbox,
                    contribution) in self._pluginPropertyRows:
                applicable = [
                    item
                    for item in self._currentPropertyItems
                    if self._pageTypes.is_applicable(item, contribution)
                ]
                values = {
                    self._pageTypes.is_enabled(item, contribution)
                    for item in applicable
                }
                state = (
                    Qt.PartiallyChecked
                    if len(values) > 1
                    else Qt.Checked
                    if values == {True}
                    else Qt.Unchecked
                )
                target = multi_checkbox if multiple else checkbox
                target.setTristate(state == Qt.PartiallyChecked)
                target.setCheckState(state)
                for widget in (
                        label, checkbox, multi_label, multi_checkbox):
                    widget.setEnabled(bool(applicable))
                label.setVisible(not multiple)
                checkbox.setVisible(not multiple)
                multi_label.setVisible(multiple)
                multi_checkbox.setVisible(multiple)
        finally:
            self._syncingPluginProperties = False

    def setLabelsItalic(self, value):
        f = self.lblPOV.font()
        f.setItalic(value)
        for lbl in [
            self.lblPOV,
            self.lblStatus,
            self.lblLabel,
            self.lblCompile,
            self.lblGoal
        ]:
            lbl.setFont(f)
