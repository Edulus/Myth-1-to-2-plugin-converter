"""Tests for the website's in-browser converter entry point."""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import __version__, reader, web  # noqa: E402

from . import fixtures  # noqa: E402

CHANGES = pathlib.Path(__file__).resolve().parent.parent / "web" / "convert" / "changes.json"


class TestChanges(unittest.TestCase):
    """The website's list of changes and the version number must agree."""

    def setUp(self):
        import json

        self.changes = json.loads(CHANGES.read_text(encoding="utf-8"))

    def test_the_newest_change_is_the_current_version(self):
        self.assertEqual(__version__, self.changes[0]["version"])

    def test_the_newest_version_says_what_to_test_next(self):
        tests = self.changes[0].get("test", [])
        self.assertTrue(tests)
        for t in tests:
            self.assertTrue(t.strip())

    def test_newest_first_with_distinct_versions_and_dates(self):
        import datetime

        versions = [tuple(map(int, c["version"].split("."))) for c in self.changes]
        self.assertEqual(sorted(versions, reverse=True), versions)
        self.assertEqual(len(set(versions)), len(versions))
        dates = [datetime.date.fromisoformat(c["date"]) for c in self.changes]
        self.assertEqual(sorted(dates, reverse=True), dates)
        for c in self.changes:
            self.assertTrue(c["change"].strip())


class TestOutputName(unittest.TestCase):
    def test_drops_the_extension_and_says_what_it_is_for(self):
        self.assertEqual("Mauriac for M2", web.output_name("Mauriac.gor"))
        self.assertEqual("Mauriac for M2", web.output_name("Mauriac.GOR"))

    def test_no_dots_for_a_browser_to_mistake_for_a_file_type(self):
        self.assertEqual("cbc TFL mauriac for M2", web.output_name("cbc.TFL.mauriac.gor"))

    def test_never_longer_than_myth_ii_lists(self):
        name = web.output_name("A very long plugin name that goes on and on.gor")
        self.assertLessEqual(len(name), 32)
        self.assertTrue(name.endswith(" for M2"))

    def test_characters_a_filename_cannot_hold_are_removed(self):
        self.assertEqual("ab for M2", web.output_name('a:b?.gor'))

    def test_an_empty_name_still_gives_a_name(self):
        self.assertEqual("Converted plugin for M2", web.output_name(".gor"))


class TestConvert(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.plugin = self.dir / "upload"
        self.plugin.write_bytes(fixtures.build_tfl_mono(fixtures.MESH_TAGS))
        self.stock = self.dir / "TAGS.GOR"
        self.stock.write_bytes(fixtures.build_tfl_mono([
            (b"stock text", b"text", b"stk1", b"unused"),
        ]))

    def tearDown(self):
        self.tmp.cleanup()

    def convert(self, name="Crows Bridge.gor"):
        return web.convert(self.plugin, name, self.dir, [self.stock])

    def test_writes_a_myth_ii_plugin_named_for_the_upload(self):
        result = self.convert()
        self.assertEqual("Crows Bridge for M2", result["filename"])
        written = reader.read(result["path"])
        self.assertTrue(written.is_sb)
        self.assertEqual("Crows Bridge for M2", written.header.name.rstrip(b"\0").decode())
        self.assertEqual(pathlib.Path(result["path"]).stat().st_size, result["bytes"])

    def test_lists_the_levels_the_game_will_show(self):
        self.assertEqual(1, len(self.convert()["levels"]))

    def test_keeps_the_technical_report(self):
        self.assertIn("Levels the game will list", self.convert()["details"])

    def test_the_report_names_the_converter_version(self):
        self.assertTrue(self.convert()["details"].startswith(f"Converter version {__version__}\n"))

    def test_no_levels_is_explained(self):
        self.plugin.write_bytes(fixtures.build_tfl_mono(fixtures.SAMPLE_TAGS))
        notes = self.convert()["notes"]
        self.assertTrue([n for n in notes if "No playable levels" in n])

    def test_a_file_that_is_not_a_plugin_gets_a_plain_message(self):
        self.plugin.write_bytes(b"not a plugin at all" * 10)
        with self.assertRaises(web.Problem) as caught:
            self.convert()
        self.assertIn(".gor", str(caught.exception))

    def test_a_myth_ii_plugin_is_turned_away_kindly(self):
        self.plugin.write_bytes(fixtures.build_sb_mono([(b"x", b"text", b"xxxx", b"hi")]))
        with self.assertRaises(web.Problem) as caught:
            self.convert()
        self.assertIn("already a Myth II plugin", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
