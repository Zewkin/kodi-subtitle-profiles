import unittest

from subtitle_profiles.model import choose_apple_font, effective_kodi_values, merge_properties, property_diff


class ModelTests(unittest.TestCase):
    def test_merge_is_non_destructive(self):
        base = {"font_size": 36, "text_opacity": 50}
        modified = merge_properties(base, {"text_opacity": 65, "vertical_offset_px": 20})
        self.assertEqual(base, {"font_size": 36, "text_opacity": 50})
        self.assertEqual(modified["text_opacity"], 65)
        self.assertEqual(property_diff(base, modified), {"text_opacity": 65, "vertical_offset_px": 20})

    def test_vertical_offset_is_deterministic_margin(self):
        values = effective_kodi_values({"margin_vertical": 5.0, "vertical_offset_px": 54}, 1080)
        self.assertEqual(values["subtitles.marginvertical"], 10.0)
        values_again = effective_kodi_values({"margin_vertical": 5.0, "vertical_offset_px": 54}, 1080)
        self.assertEqual(values, values_again)

    def test_apple_font_preference(self):
        self.assertEqual(choose_apple_font(["DEFAULT", "Nimbus Sans", "SF Pro Display"]), "SF Pro Display")
        self.assertEqual(choose_apple_font(["DEFAULT", "Nimbus Sans"]), "Nimbus Sans")


if __name__ == "__main__":
    unittest.main()
