"""Settings stored in old projects must survive a key changing shape."""

import json
import logging

from manuskript.settings_migrations import (
    SETTINGS_VERSION,
    VERSION_KEY,
    upgrade,
)
from manuskript.settingsManager import SettingsManager


PLAIN = "manuskript.card.plain"
RULED = "manuskript.card.ruled"


def test_absent_marker_is_treated_as_version_zero():
    # Every project written before versioning existed looks like this.
    upgraded = upgrade({"corkStyle": "old"})

    assert upgraded[VERSION_KEY] == SETTINGS_VERSION
    assert upgraded["indexCardStyle"] == RULED
    assert "corkStyle" not in upgraded


def test_legacy_cork_styles_map_to_card_ids():
    assert upgrade({"corkStyle": "old"})["indexCardStyle"] == RULED
    assert upgrade({"corkStyle": "new"})["indexCardStyle"] == PLAIN


def test_missing_or_unknown_legacy_value_falls_back_to_plain():
    assert upgrade({})["indexCardStyle"] == PLAIN
    assert upgrade({"corkStyle": "chartreuse"})["indexCardStyle"] == PLAIN


def test_current_version_data_is_left_alone():
    current = {VERSION_KEY: SETTINGS_VERSION, "indexCardStyle": RULED}

    upgraded = upgrade(dict(current))

    assert upgraded == current


def test_future_version_loads_best_effort_instead_of_raising(caplog):
    future = {VERSION_KEY: SETTINGS_VERSION + 5, "indexCardStyle": RULED}

    with caplog.at_level(logging.WARNING):
        upgraded = upgrade(dict(future))

    # Refusing would make the project unopenable.
    assert upgraded["indexCardStyle"] == RULED
    assert upgraded[VERSION_KEY] == SETTINGS_VERSION + 5
    assert "understands" in caplog.text


def test_unreadable_version_marker_is_treated_as_version_zero(caplog):
    with caplog.at_level(logging.WARNING):
        upgraded = upgrade({VERSION_KEY: "banana", "corkStyle": "old"})

    assert upgraded["indexCardStyle"] == RULED
    assert upgraded[VERSION_KEY] == SETTINGS_VERSION


def test_manager_writes_the_version_without_exposing_it_as_a_setting():
    manager = SettingsManager()

    saved = json.loads(manager.save())

    assert saved[VERSION_KEY] == SETTINGS_VERSION
    assert VERSION_KEY not in SettingsManager._setting_names
    assert not hasattr(manager, VERSION_KEY)


def test_manager_round_trips_the_card_style():
    manager = SettingsManager()
    manager.indexCardStyle = RULED

    restored = SettingsManager()
    restored.load(manager.save())

    assert restored.indexCardStyle == RULED


def test_manager_upgrades_a_legacy_project_on_load():
    legacy = json.dumps({"corkStyle": "old", "spellcheck": False})
    manager = SettingsManager()

    manager.load(legacy)

    assert manager.indexCardStyle == RULED
    # And the next save writes the new vocabulary, not the old.
    saved = json.loads(manager.save())
    assert saved["indexCardStyle"] == RULED
    assert "corkStyle" not in saved
