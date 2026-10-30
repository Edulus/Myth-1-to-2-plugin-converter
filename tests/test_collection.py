"""Tests for the `.256` sprite collection converter."""

import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.convert.tags import collection  # noqa: E402

DATA = 320


def tfl_collection(bitmap_height=3, row_table=True):
    """A minimal TFL collection: one colour table, one bitmap reference
    pointing at a bitmap with a row address table, one sequence reference."""
    color = bytes(32)
    bitref_off, seqref_off = 32, 160
    bitmap_off = 288
    meta = bytearray(52)
    flags = 0 if row_table else collection.NO_ROW_ADDRESS_TABLE
    struct.pack_into(">HHhH", meta, 0, 4, bitmap_height, 4, flags)
    meta[18:52] = b"\xaa" * 34  # stale runtime values
    rows = b"\x02\x94\x8b\x80" * (bitmap_height - 1) if row_table else b""
    pixels = b"\x11" * 12
    bitmap = bytes(meta) + rows + pixels

    bitref = bytearray(128)
    bitref[:4] = b"bmp0"
    struct.pack_into(">II", bitref, 64, bitmap_off, len(bitmap))
    bitref[72:76] = b"\x02\x94\x89\x50"
    seqref = bytearray(128)
    struct.pack_into(">II", seqref, 64, 999, 64)
    seqref[72:76] = b"\x02\x82\xc3\xa0"

    data = color + bytes(bitref) + bytes(seqref) + bitmap
    header = bytearray(DATA)
    sections = {0: (1, 0, 32), 2: (1, bitref_off, 128), 4: (1, seqref_off, 128)}
    for k in range(8):
        count, offset, size = sections.get(k, (0, 0, 0))
        struct.pack_into(">4I", header, 64 + 16 * k, count, offset, size, 0xDEADBEEF)
    struct.pack_into(">III", header, 248, DATA, len(data), 0)
    return bytes(header) + data


def tfl_landscape(sizes):
    """A TFL collection with no sequences and one bitmap per ``(width, height)``.
    Pixels are left out: only each bitmap's metadata is read."""
    refs_off = 32
    bitmaps_off = refs_off + 128 * len(sizes)
    refs, bitmaps = bytearray(), bytearray()
    for w, h in sizes:
        meta = bytearray(52)
        struct.pack_into(">HHhH", meta, 0, w, h, w, collection.NO_ROW_ADDRESS_TABLE)
        ref = bytearray(128)
        struct.pack_into(">II", ref, 64, bitmaps_off + len(bitmaps), len(meta))
        refs += ref
        bitmaps += meta
    data = bytes(32) + bytes(refs) + bytes(bitmaps)
    header = bytearray(DATA)
    sections = {0: (1, 0, 32), 2: (len(sizes), refs_off, len(refs))}
    for k in range(8):
        count, offset, size = sections.get(k, (0, 0, 0))
        struct.pack_into(">4I", header, 64 + 16 * k, count, offset, size, 0)
    struct.pack_into(">III", header, 248, DATA, len(data), 0)
    return bytes(header) + data


class TestLandscape(unittest.TestCase):
    def bitmap_refs(self, out):
        return struct.unpack_from(">3I", out, 64 + 16 * 2)

    def test_a_bitmap_after_the_tiles_is_dropped(self):
        """Crow's Bridge's ``ambu``: 60 tiles, then one 153x128 bitmap."""
        body = tfl_landscape([(256, 256)] * 4 + [(153, 128)])
        out, warnings = collection.convert(body)
        self.assertEqual((4, 64, 4 * 128), self.bitmap_refs(out))
        self.assertEqual(len(body) + 32, len(out), "the dropped bytes stay")
        self.assertEqual(1, len(warnings))
        self.assertIn("153x128", warnings[0])

    def test_a_landscape_of_only_tiles_is_left_alone(self):
        out, warnings = collection.convert(tfl_landscape([(256, 256)] * 4))
        self.assertEqual((4, 64, 4 * 128), self.bitmap_refs(out))
        self.assertEqual([], warnings)

    def test_a_tile_after_an_odd_bitmap_keeps_everything(self):
        out, warnings = collection.convert(tfl_landscape([(256, 256), (64, 64), (256, 256)]))
        self.assertEqual(3, self.bitmap_refs(out)[0])
        self.assertEqual([], warnings)

    def test_a_collection_with_sequences_is_never_trimmed(self):
        out, warnings = collection.convert(tfl_collection())
        self.assertEqual(1, self.bitmap_refs(out)[0])
        self.assertEqual([], warnings)


class TestCollection(unittest.TestCase):
    def setUp(self):
        self.body = tfl_collection()
        self.out, self.warnings = collection.convert(self.body)

    def section(self, k):
        return struct.unpack_from(">4I", self.out, 64 + 16 * k)

    def test_grows_by_32_and_the_data_follows(self):
        self.assertEqual(len(self.body) + 32, len(self.out))
        self.assertEqual(bytes(32), self.out[DATA : DATA + 32])
        self.assertEqual(self.body[DATA : DATA + 32], self.out[DATA + 32 : DATA + 64], "colour table")
        self.assertEqual([], self.warnings)
        self.assertEqual(struct.unpack_from(">I", self.body, 252)[0] + 32,
                         struct.unpack_from(">I", self.out, 252)[0])

    def test_section_offsets_move_and_empty_ones_are_zero(self):
        self.assertEqual((1, 32, 32, 0), self.section(0))
        self.assertEqual((0, 0, 0, 0), self.section(1))
        self.assertEqual((1, 64, 128, 0), self.section(2))
        self.assertEqual((1, 192, 128, 0), self.section(4))

    def test_reference_offsets_move_and_runtime_words_clear(self):
        bitref = DATA + 64  # section offsets count from the data block, which now starts with the 32
        self.assertEqual(288 + 32, struct.unpack_from(">I", self.out, bitref + 64)[0])
        self.assertEqual(bytes(4), self.out[bitref + 72 : bitref + 76])
        seqref = DATA + 192
        self.assertEqual(999 + 32, struct.unpack_from(">I", self.out, seqref + 64)[0])
        self.assertEqual(bytes(56), self.out[seqref + 72 : seqref + 128])

    def test_bitmap_runtime_fields_and_row_table_clear_but_pixels_stay(self):
        meta = DATA + 288 + 32
        self.assertEqual(bytes(34), self.out[meta + 18 : meta + 52])
        self.assertEqual(bytes(8), self.out[meta + 52 : meta + 60])
        self.assertEqual(b"\x11" * 12, self.out[meta + 60 : meta + 72])

    def test_no_row_table_means_pixels_start_after_the_meta(self):
        out, _ = collection.convert(tfl_collection(row_table=False))
        meta = DATA + 288 + 32
        self.assertEqual(b"\x11" * 12, out[meta + 52 : meta + 64])

    def test_a_section_outside_the_body_is_reported_not_mangled(self):
        body = bytearray(tfl_collection())
        struct.pack_into(">I", body, 64 + 16 * 2 + 4, 10_000_000)
        out, warnings = collection.convert(bytes(body))
        self.assertEqual(bytes(body), out)
        self.assertTrue(warnings)

    def test_a_short_body_is_left_alone(self):
        out, warnings = collection.convert(b"\0" * 100)
        self.assertEqual(b"\0" * 100, out)
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
