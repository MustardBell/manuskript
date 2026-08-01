from unittest.mock import MagicMock, call

from manuskript.services.application_preferences import (
    ApplicationPreferences,
)


def test_application_preferences_expose_optional_values():
    settings = MagicMock()
    values = {
        "applicationStyle": "Fusion",
        "applicationTranslation": "manuskript_uk.qm",
        "appFontSize": "13",
        "lastExporter": "Manuskript",
        "lastExportFormat": "Markdown",
    }
    settings.contains.side_effect = values.__contains__
    settings.value.side_effect = values.__getitem__
    preferences = ApplicationPreferences(settings)

    assert preferences.style == "Fusion"
    assert preferences.translation == "manuskript_uk.qm"
    assert preferences.font_size == 13
    assert preferences.last_exporter == "Manuskript"
    assert preferences.last_export_format == "Markdown"


def test_application_preferences_distinguish_missing_from_builtin_language():
    settings = MagicMock()
    settings.contains.return_value = True
    settings.value.return_value = ""

    assert ApplicationPreferences(settings).translation == ""

    settings.contains.return_value = False
    assert ApplicationPreferences(settings).translation is None


def test_application_preferences_persist_and_sync_changes():
    settings = MagicMock()
    preferences = ApplicationPreferences(settings)

    preferences.style = "Windows"
    preferences.translation = ""
    preferences.font_size = 14
    preferences.last_exporter = "Manuskript"
    preferences.last_export_format = "HTML"

    assert settings.setValue.call_args_list == [
        call("applicationStyle", "Windows"),
        call("applicationTranslation", ""),
        call("appFontSize", 14),
        call("lastExporter", "Manuskript"),
        call("lastExportFormat", "HTML"),
    ]
    assert settings.sync.call_count == 5


def test_application_preferences_ignore_invalid_legacy_font_size():
    settings = MagicMock()
    settings.contains.return_value = True
    settings.value.return_value = "large"

    assert ApplicationPreferences(settings).font_size is None
