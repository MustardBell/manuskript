"""The Story line panel: plots and texts on a timeline.

The widget class does all its own construction; the Designer file only
ever named an instance of it. The factory does the same, into the same
``splitterRedacV`` slot.
"""

from manuskript.ui.views.storylineView import storylineView


def build_storyline(context, parent):
    view = storylineView(parent)
    view.setObjectName("storylineView")
    return view
