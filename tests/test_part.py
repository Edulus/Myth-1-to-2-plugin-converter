"""Tests for the particle system (`part`) body converter."""

import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.convert import plugin as convert_plugin  # noqa: E402
from src.convert.tags import part  # noqa: E402
from src.idmap import IdMap  # noqa: E402


class TestParticleSystem(unittest.TestCase):
    def test_grows_to_132_and_keeps_the_shared_92_bytes(self):
        body = bytes(range(92)) + bytes(36)
        converted, warnings = part.convert(body)
        self.assertEqual(132, len(converted))
        self.assertEqual(body[:92], converted[:92])
        self.assertEqual([], warnings)

    def test_box_width_is_never_zero(self):
        """A zero box width crashed Myth II with a divide by zero on the first
        frame of Tandem (particle_systems.c:352)."""
        converted, _ = part.convert(bytes(128))
        width, top, bottom, splashes, effects = struct.unpack_from(">HHhHH", converted, 92)
        self.assertGreater(width, 0)
        self.assertEqual((4, 0x0800, -0x200, 1, 8), (width, top, bottom, splashes, effects))

    def test_non_zero_tfl_tail_is_reported(self):
        body = bytes(100) + b"\x01" + bytes(27)
        _, warnings = part.convert(body)
        self.assertTrue(warnings)

    def test_a_body_of_another_size_is_left_alone(self):
        converted, warnings = part.convert(bytes(132))
        self.assertEqual(bytes(132), converted)
        self.assertTrue(warnings)

    def test_references_follow_the_id_map(self):
        id_map = IdMap()
        id_map.add(b"core", b"oldc", b"newc")
        id_map.add(b"lpgr", b"oldl", b"newl")
        context = convert_plugin.ConversionContext(id_map=id_map)
        body = bytearray(128)
        body[4:8] = b"oldc"
        body[88:92] = b"oldl"
        converted, _ = part.convert(bytes(body), context)
        self.assertEqual(b"newc", converted[4:8])
        self.assertEqual(b"newl", converted[88:92])


if __name__ == "__main__":
    unittest.main()
