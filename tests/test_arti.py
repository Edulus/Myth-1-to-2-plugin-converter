"""Tests for the artifact (`arti`) body converter."""

import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import mons  # noqa: E402
from src.convert import plugin as convert_plugin  # noqa: E402
from src.convert.tags import arti  # noqa: E402
from src.idmap import IdMap  # noqa: E402


def tfl_arti(size=256, **fields):
    """A TFL artifact body. ``fields`` maps TFL offset -> bytes."""
    body = bytearray(size)
    for offset, value in fields.items():
        offset = int(offset)
        body[offset : offset + len(value)] = value
    return bytes(body)


class TestLayout(unittest.TestCase):
    def test_both_tfl_sizes_become_168(self):
        for size in (128, 256):
            converted, warnings = arti.convert(tfl_arti(size))
            self.assertEqual(168, len(converted))
            self.assertEqual([], warnings)

    def test_header_and_tail_keep_their_meaning(self):
        body = tfl_arti(**{"4": b"dwar", "16": b"heob", "28": b"bahe", "108": b"sp04", "112": b"mons"})
        converted, _ = arti.convert(body)
        self.assertEqual(b"dwar", converted[4:8])
        self.assertEqual(b"heob", converted[16:20])
        self.assertEqual(b"bahe", converted[28:32])
        self.assertEqual(b"sp04", converted[148:152])
        self.assertEqual(b"mons", converted[152:156])

    def test_the_attack_is_converted_like_a_monster_attack(self):
        attack = bytes(range(32))
        converted, _ = arti.convert(tfl_arti(**{"76": attack}))
        expected = mons.convert_attack(attack)
        expected = expected if isinstance(expected, (bytes, bytearray)) else expected.encode()
        self.assertEqual(expected, converted[84:148])

    def test_non_zero_padding_is_reported(self):
        _, warnings = arti.convert(tfl_arti(**{"200": b"\x01"}))
        self.assertTrue(warnings)

    def test_a_body_of_another_size_is_left_alone(self):
        converted, warnings = arti.convert(b"\0" * 100)
        self.assertEqual(b"\0" * 100, converted)
        self.assertTrue(warnings)


class TestEffectModifiers(unittest.TestCase):
    def mods(self, body):
        converted, _ = arti.convert(body)
        return struct.unpack(">16h", converted[52:84])

    def test_all_zero_becomes_normal_not_immune(self):
        """0 as a damage multiplier would make the bearer immune to everything."""
        self.assertEqual((0x100,) * 9 + (0,) * 7, self.mods(tfl_arti()))

    def test_real_values_are_kept_in_the_first_twelve_slots(self):
        values = tuple(range(1, 13))
        body = tfl_arti(**{"52": struct.pack(">12h", *values)})
        self.assertEqual(values + (0,) * 4, self.mods(body))


class TestReferences(unittest.TestCase):
    def test_references_and_the_attack_projectile_follow_the_id_map(self):
        id_map = IdMap()
        id_map.add(b"proj", b"oldp", b"newp")
        id_map.add(b"stli", b"olds", b"news")
        context = convert_plugin.ConversionContext(id_map=id_map)
        attack = bytearray(32)
        attack[4:8] = b"oldp"
        body = tfl_arti(**{"28": b"oldp", "76": bytes(attack), "108": b"olds"})
        converted, _ = arti.convert(body, context)
        self.assertEqual(b"newp", converted[28:32])
        self.assertEqual(b"news", converted[148:152])
        self.assertEqual(b"newp", converted[88:92])


if __name__ == "__main__":
    unittest.main()
