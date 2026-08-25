"""Safety properties of the test process itself."""

from pathlib import Path

from PyQt5.QtCore import QSettings

from manuskript.tests import _settings_root


def test_qsettings_cannot_reach_the_developers_real_profile():
    settings = QSettings("manuskript_tests", "settings-safety-probe")
    filename = Path(settings.fileName()).resolve()

    assert _settings_root.resolve() in filename.parents
