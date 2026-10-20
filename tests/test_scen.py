"""Tests for the scenery (`scen`) body converter."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.convert import plugin as convert_plugin  # noqa: E402
from src.convert.tags import scen  # noqa: E402
from src.idmap import IdMap  # noqa: E402


def tfl_scen(**fields):
    """A 128-byte TFL scenery body. ``fields`` maps TFL offset -> bytes."""
    body = bytearray(128)
    for offset, value in fields.items():
        offset = int(offset)
        body[offset : offset + len(value)] = value
    return bytes(body)


class TestLayout(unittest.TestCase):
    def test_size_is_unchanged(self):
        converted, warnings = scen.convert(tfl_scen())
        self.assertEqual(128, len(converted))
        self.assertEqual([], warnings)

    def test_fields_land_where_myth_ii_reads_them(self):
        body = tfl_scen(**{
            "0": b"\x00\x00\x00\x23",
            "8": b"core",
            "24": b"obje",
            "28": b"proj",
            "44": b"pg01",
            "56": b"pg04",
            "60": b"\x00\x01\x00\x02",
        })
        converted, _ = scen.convert(body)
        self.assertEqual(b"\x00\x00\x00\x23", converted[0:4])
        self.assertEqual(b"core", converted[4:8])
        self.assertEqual(b"obje", converted[8:12])
        self.assertEqual(b"proj", converted[12:16])
        self.assertEqual(b"pg01", converted[24:28])
        self.assertEqual(b"pg04", converted[36:40])
        self.assertEqual(b"\x00\x01\x00\x02", converted[40:44])

    def test_tfl_only_words_are_dropped(self):
        body = tfl_scen(**{"32": b"\x00\x0b\x01\x00", "74": b"\xde\xad"})
        converted, _ = scen.convert(body)
        self.assertNotIn(b"\x00\x0b\x01\x00", converted)
        self.assertEqual(bytes(128 - 54), converted[54:])

    def test_netgame_fields_default_to_none(self):
        converted, _ = scen.convert(tfl_scen())
        self.assertEqual(b"\xff" * 4, converted[16:20])

    def test_a_body_of_the_wrong_size_is_reported_not_mangled(self):
        converted, warnings = scen.convert(b"\x01" * 64)
        self.assertEqual(b"\x01" * 64, converted)
        self.assertTrue(warnings)


class TestReferences(unittest.TestCase):
    def test_zero_references_become_none(self):
        converted, _ = scen.convert(tfl_scen())
        for offset, _type in scen.REFERENCES:
            self.assertEqual(b"\xff" * 4, converted[offset : offset + 4], offset)

    def test_references_follow_the_id_map(self):
        id_map = IdMap()
        id_map.add(b"obje", b"old1", b"new1")
        id_map.add(b"prgr", b"old2", b"new2")
        context = convert_plugin.ConversionContext(id_map=id_map)
        body = tfl_scen(**{"24": b"old1", "48": b"old2"})
        converted, _ = scen.convert(body, context)
        self.assertEqual(b"new1", converted[8:12])
        self.assertEqual(b"new2", converted[28:32])


if __name__ == "__main__":
    unittest.main()
