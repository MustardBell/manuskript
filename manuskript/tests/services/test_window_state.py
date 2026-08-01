from unittest.mock import MagicMock, call

from manuskript.services.window_state import (
    ApplicationWindowState,
    ApplicationWindowStateStore,
)


def test_window_state_store_loads_only_persisted_values():
    settings = MagicMock()
    persisted = {
        "geometry": b"geometry",
        "docks": {"navigation": True},
        "toolbar": [("group", "title", True)],
    }
    settings.contains.side_effect = persisted.__contains__
    settings.value.side_effect = persisted.__getitem__

    state = ApplicationWindowStateStore(settings).load()

    assert state.geometry == b"geometry"
    assert state.window_state is None
    assert state.docks == {"navigation": True}
    assert state.toolbar == [("group", "title", True)]


def test_window_state_store_persists_complete_snapshot():
    settings = MagicMock()
    store = ApplicationWindowStateStore(settings)
    state = ApplicationWindowState(
        geometry=b"geometry",
        window_state=b"window",
        docks={"navigation": False},
        metadata=[True, False],
        revisions=[False],
        redaction_horizontal=b"horizontal",
        redaction_vertical=b"vertical",
        toolbar=[("group", "title", True)],
    )

    store.save(state)

    assert settings.setValue.call_args_list == [
        call("geometry", b"geometry"),
        call("windowState", b"window"),
        call("docks", {"navigation": False}),
        call("metadataState", [True, False]),
        call("revisionsState", [False]),
        call("splitterRedacH", b"horizontal"),
        call("splitterRedacV", b"vertical"),
        call("toolbar", [("group", "title", True)]),
    ]
    settings.sync.assert_called_once_with()
