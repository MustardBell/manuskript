from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from manuskript.plugins.api import OptionKind


class PluginOptionsWidget(QWidget):
    """Generic Qt form for the serializable plugin option schema."""

    def __init__(self, fields, values, parent=None):
        super().__init__(parent)
        self.fields = tuple(fields)
        self.controls = {}
        grouped = any(field.section for field in self.fields)
        if grouped:
            layout = QVBoxLayout(self)
            section_layouts = {}
            ungrouped_layout = None
        else:
            form_layout = QFormLayout(self)
        for field in self.fields:
            if grouped:
                if field.section:
                    form_layout = section_layouts.get(field.section)
                    if form_layout is None:
                        group = QGroupBox(field.section, self)
                        form_layout = QFormLayout(group)
                        section_layouts[field.section] = form_layout
                        layout.addWidget(group)
                else:
                    if ungrouped_layout is None:
                        ungrouped = QWidget(self)
                        ungrouped_layout = QFormLayout(ungrouped)
                        layout.addWidget(ungrouped)
                    form_layout = ungrouped_layout
            control = self._control(field, values.get(field.key))
            control.setToolTip(field.description)
            self.controls[field.key] = control
            form_layout.addRow(field.label, control)
        if grouped:
            layout.addStretch(1)

    def values(self):
        values = {}
        for field in self.fields:
            control = self.controls[field.key]
            if field.kind is OptionKind.BOOLEAN:
                value = control.isChecked()
            elif field.kind is OptionKind.INTEGER:
                value = control.value()
            elif field.kind is OptionKind.NUMBER:
                value = control.value()
            elif field.kind is OptionKind.CHOICE:
                value = control.currentData()
            else:
                value = control.text()
            values[field.key] = value
        return values

    @staticmethod
    def _control(field, value):
        if field.kind is OptionKind.BOOLEAN:
            control = QCheckBox()
            control.setChecked(bool(value))
            return control
        if field.kind is OptionKind.INTEGER:
            control = QSpinBox()
            control.setRange(
                int(field.minimum if field.minimum is not None else -999999),
                int(field.maximum if field.maximum is not None else 999999),
            )
            control.setValue(int(value or 0))
            return control
        if field.kind is OptionKind.NUMBER:
            control = QDoubleSpinBox()
            control.setRange(
                float(
                    field.minimum
                    if field.minimum is not None
                    else -999999.0
                ),
                float(
                    field.maximum
                    if field.maximum is not None
                    else 999999.0
                ),
            )
            control.setValue(float(value or 0.0))
            return control
        if field.kind is OptionKind.CHOICE:
            control = QComboBox()
            for label, choice_value in field.choices:
                control.addItem(label, choice_value)
            selected = control.findData(value)
            control.setCurrentIndex(max(0, selected))
            return control
        control = QLineEdit()
        control.setText("" if value is None else str(value))
        return control


def plugin_options_widget(contribution, option_store, parent=None):
    initial = option_store.load(
        contribution.descriptor.id,
        contribution.options,
    )
    if contribution.options_view_factory is None:
        return PluginOptionsWidget(
            contribution.options,
            initial,
            parent,
        )
    widget = contribution.options_view_factory(initial, parent)
    if not isinstance(widget, QWidget) or not callable(
        getattr(widget, "values", None)
    ):
        raise TypeError(
            "Custom plugin option views must be QWidget instances "
            "with a values() method."
        )
    return widget


class PluginOptionsDialog(QDialog):
    """Standard editor for one contribution's declared options."""

    def __init__(self, contribution, option_store, parent=None):
        super().__init__(parent)
        self.contribution = contribution
        self.option_store = option_store
        self.setWindowTitle(
            self.tr("Configure {}").format(contribution.descriptor.name)
        )
        self.resize(760, 650)
        layout = QVBoxLayout(self)
        description = QLabel(contribution.descriptor.description, self)
        description.setWordWrap(True)
        layout.addWidget(description)
        self.optionsWidget = plugin_options_widget(
            contribution,
            option_store,
            None,
        )
        self.optionsScroll = QScrollArea(self)
        self.optionsScroll.setWidgetResizable(True)
        self.optionsScroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.optionsScroll.setWidget(self.optionsWidget)
        layout.addWidget(self.optionsScroll, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        self.option_store.save(
            self.contribution.descriptor.id,
            self.optionsWidget.values(),
        )
        self.accept()
