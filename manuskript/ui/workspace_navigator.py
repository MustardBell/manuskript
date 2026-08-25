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
    #: Selecting this row is an explicit construction command, not ordinary
    #: navigation. Kept on the target rather than inferred from absence:
    #: sparse workspaces must not acquire every missing surface, while Editor
    #: deliberately offers another independent editing view.
    creates_surface: bool = False

    def __post_init__(self):
        if (self.page is None) == (not self.panel_id):
            raise ValueError(
                "A navigator row opens either a page or a panel: "
                "got page={!r} panel_id={!r}.".format(
                    self.page, self.panel_id
                )
            )
        if self.creates_surface and not self.panel_id:
            raise ValueError(
                "Only a surface target can construct a surface."
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
    def compose(cls, pages=(), surfaces=(), launchers=()):
        """Rows from this window's pages, surfaces, and explicit commands.

        ``pages`` are ``NavigatorTarget``s the window states itself.
        ``surfaces`` are workspace surfaces -- the places the writer goes.
        ``launchers`` are visibly declared construction commands. They are
        not synthesized from every surface the application knows, and an
        owned surface replaces a launcher with its ordinary activation row.

        It used to take every panel and pick out the ones with a navigator
        entry, reaching for the field with ``getattr`` and accepting its
        absence. That made this the last place deciding what kind of thing
        it was holding by looking at a field, which is exactly what the two
        descriptor types exist to stop. A surface may still leave its entry
        unset and take no row; nothing else can take one at all.
        """

        targets = list(pages)
        for descriptor in surfaces:
            entry = descriptor.navigator
            if entry is None:
                continue
            targets.append(NavigatorTarget(
                label=entry.label,
                icon=entry.icon,
                order=entry.order,
                panel_id=descriptor.id,
            ))
        held_ids = {descriptor.id for descriptor in surfaces}
        targets.extend(
            launcher
            for launcher in launchers
            if launcher.panel_id not in held_ids
        )
        return cls(targets)
