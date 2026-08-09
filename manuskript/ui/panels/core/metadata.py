"""The Metadata panel: properties, summaries, notes and revisions.

The most connected of the four workspace panels -- window state saves
its group-box collapse states, search jumps into its fields, selection
changes flow into it. All of that reaches it by attribute or by
objectName, both of which this factory preserves.
"""

from manuskript.ui.views.metadataView import metadataView


def build_metadata(context, parent):
    view = metadataView(parent)
    view.setObjectName("redacMetadata")
    return view
