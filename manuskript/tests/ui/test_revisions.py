from manuskript.ui.revisions import numberedDiff


def test_numbered_diff_tracks_replacement_line_numbers():
    entries = numberedDiff(
        ["first", "old", "third"],
        ["first", "new", "third"],
    )

    assert entries == [
        ("  ", "first", 1, 1),
        ("- ", "old", 2, 1),
        ("+ ", "new", 2, 2),
        ("  ", "third", 3, 3),
    ]


def test_numbered_diff_tracks_insertions_independently():
    entries = numberedDiff(
        ["first", "third"],
        ["first", "second", "third"],
    )

    assert entries[1] == ("+ ", "second", 1, 2)
    assert entries[2] == ("  ", "third", 2, 3)
