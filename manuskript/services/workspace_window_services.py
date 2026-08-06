"""What a workspace window is given, composed once for the application.

A window is one view of things it does not own: the project, the list of
panels that exist, what the plugins contribute, which windows are
workspaces. Every one of those is application- or project-scope, and every
window must see the same instance or they are not views of one thing.

They used to arrive as ten optional arguments, each with a fallback --
``panel_registry if panel_registry is not None else PanelRegistry()`` and
so on. Two things followed from that, and both are why this exists.

A window given nothing composed a whole second application quietly: its
own panel registry, its own preferences, its own project. Nothing raised;
the window worked; it simply was not looking at the same application as
its neighbour. And opening a second window meant re-listing all ten
arguments at the other construction site, so adding an application-scope
service and forgetting that second list produced exactly that silent
second graph, in the one place hardest to notice it.

One object, passed whole, fixes both: there is nothing to forget and
nothing to compose. Absent is not a state this can be in -- every field is
required, and a field that is legitimately nothing (no plugin runtime, so
nothing contributed) has to be said to be nothing.

No behaviour here on purpose. This is what the composition root hands
over, not another place to ask questions about the application.
"""

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class WorkspaceWindowServices:
    """Everything a workspace window receives rather than builds."""

    #: Preferences that are the application's, not a project's.
    application_preferences: object
    #: The plugin layer. None where plugins are not running at all.
    plugin_runtime: object
    plugin_option_store: object
    #: What the plugins contribute, and the news that it changed.
    plugin_contributions: object
    #: Every media type core and plugins know, in one registry.
    media_types: object
    media_type_preferences: object
    #: Every panel a window can show. Windows build their own copies.
    panel_registry: object
    #: The open project, shared by every window viewing it.
    project_runtime: object
    #: Which windows are workspaces, and where commands go.
    window_registry: object

    @classmethod
    def field_names(cls):
        """The services by name, for anything that must cover all of them.

        A list that derives itself, so a service added here cannot be
        missed by whatever checks that two windows share them.
        """
        return tuple(field.name for field in fields(cls))
