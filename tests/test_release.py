"""scripts/release.py: the parts that need no game files."""

import importlib.util
import pathlib
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("release", ROOT / "scripts" / "release.py")
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)


class ReadmeVersion(unittest.TestCase):
    TEXT = "Intro\nIt is an unofficial conversion, made with version 0.12 of the converter. Two\nlevels\n"

    def test_sets_version_and_windows_line_endings(self):
        out = release.readme_for(self.TEXT, "0.19")
        self.assertIn("made with version 0.19 of the converter", out)
        self.assertNotIn("0.12", out)
        self.assertEqual(out.count("\r\n"), 3)
        self.assertNotIn("\r\r", out)

    def test_already_crlf_stays_single(self):
        out = release.readme_for(self.TEXT.replace("\n", "\r\n"), "0.19")
        self.assertEqual(out.count("\r\n"), 3)
        self.assertNotIn("\r\r", out)

    def test_missing_or_repeated_line_is_refused(self):
        with self.assertRaises(release.ReleaseError):
            release.readme_for("no version here\n", "0.19")
        with self.assertRaises(release.ReleaseError):
            release.readme_for(self.TEXT + self.TEXT, "0.19")


class ZipLayout(unittest.TestCase):
    def test_three_files_at_the_top_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            (tmp / "plugin").write_bytes(b"\x00" * 100)
            (tmp / "credits").write_text("CbC", encoding="utf-8")
            zpath = tmp / "out.zip"
            release.build_zip(zpath, tmp / "plugin", "read me\r\n", tmp / "credits")
            with zipfile.ZipFile(zpath) as z:
                self.assertEqual(sorted(z.namelist()),
                                 sorted([release.PLUGIN_NAME, release.README_NAME, release.CREDITS_NAME]))
                self.assertEqual(z.read(release.README_NAME), b"read me\r\n")
                self.assertEqual(len(z.read(release.PLUGIN_NAME)), 100)


class SiteConstants(unittest.TestCase):
    SITE = 'X = 1\nDOWNLOAD_SHA256 = "old"\nDOWNLOAD_MB = 222\nDOWNLOAD_VERSION = "0.18"\nY = 2\n'

    def test_replaces_all_three(self):
        out = release.site_constants(self.SITE, "abc123", 230, "0.19")
        self.assertIn('DOWNLOAD_SHA256 = "abc123"', out)
        self.assertIn("DOWNLOAD_MB = 230", out)
        self.assertIn('DOWNLOAD_VERSION = "0.19"', out)
        self.assertTrue(out.startswith("X = 1\n") and out.endswith("Y = 2\n"))

    def test_missing_constant_is_refused(self):
        with self.assertRaises(release.ReleaseError):
            release.site_constants("DOWNLOAD_MB = 1\n", "abc", 1, "0.19")

    def test_the_real_site_has_all_three(self):
        text = (ROOT / "scripts" / "keep_site.py").read_text(encoding="utf-8")
        release.site_constants(text, "abc", 1, "0.19")


if __name__ == "__main__":
    unittest.main()
