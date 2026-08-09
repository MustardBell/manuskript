"""What a panel's widget factory receives.

A panel is mounted in a window, but that does not make the window one of its
dependencies.  Factories receive the few operations that are meaningful at
construction time: translating their own labels, reporting a failure, and --
for a plugin project panel -- asking the host for that plugin's already-scoped
project context.

There is deliberately no ``window`` field.  Passing the whole window made a
panel factory a service locator: any new dependency could be acquired without
being declared, and an application-scoped descriptor could accidentally keep
the first window alive.  Compatibility aliases for old core callers are
installed after construction at the window boundary instead.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional


def _identity(text):
    return text


@dataclass(frozen=True)
class PanelContext:
    #: Translate labels owned by the panel.  Identity keeps small host tests
    #: independent of a full application translator.
    translate: Callable[[str], str] = _identity
    show_status: Optional[Callable[..., None]] = None
    #: Build the public, plugin-scoped project context for one project panel.
    #: Core panels and non-project panels receive no such authority.
    plugin_project: Optional[Callable[[str, str], Any]] = None

    def project_for_plugin(self, plugin_id, default_file=""):
        """Return one plugin's scoped project context, or refuse clearly."""
        if self.plugin_project is None:
            raise RuntimeError(
                "This panel was not opened with a plugin project context."
            )
        return self.plugin_project(str(plugin_id), str(default_file))
