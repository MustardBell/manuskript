"""The developer tool where a user names a format Manuskript never heard of.

Declaring is the safe half: a plugin cannot know every format, so the user
can name one and then decide what stands in for it, or leave it unassigned
until something arrives that produces it.

Overriding is the sharp half. It asserts what another plugin's output really
is, and if that is wrong the export succeeds under the wrong name. Which is
why every interested party is on record: the consequence can be stated before
the user commits, rather than discovered later.
"""

import pytest
from PyQt5.QtCore import Qt

from manuskript.media_types import (
    BBCODE,
    CORE,
    HTML,
    MARKDOWN,
    PLAIN,
    PRODUCES,
    USER,
    MediaType,
    core_registry,
)
from manuskript.services.media_type_preferences import (
    InMemoryMediaTypePreferences,
)
from manuskript.ui.tools.media_type_inspector import (
    COLUMN_DECLARED,
    COLUMN_FALLBACK,
    COLUMN_ID,
    COLUMN_LABEL,
    COLUMN_PROMISES,
    UNASSIGNED,
    MediaTypeDialog,
    MediaTypeInspector,
    promise_summary,
)


FB2 = "application/x-fictionbook+xml"


def inspector(registry=None, preferences=None):
    return MediaTypeInspector(
        registry if registry is not None else core_registry(),
        preferences
        if preferences is not None
        else InMemoryMediaTypePreferences(),
    )


def row_of(subject, media_id):
    for row in range(subject.table.rowCount()):
        item = subject.table.item(row, COLUMN_ID)
        if item is not None and item.data(Qt.UserRole) == media_id:
            return row
    raise AssertionError("{} is not listed".format(media_id))


def cell(subject, media_id, column):
    return subject.table.item(row_of(subject, media_id), column)


# ------------------------------------------------------------- the listing

def test_every_declared_format_is_listed():
    registry = core_registry()
    registry.declare(MediaType(FB2, "FictionBook 2"), "vendor.fb2")

    subject = inspector(registry)

    assert cell(subject, FB2, COLUMN_LABEL).text() == "FictionBook 2"
    assert cell(subject, BBCODE, COLUMN_LABEL).text() == "BBCode"


def test_a_format_awaiting_its_attributes_says_so():
    registry = core_registry()
    registry.declare(FB2, "vendor.reader")

    subject = inspector(registry)

    assert "not named" in cell(subject, FB2, COLUMN_LABEL).text()


def test_every_declarer_is_shown():
    registry = core_registry()
    registry.declare(BBCODE, "vendor.structured-pages")

    subject = inspector(registry)

    declared = cell(subject, BBCODE, COLUMN_DECLARED).text()
    assert CORE in declared
    assert "vendor.structured-pages" in declared


def test_promises_are_summarised_per_format():
    registry = core_registry()
    registry.promise(MARKDOWN, PRODUCES, "vendor.structured-pages")

    assert promise_summary(registry, MARKDOWN) == (
        "vendor.structured-pages produce"
    )
    subject = inspector(registry)
    assert "produce" in cell(subject, MARKDOWN, COLUMN_PROMISES).text()


def test_a_format_nobody_promised_shows_nothing():
    subject = inspector()

    assert cell(subject, BBCODE, COLUMN_PROMISES).text() == ""


def test_what_stands_in_is_shown_with_the_whole_chain():
    subject = inspector()

    stands_in = cell(subject, HTML, COLUMN_FALLBACK)

    assert stands_in.text() == "Markdown"
    assert HTML in stands_in.toolTip()
    assert MARKDOWN in stands_in.toolTip()


def test_a_format_nothing_stands_in_for_is_marked():
    subject = inspector()

    assert cell(
        subject, "application/epub+zip", COLUMN_FALLBACK
    ).text() == UNASSIGNED


# -------------------------------------------------------------- declaring

def test_the_user_can_declare_a_format_and_it_persists():
    registry = core_registry()
    preferences = InMemoryMediaTypePreferences()
    subject = inspector(registry, preferences)
    declared = MediaType(FB2, "FictionBook 2", textual=False)

    registry.declare(declared, USER)
    preferences.remember_declaration(declared)
    subject.refresh()

    assert cell(subject, FB2, COLUMN_DECLARED).text() == USER
    # And it comes back next time, into a fresh registry.
    restored = preferences.apply(core_registry())
    assert restored.get(FB2).label == "FictionBook 2"
    assert restored.get(FB2).textual is False
    assert restored.declared_by(FB2) == (USER,)


def test_forgetting_a_declaration_removes_it():
    preferences = InMemoryMediaTypePreferences()
    preferences.remember_declaration(MediaType(FB2, "FictionBook 2"))
    preferences.forget_declaration(FB2)

    assert preferences.apply(core_registry()).is_known(FB2) is False


def test_declaring_twice_replaces_rather_than_duplicates():
    preferences = InMemoryMediaTypePreferences()
    preferences.remember_declaration(MediaType(FB2, "First"))
    preferences.remember_declaration(MediaType(FB2, "Second"))

    assert len(preferences.declarations()) == 1
    assert preferences.declarations()[0].label == "Second"


def test_the_declaration_dialog_refuses_an_incomplete_format():
    dialog = MediaTypeDialog(core_registry())

    dialog.identifierEdit.setText("   ")
    assert dialog.mediaType() is None
    assert "identifier" in dialog.validationError()

    # An identifier alone is not enough: the list would show a blank name.
    dialog.identifierEdit.setText(FB2)
    dialog.labelEdit.setText("")
    assert "name" in dialog.validationError()

    dialog.labelEdit.setText("FictionBook 2")
    assert dialog.validationError() == ""


def test_the_declaration_dialog_offers_declared_formats_as_a_base():
    dialog = MediaTypeDialog(core_registry())

    bases = [
        dialog.baseCombo.itemData(index)
        for index in range(dialog.baseCombo.count())
    ]

    assert "" in bases          # stands alone
    assert MARKDOWN in bases


def test_a_declared_format_round_trips_through_the_dialog():
    declared = MediaType(FB2, "FictionBook 2", base=HTML, textual=False)
    registry = core_registry()
    registry.declare(declared, USER)

    dialog = MediaTypeDialog(registry, media_type=declared)

    assert dialog.identifierEdit.isReadOnly()
    assert dialog.mediaType() == declared


# --------------------------------------------------------------- overrides

def test_an_override_is_shown_bold_with_the_original_on_hover():
    registry = core_registry()
    registry.assign_override(PLAIN, BBCODE)

    subject = inspector(registry)
    item = cell(subject, PLAIN, COLUMN_ID)

    assert item.text() == BBCODE
    assert item.font().bold() is True
    # The original is still recoverable months later.
    assert PLAIN in item.toolTip()
    assert item.data(Qt.UserRole) == PLAIN


def test_a_format_with_no_override_is_not_bold():
    subject = inspector()

    item = cell(subject, PLAIN, COLUMN_ID)

    assert item.text() == PLAIN
    assert item.font().bold() is False
    assert item.toolTip() == ""


def test_an_override_persists_and_changes_what_resolves():
    preferences = InMemoryMediaTypePreferences()
    preferences.remember_override(PLAIN, BBCODE)

    registry = preferences.apply(core_registry())

    assert registry.resolve(PLAIN) == BBCODE


def test_a_stored_override_naming_a_vanished_format_is_dropped():
    preferences = InMemoryMediaTypePreferences(overrides={PLAIN: FB2})

    registry = preferences.apply(core_registry())

    # The plugin that declared FB2 was uninstalled. Manuskript still runs.
    assert registry.resolve(PLAIN) == PLAIN


def test_declarations_load_before_the_choices_that_name_them():
    preferences = InMemoryMediaTypePreferences(
        declarations=[{"id": FB2, "label": "FictionBook 2"}],
        fallbacks={FB2: MARKDOWN},
        overrides={PLAIN: FB2},
    )

    registry = preferences.apply(core_registry())

    # A choice may name a format only the user introduced, so declarations
    # have to go in first or both would be dropped as unknown.
    assert registry.fallback(FB2) == MARKDOWN
    assert registry.resolve(PLAIN) == FB2


# ---------------------------------------------- who an override affects

def test_the_declarers_of_an_overridden_format_are_knowable():
    registry = core_registry()
    registry.declare(BBCODE, "vendor.structured-pages")
    registry.declare(BBCODE, "vendor.other")

    affected = [
        origin
        for origin in registry.declared_by(BBCODE)
        if origin not in (CORE, USER)
    ]

    # This is what declaring an interest bought: the consequence of a
    # remapping can be named before the user confirms it.
    assert affected == ["vendor.structured-pages", "vendor.other"]


# -------------------------------------------------------------- selection

def test_a_refresh_keeps_the_selected_row():
    registry = core_registry()
    subject = inspector(registry)
    subject.select(BBCODE)

    subject.refresh()

    assert subject.selected_id() == BBCODE


def test_nothing_selected_yields_no_identifier():
    subject = inspector()
    subject.table.setCurrentCell(-1, -1)

    assert subject.selected_id() == ""
