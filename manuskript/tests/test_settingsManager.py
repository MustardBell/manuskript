import unittest
from manuskript.settingsManager import SettingsManager


class TestSettingsManager(unittest.TestCase):
    
    def test_singleton_behavior(self):
        """Test that SettingsManager is a proper singleton."""
        s1 = SettingsManager()
        s2 = SettingsManager()
        
        # Should be the same instance
        self.assertIs(s1, s2)
        self.assertEqual(id(s1), id(s2))
    
    def test_singleton_state_persistence(self):
        """Test that settings persist across multiple SettingsManager() calls."""
        # Get first instance and modify a setting
        s1 = SettingsManager()
        original_value = s1.spellcheck
        s1.spellcheck = not original_value  # Toggle the boolean
        
        # Get second instance and check the change persisted
        s2 = SettingsManager()
        self.assertEqual(s2.spellcheck, not original_value)
        self.assertIs(s1, s2)
        
        # Reset for other tests
        s1.spellcheck = original_value
    
    def test_load_save_persistence(self):
        """Test that loaded settings persist and can be saved correctly."""
        import json
        
        # Create test settings JSON
        test_settings = {
            "spellcheck": True,
            "corkSizeFactor": 150,
            "folderView": "outline",
            "tooltipStyle": {
                "useSystemDefaultsForTooltips": False,
                "textColor": "#123456",
                "backgroundColor": "#abcdef",
                "borderColor": "#fedcba"
            }
        }
        settings_json = json.dumps(test_settings)
        
        # Load settings into singleton
        s1 = SettingsManager()
        s1.load(settings_json)
        
        # Get new reference and verify settings persisted
        s2 = SettingsManager()
        self.assertEqual(s2.spellcheck, True)
        self.assertEqual(s2.corkSizeFactor, 150) 
        self.assertEqual(s2.folderView, "outline")
        self.assertEqual(s2.tooltipStyle["textColor"], "#123456")
        
        # Verify save returns the loaded settings
        saved_json = s2.save()
        saved_settings = json.loads(saved_json)
        self.assertEqual(saved_settings["spellcheck"], True)
        self.assertEqual(saved_settings["corkSizeFactor"], 150)
        self.assertEqual(saved_settings["folderView"], "outline")
        self.assertEqual(saved_settings["tooltipStyle"]["textColor"], "#123456")


if __name__ == '__main__':
    unittest.main()