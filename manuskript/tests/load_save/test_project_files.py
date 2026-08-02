import os
import stat
import zipfile

import pytest

from manuskript.load_save.project_files import Version1ProjectFiles

# chmod on Windows only honours the read-only bit, so a POSIX mode cannot
# be set or read back there. The behaviour under test is POSIX-specific;
# what matters on Windows is that it stays a harmless no-op, covered below.
posix_only = pytest.mark.skipif(
    os.name != "posix", reason="POSIX file modes"
)


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


@posix_only
def test_permissions_survive_a_file_being_removed_and_written_again(
        tmp_path):
    """An undone deletion must not silently reset a file's mode.

    Manuskript rewrites the whole project on save, so a restored item is a
    brand new file. Left alone it lands with the default umask, which turns
    one undo into a pile of spurious mode changes in a versioned project.
    """
    project = tmp_path / "story.msk"
    cache = {}
    access = Version1ProjectFiles()
    scene = ("outline/chapter/scene.md", "Once upon a time")
    access.write(
        str(project), zipped=False, files=[scene], moves=[], cache=cache)

    on_disk = tmp_path / "story" / "outline" / "chapter" / "scene.md"
    os.chmod(on_disk, 0o755)
    assert stat.S_IMODE(on_disk.stat().st_mode) == 0o755

    # Delete it the way removing an outline item does.
    access.write(
        str(project), zipped=False, files=[], moves=[], cache=cache)
    assert not on_disk.exists()

    # Undo puts the item back; the next save writes the file again.
    access.write(
        str(project), zipped=False, files=[scene], moves=[], cache=cache)

    assert on_disk.exists()
    assert on_disk.read_text(encoding="utf-8") == scene[1]
    assert stat.S_IMODE(on_disk.stat().st_mode) == 0o755


@posix_only
def test_rewriting_an_existing_file_keeps_its_permissions(tmp_path):
    project = tmp_path / "story.msk"
    cache = {}
    access = Version1ProjectFiles()
    access.write(
        str(project), zipped=False,
        files=[("infos.txt", "before")], moves=[], cache=cache)
    on_disk = tmp_path / "story" / "infos.txt"
    os.chmod(on_disk, 0o600)

    access.write(
        str(project), zipped=False,
        files=[("infos.txt", "after")], moves=[], cache=cache)

    assert on_disk.read_text(encoding="utf-8") == "after"
    assert stat.S_IMODE(on_disk.stat().st_mode) == 0o600


def test_a_removed_file_is_restored_intact_on_every_platform(tmp_path):
    """The delete-then-restore round trip itself, without POSIX modes.

    Windows cannot express an executable bit, so preserving permissions is
    a no-op there. Restoring the file at all must still work, and must not
    raise from the permission handling.
    """
    project = tmp_path / "story.msk"
    cache = {}
    access = Version1ProjectFiles()
    scene = ("outline/chapter/scene.md", "Once upon a time")

    access.write(
        str(project), zipped=False, files=[scene], moves=[], cache=cache)
    on_disk = tmp_path / "story" / "outline" / "chapter" / "scene.md"
    assert on_disk.exists()

    access.write(
        str(project), zipped=False, files=[], moves=[], cache=cache)
    assert not on_disk.exists()

    result = access.write(
        str(project), zipped=False, files=[scene], moves=[], cache=cache)

    assert result.succeeded
    assert on_disk.read_text(encoding="utf-8") == scene[1]
