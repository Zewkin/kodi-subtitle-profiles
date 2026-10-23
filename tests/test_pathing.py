import unittest

from subtitle_profiles.pathing import directory_for, directory_matches, is_stable_media_path, normalize_path


class PathingTests(unittest.TestCase):
    def test_credentials_are_removed(self):
        self.assertEqual(
            normalize_path("smb://user:secret@NAS/Movies/Dune/movie.mkv"),
            "smb://nas/Movies/Dune/movie.mkv",
        )

    def test_directory_boundary(self):
        self.assertTrue(directory_matches("/Movies/Dune/movie.mkv", "/Movies/", True))
        self.assertFalse(directory_matches("/Movies2/Dune/movie.mkv", "/Movies/", True))
        self.assertFalse(directory_matches("/Movies/Dune/movie.mkv", "/Movies/", False))
        self.assertTrue(directory_matches("/Movies/movie.mkv", "/Movies/", False))

    def test_network_directory(self):
        self.assertEqual(directory_for("nfs://10.0.0.2/media/TV/Show/e01.mkv"), "nfs://10.0.0.2/media/TV/Show/")

    def test_unstable_streams(self):
        self.assertFalse(is_stable_media_path("plugin://example/play/123"))
        self.assertTrue(is_stable_media_path("smb://nas/share/movie.mkv"))


if __name__ == "__main__":
    unittest.main()
