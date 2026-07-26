import zipfile

from manuskript.load_save.project_files import Version1ProjectFiles


def test_directory_project_files_round_trip_text_and_binary(tmp_path):
    project = tmp_path / "story.msk"
    cache = {}
    access = Version1ProjectFiles()
    files = [
        ("infos.txt", "Title: Story"),
        ("world.opml", b"<opml/>"),
        ("outline/chapter/scene.md", "Once upon a time"),
    ]

    result = access.write(
        str(project),
        zipped=False,
        files=files,
        moves=[],
        cache=cache,
    )
    loaded = access.read(str(project), zipped=False)

    assert result.succeeded
    assert project.read_text(encoding="utf-8") == "1"
    assert loaded.files == dict(files)
    assert loaded.unreadable_files == ()
    assert cache == dict(files)


def test_directory_project_files_move_and_remove_cached_paths(tmp_path):
    project = tmp_path / "story.msk"
    root = tmp_path / "story"
    old = root / "characters" / "old.txt"
    stale = root / "stale.txt"
    old.parent.mkdir(parents=True)
    old.write_text("character", encoding="utf-8")
    stale.write_text("stale", encoding="utf-8")
    cache = {
        "characters/old.txt": "character",
        "stale.txt": "stale",
    }

    result = Version1ProjectFiles().write(
        str(project),
        zipped=False,
        files=[("characters/new.txt", "character")],
        moves=[("characters/old.txt", "characters/new.txt")],
        cache=cache,
    )

    assert result.succeeded
    assert not old.exists()
    assert (root / "characters" / "new.txt").exists()
    assert not stale.exists()
    assert cache == {"characters/new.txt": "character"}


def test_zip_project_files_round_trip(tmp_path):
    project = tmp_path / "story.msk"
    access = Version1ProjectFiles()
    files = [
        ("MANUSKRIPT", "1"),
        ("world.opml", b"<opml/>"),
    ]

    result = access.write(
        str(project),
        zipped=True,
        files=files,
        moves=[],
        cache={},
    )
    loaded = access.read(str(project), zipped=True)

    assert result.succeeded
    assert zipfile.is_zipfile(project)
    assert loaded.files == dict(files)


def test_directory_reader_skips_hidden_files_and_directories(tmp_path):
    project = tmp_path / "story.msk"
    root = tmp_path / "story"
    root.mkdir()
    (root / "visible.txt").write_text("visible", encoding="utf-8")
    (root / ".hidden.txt").write_text("hidden", encoding="utf-8")
    hidden_directory = root / ".hidden"
    hidden_directory.mkdir()
    (hidden_directory / "secret.txt").write_text(
        "secret",
        encoding="utf-8",
    )

    result = Version1ProjectFiles().read(
        str(project),
        zipped=False,
    )

    assert result.files == {"visible.txt": "visible"}


def test_directory_writer_rejects_paths_outside_project_root(tmp_path):
    project = tmp_path / "story.msk"
    escaped = tmp_path / "escaped.txt"

    result = Version1ProjectFiles().write(
        str(project),
        zipped=False,
        files=[("../escaped.txt", "unsafe")],
        moves=[],
        cache={},
    )

    assert not result.succeeded
    assert not escaped.exists()


def test_stale_cache_cannot_remove_paths_outside_project_root(
    tmp_path,
):
    project = tmp_path / "story.msk"
    protected = tmp_path / "protected.txt"
    protected.write_text("keep", encoding="utf-8")

    result = Version1ProjectFiles().write(
        str(project),
        zipped=False,
        files=[],
        moves=[],
        cache={"../protected.txt": "keep"},
    )

    assert not result.succeeded
    assert protected.read_text(encoding="utf-8") == "keep"
