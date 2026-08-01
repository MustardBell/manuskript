import json
import unittest
from copy import deepcopy
from unittest.mock import MagicMock, patch

from manuskript import settings as default_settings
from manuskript.settingsManager import SettingsManager


class TestSettingsManager(unittest.TestCase):
    def setUp(self):
        self.settings = SettingsManager()
        with patch.object(self.settings, "apply_loaded_settings_effects"):
            self.settings.reset_to_defaults()

    def test_singleton_behavior(self):
        """Test that SettingsManager is a proper singleton."""
        s1 = SettingsManager()
        s2 = SettingsManager()
        
        # Should be the same instance
        self.assertIs(s1, s2)
        self.assertEqual(id(s1), id(s2))
    
    def test_singleton_state_persistence(self):
        """Test that settings persist across multiple SettingsManager() calls."""
        s1 = SettingsManager()
        original_value = s1.spellcheck
        s1.spellcheck = not original_value

        s2 = SettingsManager()
        self.assertEqual(s2.spellcheck, not original_value)
        self.assertIs(s1, s2)

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

        s1 = SettingsManager()
        with patch.object(s1, "apply_loaded_settings_effects"):
            s1.load(settings_json)

        s2 = SettingsManager()
        self.assertTrue(s2.spellcheck)
        self.assertEqual(s2.corkSizeFactor, 150)
        self.assertEqual(s2.folderView, "outline")
        self.assertEqual(s2.tooltipStyle["textColor"], "#123456")

        saved_json = s2.save()
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

        s2 = SettingsManager()
        self.assertEqual(s2.spellcheck, default_settings.spellcheck)
        self.assertEqual(s2.corkSizeFactor, default_settings.corkSizeFactor)
        self.assertEqual(s2.folderView, default_settings.folderView)
        self.assertEqual(s2.viewSettings, default_settings.viewSettings)
        self.assertEqual(s2.revisions, default_settings.revisions)

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


if __name__ == '__main__':
    unittest.main()
