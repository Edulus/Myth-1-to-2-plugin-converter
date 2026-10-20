"""Tests for the projectile (`proj`) body converter."""

import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.convert import plugin as convert_plugin  # noqa: E402
from src.convert.tags import proj  # noqa: E402
from src.idmap import IdMap  # noqa: E402


def tfl_proj(**fields):
    """A 256-byte TFL projectile. ``fields`` maps TFL offset -> bytes."""
    body = bytearray(256)
    for offset, value in fields.items():
        offset = int(offset)
        body[offset : offset + len(value)] = value
    return bytes(body)


class TestLayout(unittest.TestCase):
    def test_size_is_unchanged(self):
        converted, warnings = proj.convert(tfl_proj())
        self.assertEqual(256, len(converted))
        self.assertEqual([], warnings)

    def test_fields_before_the_tfl_only_bytes_stay_put(self):
        body = tfl_proj(**{"4": b"coll", "64": b"rebo"})
        converted, _ = proj.convert(body)
        self.assertEqual(b"coll", converted[4:8])
        self.assertEqual(b"rebo", converted[64:68])

    def test_fields_after_them_move_back_four_bytes(self):
        """Anchored on real data: TFL's promoted projectile at 96 is Myth II's
        at 92, and its artifact at 124 is Myth II's at 120."""
        body = tfl_proj(**{"80": b"\x01\x00\x02\x01", "96": b"prom", "124": b"arti"})
        converted, _ = proj.convert(body)
        self.assertEqual(b"\x01\x00\x02\x01", converted[76:80])
        self.assertEqual(b"prom", converted[92:96])
        self.assertEqual(b"arti", converted[120:124])

    def test_the_tfl_only_bytes_are_dropped_and_padding_added(self):
        body = tfl_proj(**{"76": b"\xde\xad\xbe\xef", "252": b"\x11\x22\x33\x44"})
        converted, _ = proj.convert(body)
        self.assertNotIn(b"\xde\xad\xbe\xef", converted)
        self.assertEqual(b"\x11\x22\x33\x44", converted[248:252])
        self.assertEqual(b"\0\0\0\0", converted[252:256])

    def test_a_body_of_the_wrong_size_is_reported_not_mangled(self):
        body = b"\x01" * 100
        converted, warnings = proj.convert(body)
        self.assertEqual(body, converted)
        self.assertTrue(warnings)


class TestFlags(unittest.TestCase):
    def flags(self, value):
        converted, _ = proj.convert(tfl_proj(**{"0": struct.pack(">L", value)}))
        return struct.unpack_from(">L", converted)[0]

    def test_the_debris_bit_does_not_become_is_guided(self):
        """TFL sets bit 1 on thrown debris; Myth II would read it as guided."""
        self.assertEqual(0, self.flags(1 << 1))

    def test_other_bits_keep_their_meaning(self):
        value = (1 << 0) | (1 << 9) | (1 << 11) | (1 << 31)
        self.assertEqual(value, self.flags(value | (1 << 1)))


class TestReferences(unittest.TestCase):
    def test_zero_references_become_none(self):
        converted, _ = proj.convert(tfl_proj())
        for offset, _type in proj.REFERENCES:
            self.assertEqual(b"\xff" * 4, converted[offset : offset + 4], offset)

    def test_script_tag_stays_zero(self):
        """Zero in all 273 of Magma's projectiles -- not a 'none' sentinel."""
        converted, _ = proj.convert(tfl_proj())
        self.assertEqual(b"\0" * 4, converted[148:152])

    def test_references_follow_the_id_map(self):
        id_map = IdMap()
        id_map.add(b"prgr", b"oldg", b"newg")
        id_map.add(b"proj", b"oldp", b"newp")
        context = convert_plugin.ConversionContext(id_map=id_map)
        body = tfl_proj(**{"16": b"oldg", "96": b"oldp"})
        converted, _ = proj.convert(body, context)
        self.assertEqual(b"newg", converted[16:20])
        self.assertEqual(b"newp", converted[92:96])

    def test_none_is_not_remapped(self):
        id_map = IdMap()
        id_map.add(b"prgr", b"\xff\xff\xff\xff", b"oops")
        context = convert_plugin.ConversionContext(id_map=id_map)
        converted, _ = proj.convert(tfl_proj(**{"16": b"\xff" * 4}), context)
        self.assertEqual(b"\xff" * 4, converted[16:20])


if __name__ == "__main__":
    unittest.main()
