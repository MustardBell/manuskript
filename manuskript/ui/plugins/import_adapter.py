from manuskript.enums import Outline
from manuskript.importer.abstractImporter import abstractImporter
from manuskript.models import outlineItem
from manuskript.plugins.execution import run_import
from manuskript.ui.plugins.options import plugin_options_widget


class PluginImporterAdapter(abstractImporter):
    engine = "Plugins"

    def __init__(self, contribution, option_store):
        super().__init__()
        self.contribution = contribution
        self.option_store = option_store
        descriptor = contribution.descriptor
        self.name = descriptor.name
        self.description = descriptor.description
        self.icon = descriptor.icon
        self.fileFormat = (
            "<<folder>>"
            if contribution.source_kind == "folder"
            else contribution.file_filter
        )
        self._options_widget = None

    def isValid(self):
        return True

    def settingsWidget(self, widget):
        page = self.addPage(
            widget,
            self.tr("Plugin options"),
        )
        self._options_widget = plugin_options_widget(
            self.contribution,
            self.option_store,
            page,
        )
        page.layout().addWidget(self._options_widget)
        return widget

    def startImport(self, filePath, parentItem, settingsWidget):
        values = (
            self._options_widget.values()
            if self._options_widget is not None
            else self.option_store.load(
                self.contribution.descriptor.id,
                self.contribution.options,
            )
        )
        self.option_store.save(
            self.contribution.descriptor.id,
            values,
        )
        result = run_import(
            self.contribution,
            filePath,
            values,
        )
        items = []
        for node in result.nodes:
            items.extend(
                self._append_node(node, parentItem)
            )
        return items

    def _append_node(self, node, parent):
        item = outlineItem(
            title=node.title,
            parent=parent,
            _type=node.kind,
        )
        item.setData(Outline.text, node.text)
        for name, value in node.metadata.items():
            try:
                field = Outline[name]
            except KeyError:
                continue
            if field not in (Outline.title, Outline.type, Outline.text):
                item.setData(field, value)
        items = [item]
        for child in node.children:
            items.extend(self._append_node(child, item))
        return items


def create_plugin_importers(runtime, option_store):
    if runtime is None:
        return []
    return [
        PluginImporterAdapter(
            record.contribution,
            option_store,
        )
        for record in runtime.registry.records("importer")
    ]
