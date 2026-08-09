"""One binding per area of the interface, each given only its own views.

There was one class that bound all of them. It read twenty-one views off
one flat set, and every line of it could see every view: the search
binding and the metadata binding were the same object, so nothing but
attention kept them from using each other's widgets.

Four modules now, and the separation is in the import graph rather than in
a convention. :mod:`search` cannot name the metadata panel; it has never
heard of it. What more than one of them needs -- the reference service,
the text editor context -- belongs to the coordinator in
:mod:`manuskript.ui.project_context_binding`, which is the only thing that
knows the order.
"""

from manuskript.ui.project_contexts.editors import EditorBinding
from manuskript.ui.project_contexts.metadata import MetadataBinding
from manuskript.ui.project_contexts.reference_panels import (
    ReferencePanelBinding,
)
from manuskript.ui.project_contexts.search import SearchBinding

__all__ = [
    "EditorBinding",
    "MetadataBinding",
    "ReferencePanelBinding",
    "SearchBinding",
]
