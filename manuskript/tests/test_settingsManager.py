import json
import unittest
from copy import deepcopy
from unittest.mock import MagicMock, patch

from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QToolTip, qApp

from manuskript import settings as default_settings
from manuskript.settingsManager import SettingsManager
from manuskript.ui.tooltip_style import (
    MINIMUM_TEXT_CONTRAST,
    contrast_ratio,
)


class TestSettingsManager(unittest.TestCase):
    def setUp(self):
        self.settings = SettingsManager()
        with patch.object(self.settings, "apply_loaded_settings_effects"):
            self.settings.reset_to_defaults()

    def test_instances_have_explicit_independent_ownership(self):
        s1 = SettingsManager()
        s2 = SettingsManager()

        self.assertIsNot(s1, s2)
        self.assertEqual(s1.viewSettings, s2.viewSettings)
        self.assertIsNot(s1.viewSettings, s2.viewSettings)

    def test_instance_state_does_not_leak(self):
        s1 = SettingsManager()
        original_value = s1.spellcheck
        s1.spellcheck = not original_value

        s2 = SettingsManager()
        self.assertEqual(s2.spellcheck, original_value)
        self.assertIsNot(s1, s2)

    def test_load_save_persistence(self):
        """Test that loaded settings persist and can be saved correctly."""
        test_settings = {
            "spellcheck": True,
            "corkSizeFactor": 150,
            "folderView": "outline",
            "tooltipStyle": {
                "useSystemDefaultsForTooltips": False,
                "textColor": "#123456",
                "backgroundColor": "#abcdef",
                "borderColor": "#fedcba",
            },
        }
        settings_json = json.dumps(test_settings)

        settings = SettingsManager()
        with patch.object(settings, "apply_loaded_settings_effects"):
            settings.load(settings_json)

        self.assertTrue(settings.spellcheck)
        self.assertEqual(settings.corkSizeFactor, 150)
        self.assertEqual(settings.folderView, "outline")
        self.assertEqual(settings.tooltipStyle["textColor"], "#123456")

        saved_json = settings.save()
        saved_settings = json.loads(saved_json)
        self.assertTrue(saved_settings["spellcheck"])
        self.assertEqual(saved_settings["corkSizeFactor"], 150)
        self.assertEqual(saved_settings["folderView"], "outline")
        self.assertEqual(saved_settings["tooltipStyle"]["textColor"], "#123456")

    def test_reset_to_defaults(self):
        """Reset scalar and nested settings to pristine defaults."""
        s1 = SettingsManager()
        s1.spellcheck = not default_settings.spellcheck
        s1.corkSizeFactor = 999
        s1.folderView = "custom_test_value"
        s1.viewSettings["Tree"]["iconSize"] = 999
        s1.revisions["rules"].clear()

        with patch.object(s1, "apply_loaded_settings_effects"):
            s1.reset_to_defaults()

        self.assertEqual(s1.spellcheck, default_settings.spellcheck)
        self.assertEqual(s1.corkSizeFactor, default_settings.corkSizeFactor)
        self.assertEqual(s1.folderView, default_settings.folderView)
        self.assertEqual(s1.viewSettings, default_settings.viewSettings)
        self.assertEqual(s1.revisions, default_settings.revisions)

    def test_active_settings_do_not_mutate_defaults(self):
        """Active nested settings must not leak into the defaults module."""
        expected_view_settings = deepcopy(default_settings.viewSettings)
        expected_revisions = deepcopy(default_settings.revisions)

        self.settings.viewSettings["Tree"]["iconSize"] = 999
        self.settings.revisions["rules"].clear()

        self.assertEqual(default_settings.viewSettings, expected_view_settings)
        self.assertEqual(default_settings.revisions, expected_revisions)

    def test_load_does_not_replace_defaults(self):
        """Loading a project must not turn its settings into future defaults."""
        expected_spellcheck = default_settings.spellcheck
        expected_folder_view = default_settings.folderView

        with patch.object(self.settings, "apply_loaded_settings_effects"):
            self.settings.load(
                json.dumps({
                    "spellcheck": not expected_spellcheck,
                    "folderView": "outline",
                })
            )

        self.assertEqual(default_settings.spellcheck, expected_spellcheck)
        self.assertEqual(default_settings.folderView, expected_folder_view)

    def test_old_revision_settings_gain_backend_defaults(self):
        old_settings = {
            "revisions": {
                "keep": True,
                "smartremove": False,
                "rules": {
                    "600": 60,
                    "null": 604800,
                },
            },
        }

        with patch.object(
            self.settings,
            "apply_loaded_settings_effects",
        ):
            self.settings.load(json.dumps(old_settings))

        self.assertEqual(
            self.settings.revisions["backend"],
            "git",
        )
        self.assertFalse(
            self.settings.revisions["git"]["autoCommit"]
        )
        self.assertTrue(
            self.settings.revisions["git"]["taggedOnly"]
        )
        self.assertEqual(
            self.settings.revisions["rules"][None],
            604800,
        )

    def test_cursor_flash_time_uses_injected_platform_default(self):
        original_provider = self.settings._default_cursor_flash_time
        provider = MagicMock(return_value=875)
        self.settings.textEditor["cursorNotBlinking"] = False
        try:
            self.settings.configure_cursor_flash_time(provider)
            with patch("manuskript.settingsManager.qApp") as application:
                self.settings.applyCursorFlashTime()
        finally:
            self.settings._default_cursor_flash_time = original_provider

        provider.assert_called_once_with()
        application.setCursorFlashTime.assert_called_once_with(875)

    def test_cursor_flash_time_rejects_non_callable_default(self):
        with self.assertRaisesRegex(TypeError, "must be callable"):
            self.settings.configure_cursor_flash_time(875)

    def test_system_tooltip_style_repairs_inaccessible_palette(self):
        palette = QPalette(qApp.palette())
        palette.setColor(
            QPalette.Inactive,
            QPalette.ToolTipText,
            QColor("white"),
        )
        palette.setColor(
            QPalette.Inactive,
            QPalette.ToolTipBase,
            QColor("#ffffdc"),
        )
        self.settings.tooltipStyle[
            "useSystemDefaultsForTooltips"
        ] = True

        with patch(
            "manuskript.settingsManager.qApp"
        ) as application:
            application.palette.return_value = palette
            self.settings.applyTooltipStyle()

        repaired = QToolTip.palette()
        self.assertEqual(
            repaired.color(
                QPalette.Inactive,
                QPalette.ToolTipBase,
            ).rgba(),
            QColor("#ffffdc").rgba(),
        )
        self.assertGreaterEqual(
            contrast_ratio(
                repaired.color(
                    QPalette.Inactive,
                    QPalette.ToolTipText,
                ),
                repaired.color(
                    QPalette.Inactive,
                    QPalette.ToolTipBase,
                ),
            ),
            MINIMUM_TEXT_CONTRAST,
        )
        self.assertEqual(
            repaired.color(
                QPalette.Inactive,
                QPalette.ToolTipText,
            ).rgba(),
            QColor("black").rgba(),
        )

    def test_a_stylesheet_is_only_assigned_when_it_would_change(self):
        """Qt re-polishes every widget in the application on assignment,
        whether the sheet differs or not. Opening a project applies settings
        twice -- the defaults, then the project's own -- so the first
        assignment was superseded before anybody could see it.
        """
        self.settings.tooltipStyle[
            "useSystemDefaultsForTooltips"
        ] = False
        self.settings.tooltipStyle["textColor"] = "#123456"
        self.settings.tooltipStyle["backgroundColor"] = "#abcdef"
        self.settings.tooltipStyle["borderColor"] = "#000000"

        with patch("manuskript.settingsManager.qApp") as application:
            # What Qt already has is what it is asked for the second time.
            application.styleSheet.side_effect = ["", "#123456 sheet"]
            application.setStyleSheet.side_effect = (
                lambda sheet: application.styleSheet.configure_mock(
                    side_effect=None, return_value=sheet,
                )
            )
            self.settings.applyTooltipStyle()
            first = application.setStyleSheet.call_count
            self.settings.applyTooltipStyle()

        self.assertEqual(first, 1)
        self.assertEqual(application.setStyleSheet.call_count, 1)

    def test_the_stylesheet_is_still_assigned_when_it_differs(self):
        """The guard must not turn into a refusal to restyle."""
        self.settings.tooltipStyle[
            "useSystemDefaultsForTooltips"
        ] = False
        self.settings.tooltipStyle["textColor"] = "#123456"
        self.settings.tooltipStyle["backgroundColor"] = "#abcdef"
        self.settings.tooltipStyle["borderColor"] = "#000000"

        with patch("manuskript.settingsManager.qApp") as application:
            application.styleSheet.return_value = "something else"
            self.settings.applyTooltipStyle()

        application.setStyleSheet.assert_called_once()
        assigned = application.setStyleSheet.call_args[0][0]
        self.assertIn("#123456", assigned)
        self.assertIn("#abcdef", assigned)


if __name__ == '__main__':
    unittest.main()
