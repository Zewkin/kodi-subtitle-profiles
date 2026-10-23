import os
import tempfile
import unittest

from subtitle_profiles.model import merge_properties, property_diff
from subtitle_profiles.storage import Storage


DEFAULT = {
    "font": "DEFAULT",
    "font_size": 42,
    "text_opacity": 100,
    "background_opacity": 80,
    "vertical_offset_px": 0,
}


class StorageScenarios(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp.name, "profiles.db")
        self.store = Storage(self.db_path)
        self.store.initialize_defaults(DEFAULT, "Nimbus Sans")

    def tearDown(self):
        self.temp.cleanup()

    def preset(self, name):
        return next(item for item in self.store.list_presets() if item.name == name)

    def test_scenario_a_modified_preset_saved_as_new(self):
        apple = self.preset("Apple TV")
        modified = merge_properties(apple.properties, {"vertical_offset_px": 20})
        lower = self.store.create_preset("Apple TV Lower", modified)
        self.assertEqual(self.store.get_preset(apple.id).properties["vertical_offset_px"], 0)
        self.assertEqual(lower.properties["vertical_offset_px"], 20)

    def test_scenario_b_directory_customization_without_new_preset(self):
        apple = self.preset("Apple TV")
        custom = merge_properties(apple.properties, {"background_opacity": 65, "vertical_offset_px": 20})
        self.store.set_assignment(
            "directory", "/Movies/", True, apple.id, property_diff(apple.properties, custom)
        )
        result = self.store.resolve("/Movies/Dune/movie.mkv")
        self.assertEqual(result.preset.id, apple.id)
        self.assertEqual(result.properties["background_opacity"], 65)
        self.assertEqual(len(self.store.list_presets()), 2)

    def test_scenario_c_file_override(self):
        apple = self.preset("Apple TV")
        cinema = self.store.create_preset("Cinema", {**DEFAULT, "font_size": 50})
        self.store.set_assignment("directory", "/Movies/", True, apple.id)
        self.store.set_assignment("file", "/Movies/Dune/movie.mkv", preset_id=cinema.id)
        self.assertEqual(self.store.resolve("/Movies/Dune/movie.mkv").preset.name, "Cinema")
        self.assertEqual(self.store.resolve("/Movies/Arrival/movie.mkv").preset.name, "Apple TV")

    def test_scenario_d_restart_persistence(self):
        apple = self.preset("Apple TV")
        self.store.set_assignment("directory", "nfs://host/media/TV/", True, apple.id)
        reopened = Storage(self.db_path)
        self.assertEqual(reopened.resolve("nfs://host/media/TV/Dark/e01.mkv").preset.name, "Apple TV")

    def test_scenario_e_video_switch_does_not_leak(self):
        apple = self.preset("Apple TV")
        custom = merge_properties(apple.properties, {"vertical_offset_px": 120})
        self.store.set_assignment("file", "/TV/Offset/e01.mkv", preset_id=apple.id, overrides=property_diff(apple.properties, custom))
        first = self.store.resolve("/TV/Offset/e01.mkv")
        second = self.store.resolve("/TV/Other/e02.mkv")
        self.assertEqual(first.properties["vertical_offset_px"], 120)
        self.assertEqual(second.properties["vertical_offset_px"], 0)

    def test_scenario_f_linked_preset_update_preserves_overrides(self):
        apple = self.preset("Apple TV")
        self.store.set_assignment("directory", "/Movies/", True, apple.id, {"background_opacity": 65})
        changed = dict(apple.properties)
        changed["font_size"] = 40
        self.store.update_preset(apple.id, changed)
        result = self.store.resolve("/Movies/a.mkv")
        self.assertEqual(result.properties["font_size"], 40)
        self.assertEqual(result.properties["background_opacity"], 65)

    def test_scenario_g_remove_file_assignment_inherits_parent(self):
        apple = self.preset("Apple TV")
        cinema = self.store.create_preset("Cinema", {**DEFAULT, "font_size": 50})
        self.store.set_assignment("directory", "/Movies/", True, apple.id)
        assignment = self.store.set_assignment("file", "/Movies/a.mkv", preset_id=cinema.id)
        self.store.remove_assignment(assignment.id)
        self.assertEqual(self.store.resolve("/Movies/a.mkv").preset.name, "Apple TV")

    def test_most_specific_directory_wins(self):
        apple = self.preset("Apple TV")
        cinema = self.store.create_preset("Cinema", {**DEFAULT, "font_size": 50})
        self.store.set_assignment("directory", "/Movies/", True, cinema.id)
        self.store.set_assignment("directory", "/Movies/Sci-Fi/", True, apple.id)
        self.assertEqual(self.store.resolve("/Movies/Sci-Fi/Dune/movie.mkv").preset.name, "Apple TV")

    def test_deleted_preset_detaches_assignments(self):
        custom = self.store.create_preset("Temporary", {**DEFAULT, "font_size": 60})
        assignment = self.store.set_assignment("directory", "/Temp/", True, custom.id, {"text_opacity": 50})
        self.store.delete_preset(custom.id)
        detached = self.store.get_assignment(assignment.id)
        self.assertIsNone(detached.preset_id)
        self.assertEqual(self.store.resolve("/Temp/a.mkv").properties["font_size"], 60)
        self.assertEqual(self.store.resolve("/Temp/a.mkv").properties["text_opacity"], 50)


if __name__ == "__main__":
    unittest.main()
