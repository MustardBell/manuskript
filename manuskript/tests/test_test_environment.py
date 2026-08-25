"""Safety properties of the test process itself."""

from pathlib import Path

from PyQt5.QtCore import QSettings

from manuskript.tests import _settings_root


def test_qsettings_cannot_reach_the_developers_real_profile():
    settings = QSettings("manuskript_tests", "settings-safety-probe")
    filename = Path(settings.fileName()).resolve()

    assert settings.format() == QSettings.IniFormat
    assert _settings_root.resolve() in filename.parents


def test_scoped_native_qsettings_is_redirected_to_private_ini_storage():
    settings = QSettings(
        QSettings.NativeFormat,
        QSettings.UserScope,
        "manuskript_tests",
        "native-settings-safety-probe",
    )
    filename = Path(settings.fileName()).resolve()

    assert settings.format() == QSettings.IniFormat
    assert _settings_root.resolve() in filename.parents


def test_explicit_ini_file_settings_keep_their_requested_path(tmp_path):
    requested = tmp_path / "explicit-settings.ini"

    settings = QSettings(str(requested), QSettings.IniFormat)

    assert Path(settings.fileName()).resolve() == requested.resolve()
