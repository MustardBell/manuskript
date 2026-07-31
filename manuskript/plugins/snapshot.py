from types import MappingProxyType

from manuskript.enums import Outline
from manuskript.plugins.api import OutlineSnapshot, ProjectSnapshot


FLAT_METADATA = (
    "title",
    "subtitle",
    "series",
    "volume",
    "genre",
    "license",
    "author",
    "email",
)


def project_snapshot_from_export_context(context):
    metadata = {}
    for column, name in enumerate(FLAT_METADATA):
        item = context.flat_data_model.item(0, column)
        metadata[name] = item.text() if item is not None else ""
    return ProjectSnapshot(
        project_file=context.project_file,
        metadata=MappingProxyType(metadata),
        outline=_outline_snapshot(
            context.outline_model.rootItem,
        ),
    )


def _outline_snapshot(item):
    metadata = {}
    for field in Outline:
        if field in (Outline.text, Outline.title, Outline.type):
            continue
        value = item.data(field)
        if value not in (None, ""):
            metadata[field.name] = _portable_value(value)
    return OutlineSnapshot(
        id=str(item.ID()),
        title=str(item.title()),
        kind=str(item.type()),
        text=str(item.data(Outline.text) or ""),
        metadata=MappingProxyType(metadata),
        children=tuple(
            _outline_snapshot(item.child(row))
            for row in range(item.childCount())
        ),
    )


def _portable_value(value):
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    return str(value)
