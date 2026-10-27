"""Tests for converting TFL tag archives into a Myth II tagset."""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import codec, idmap, reader  # noqa: E402
from src.convert import plugin as convert_plugin  # noqa: E402

from . import fixtures  # noqa: E402


class TestTagset(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.first = self.dir / "TAGS.GOR"
        self.second = self.dir / "ARTSOUND.GOR"
        # The first archive has a mesh, which on its own would get an entrypoint.
        self.first.write_bytes(fixtures.build_tfl_mono(fixtures.MESH_TAGS))
        shared = fixtures.MESH_TAGS[0]
        self.second.write_bytes(fixtures.build_tfl_mono([
            (shared[0], shared[1], shared[2], b"a different body"),
            (b"extra", b"soun", b"xtra", b"\0" * 16),
        ]))
        self.out = self.dir / "ZZ TFL stock"

    def tearDown(self):
        self.tmp.cleanup()

    def convert(self, **kwargs):
        return convert_plugin.convert_tagset([self.first, self.second], self.out, **kwargs)

    def test_writes_a_myth_ii_tagset_with_no_entrypoints(self):
        """Only entrypoint-free plugins can be activated as tagsets (in-engine)."""
        self.convert()
        result = reader.read(self.out)
        self.assertTrue(result.is_sb)
        self.assertEqual([], result.entrypoints)
        self.assertEqual(0, result.header.entry_tag_count)

    def test_the_internal_name_defaults_to_the_filename(self):
        """Myth II identifies plugins by this name; a clash hides one of them."""
        self.convert()
        self.assertEqual("ZZ TFL stock", codec.decode_string(reader.read(self.out).header.name))

    def test_an_explicit_name_wins(self):
        self.out = self.dir / "file"
        self.convert(name="ZZ Named")
        self.assertEqual("ZZ Named", codec.decode_string(reader.read(self.out).header.name))

    def test_archives_merge_and_the_first_wins(self):
        _report, _written, duplicates = self.convert()
        result = reader.read(self.out)
        ids = {(t.tag_type, t.tag_id) for t in result.tags}
        self.assertIn((b"soun", b"xtra"), ids, "tags only in a later archive are kept")
        shared_type, shared_id = fixtures.MESH_TAGS[0][1], fixtures.MESH_TAGS[0][2]
        bodies = [t.body for t in result.tags if (t.tag_type, t.tag_id) == (shared_type, shared_id)]
        self.assertEqual(1, len(bodies))
        self.assertNotEqual(b"a different body", bodies[0])
        self.assertEqual({str(self.second): 1}, duplicates)

    def test_engine_facing_tags_are_left_for_myth_ii(self):
        """A tagset's tags replace Myth II's base tags of the same ID. TFL's
        'internal solo postgame' strings crashed every level's end screen."""
        self.second.write_bytes(fixtures.build_tfl_mono([
            (b"internal solo postgame", b"stli", b"in03", b"%d killed\0"),
            (b"screen low-resolution", b"font", b"co#1", b"\0" * 16),
            (b"08 subtitles", b"stli", b"08su", b"a line\0"),
        ]))
        report, _written, _dups = self.convert()
        ids = {(t.tag_type, t.tag_id) for t in reader.read(self.out).tags}
        self.assertNotIn((b"stli", b"in03"), ids)
        self.assertNotIn((b"font", b"co#1"), ids)
        self.assertIn((b"stli", b"08su"), ids, "level text is content, and stays")
        self.assertTrue([w for w in report.warnings if "left out 2 engine-facing" in w])

    def test_a_myth_ii_archive_is_refused(self):
        sb = self.dir / "myth2"
        sb.write_bytes(fixtures.build_sb_mono([(b"x", b"text", b"xxxx", b"hi")]))
        with self.assertRaises(convert_plugin.ConversionError):
            convert_plugin.convert_tagset([sb], self.out)


class TestBundleStock(unittest.TestCase):
    """`convert --stock`: a plugin that carries the stock tags it leans on."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.plugin = self.dir / "plugin.gor"
        # The plugin points at stk1; a collection's sequence names the sound
        # stk4; sample data "mentions" stk5 by chance.
        self.plugin.write_bytes(fixtures.build_tfl_mono(fixtures.MESH_TAGS + [
            (b"refers", b"text", b"refs", b"..stk1.."),
            (b"a picture", b".256", b"pict", b"pixels stk4 pixels"),
            (b"a sound", b"soun", b"snd1", b"samples stk5 samples"),
        ]))
        self.stock = self.dir / "TAGS.GOR"
        self.stock.write_bytes(fixtures.build_tfl_mono([
            (b"stock text", b"text", b"stk1", b"from the stock set, see stk2"),
            (b"reached via stk1", b"stli", b"stk2", b"chained\0"),
            (b"never mentioned", b"text", b"stk3", b"unused"),
            (b"named by a sequence", b"soun", b"stk4", b"a celebration"),
            (b"only in samples", b"text", b"stk5", b"unused"),
            (b"clash", b"stli", b"30cc", b"the stock version"),
            (b"a stock level", b"mesh", b"stlv", fixtures.MESH_TAGS[0][3]),
            (b"internal solo postgame", b"stli", b"in03", b"%d killed\0"),
        ]))
        self.out = self.dir / "ZZ bundled"

    def tearDown(self):
        self.tmp.cleanup()

    def bundle(self, **kwargs):
        report, _written = convert_plugin.convert_file(
            self.plugin, self.out, stock_paths=[self.stock], **kwargs
        )
        return report, reader.read(self.out)

    def ids(self, result):
        return {(t.tag_type, t.tag_id) for t in result.tags}

    def test_stock_tags_the_plugin_uses_are_carried_in(self):
        report, result = self.bundle()
        self.assertIn((b"text", b"stk1"), self.ids(result))
        self.assertIn((b"stli", b"stk2"), self.ids(result), "reached through stk1")
        self.assertEqual(3, report.bundled_stock)

    def test_stock_tags_nothing_points_at_are_left_out(self):
        _report, result = self.bundle()
        self.assertNotIn((b"text", b"stk3"), self.ids(result))

    def test_sounds_named_by_a_collection_are_carried_in(self):
        _report, result = self.bundle()
        self.assertIn((b"soun", b"stk4"), self.ids(result))

    def test_sound_data_is_not_searched_for_references(self):
        _report, result = self.bundle()
        self.assertNotIn((b"text", b"stk5"), self.ids(result))

    def test_all_stock_carries_everything(self):
        report, result = self.bundle(all_stock=True)
        self.assertIn((b"text", b"stk3"), self.ids(result))
        self.assertEqual(5, report.bundled_stock)

    def test_a_decisions_mapping_target_is_carried_in(self):
        id_map = idmap.IdMap()
        id_map.add(b"text", b"gone", b"stk3")
        _report, result = self.bundle(id_map=id_map)
        self.assertIn((b"text", b"stk3"), self.ids(result))

    def test_the_plugins_own_tag_beats_a_stock_tag_of_the_same_id(self):
        _report, result = self.bundle()
        bodies = [t.body for t in result.tags if (t.tag_type, t.tag_id) == (b"stli", b"30cc")]
        self.assertEqual(1, len(bodies))
        self.assertNotEqual(b"the stock version", bodies[0])

    def test_stock_levels_do_not_become_entrypoints(self):
        _report, result = self.bundle()
        self.assertEqual(1, len(result.entrypoints), "only the plugin's own level")
        self.assertNotIn((b"mesh", b"stlv"), {(t.tag_type, t.tag_id) for t in result.tags})

    def test_engine_facing_stock_tags_are_left_for_myth_ii(self):
        _report, result = self.bundle()
        self.assertNotIn((b"stli", b"in03"), {(t.tag_type, t.tag_id) for t in result.tags})

    def test_a_myth_ii_stock_archive_is_refused(self):
        sb = self.dir / "myth2"
        sb.write_bytes(fixtures.build_sb_mono([(b"x", b"text", b"xxxx", b"hi")]))
        with self.assertRaises(convert_plugin.ConversionError):
            convert_plugin.convert_file(self.plugin, self.out, stock_paths=[sb])


if __name__ == "__main__":
    unittest.main()
