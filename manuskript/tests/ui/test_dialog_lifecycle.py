from PyQt5.QtWidgets import QWidget

from manuskript.ui.dialog_lifecycle import NamedDialogLifecycle


def test_named_lifecycle_replaces_and_presents_dialogs():
    centered = []
    lifecycle = NamedDialogLifecycle(centered.append)
    first = QWidget()
    second = QWidget()

    assert lifecycle.replace("transfer", lambda: first) is first
    lifecycle.present(first)
    lifecycle.replace("transfer", lambda: second)

    assert first.isHidden()
    assert lifecycle.current("transfer") is second
    assert centered == [first]
    lifecycle.close_all()


def test_destroying_replaced_dialog_cannot_forget_current_dialog():
    lifecycle = NamedDialogLifecycle(lambda _dialog: None)
    first = QWidget()
    second = QWidget()

    lifecycle.register("transfer", first)
    first_token = lifecycle._tokens["transfer"]
    lifecycle.replace("transfer", lambda: second)
    # This is what the old dialog's queued destroyed signal delivers after
    # the replacement has already claimed the same role.
    lifecycle._discard("transfer", first_token)

    assert lifecycle.current("transfer") is second
    lifecycle.close_all()


def test_close_all_disconnects_late_destroyed_callbacks():
    lifecycle = NamedDialogLifecycle(lambda _dialog: None)
    dialog = QWidget()
    lifecycle.register("transfer", dialog)
    callback = lifecycle._callbacks["transfer"]

    lifecycle.close_all()

    assert lifecycle.current("transfer") is None
    # The callback is no longer retained by the native QObject and remains
    # harmless if an already queued delivery invokes it directly.
    callback()
    assert lifecycle.current("transfer") is None
