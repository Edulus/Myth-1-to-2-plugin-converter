"""Tests for converting TFL tag archives into a Myth II tagset."""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import codec, reader  # noqa: E402
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

    def test_a_myth_ii_archive_is_refused(self):
        sb = self.dir / "myth2"
        sb.write_bytes(fixtures.build_sb_mono([(b"x", b"text", b"xxxx", b"hi")]))
        with self.assertRaises(convert_plugin.ConversionError):
            convert_plugin.convert_tagset([sb], self.out)


if __name__ == "__main__":
    unittest.main()
