"""The rows of a window's navigator, and what each one opens.

The navigator is the list down the left of a workspace: the places a
person goes rather than the panels that exist. It used to be built from
the main tab widget, one row per page, which meant a row could only ever
stand for a page -- so a surface that stopped being a page had to either
lose its row or keep an empty page behind it.

A row now stands for either a page or a panel, and panels ask for one by
declaring it on their descriptor. Nothing here knows which panels the
application ships, so a plugin's panel takes a row on the same terms as
a core one.
"""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class NavigatorTarget:
    """One row: what it reads as, and what it opens."""

    label: str
    icon: str = ""
    order: int = 1000
    #: The main-tab page this row switches to, when it stands for one.
    page: Optional[int] = None
    #: The panel this row reveals, when it stands for one.
    panel_id: str = ""

    def __post_init__(self):
        if (self.page is None) == (not self.panel_id):
            raise ValueError(
                "A navigator row opens either a page or a panel: "
                "got page={!r} panel_id={!r}.".format(
                    self.page, self.panel_id
                )
            )

    @property
    def opens_panel(self) -> bool:
        return bool(self.panel_id)


class WorkspaceNavigator:
    """One window's navigator rows, in the order they are read."""

    def __init__(self, targets=()):
        self._targets = tuple(
            sorted(targets, key=lambda item: (item.order, item.label))
        )

    def __len__(self):
        return len(self._targets)

    @property
    def targets(self) -> Tuple[NavigatorTarget, ...]:
        return self._targets

    def target(self, row) -> Optional[NavigatorTarget]:
        """What the row at this position opens, if anything does."""
        if 0 <= row < len(self._targets):
            return self._targets[row]
        return None

    def row_for_page(self, page) -> Optional[int]:
        """Which row stands for a page, so a page change can select it."""
        for row, target in enumerate(self._targets):
            if target.page == page:
                return row
        return None

    def row_for_panel(self, panel_id) -> Optional[int]:
        for row, target in enumerate(self._targets):
            if target.panel_id == panel_id:
                return row
        return None

    @classmethod
    def compose(cls, pages=(), descriptors=()):
        """Rows from the pages a window keeps and the panels that ask.

        ``pages`` are ``NavigatorTarget``s the window states itself.
        ``descriptors`` is every panel available; the ones declaring a
        navigator entry contribute a row.
        """
        targets = list(pages)
        for descriptor in descriptors:
            entry = getattr(descriptor, "navigator", None)
            if entry is None:
                continue
            targets.append(NavigatorTarget(
                label=entry.label,
                icon=entry.icon,
                order=entry.order,
                panel_id=descriptor.id,
            ))
        return cls(targets)
