"""Asking a saved layout which docks it still knows about.

``QMainWindow.saveState`` keeps the entry for a dock it restored but never
found, for the life of the profile. That is deliberate -- a panel whose
plugin is away comes back to its place -- and it means a layout written
while the seven work surfaces were docks carries seven names this build
never creates, forever, once it has been applied.

Those names cannot be removed. Measured, on Qt 5.15.3, four ways: giving
them real temporary docks so the restore resolves them and then letting
those docks go leaves every name still restorable, because
``removeDockWidget`` produces the same kind of placeholder an unresolved
name leaves. See ``tests/ui/test_legacy_layout_migration.py``.

They can be *detected*, exactly. That is what this module is for, and it
is what decides whether an old layout may be applied at all -- which was
previously decided by the version number stamped on it, and decided
wrongly: an installation upgrading from upstream arrives stamped version
one with a layout naming no surface docks whatsoever, because upstream's
surfaces were pages. Its reader would have lost an arrangement made over
years to protect against dead names their layout never had.

The asking happens on a window that is thrown away, because asking is
restoring: a window that performs the detection is a window the dead
names are now in.
"""

from PyQt5.QtWidgets import QDockWidget, QMainWindow


#: The object names the seven work surfaces' docks had, while they were
#: docks. Spelled out rather than derived from the descriptors: this is a
#: historical fact about layouts already written, and it has to keep
#: being true after a surface is renamed, removed, or given an object
#: name of its own. The same reason ``preferences_migrations`` spells out
#: the keys it moves.
LEGACY_SURFACE_DOCKS = (
    "panel.core.general",
    "panel.core.entities.project",
    "panel.core.entities.characters",
    "panel.core.entities.plots",
    "panel.core.entities.world",
    "panel.core.outline",
    "panel.core.editor",
)


def legacy_docks_in(blob, names=LEGACY_SURFACE_DOCKS):
    """Which of these dock names a saved layout has somewhere to put.

    Empty for a layout this build could apply without inheriting
    anything: one it wrote itself, or one an upstream installation
    brought with it.

    Answers empty for a payload that will not restore at all, rather than
    guessing at what it might have been. Whatever is wrong with it is
    about to be wrong for the real window too, which reports it by
    failing to restore.
    """

    if not blob:
        return ()
    scratch = QMainWindow()
    try:
        if not scratch.restoreState(blob):
            return ()
        found = []
        for name in names:
            candidate = QDockWidget(name, scratch)
            candidate.setObjectName(name)
            if scratch.restoreDockWidget(candidate):
                found.append(name)
            scratch.removeDockWidget(candidate)
        return tuple(found)
    finally:
        # The scratch window has the dead names in it now, which is the
        # whole reason it is not the one being restored.
        scratch.setParent(None)
        scratch.deleteLater()
