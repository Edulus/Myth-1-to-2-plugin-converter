"""Tests for ambient sound (`amso`) conversion."""

import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import reader  # noqa: E402
from src.convert import plugin as convert_plugin  # noqa: E402
from src.convert import tags  # noqa: E402
from src.convert.tags import amso  # noqa: E402

from . import fixtures  # noqa: E402


def body(*sounds):
    slots = b"".join(sounds) + bytes(4 * (6 - len(sounds)))
    return struct.pack(">Lhhhh", 1, 0x2000, 0x3000, 150, 150) + slots + bytes(28)


class TestAmbientSound(unittest.TestCase):
    def test_unused_sound_slots_become_none(self):
        """TFL writes an unused slot as zero; Myth II's own copies of the same
        ambient sounds have FFFFFFFF there."""
        converted, warnings = amso.convert(body(b"am01", b"ambl"))
        self.assertEqual([], warnings)
        self.assertEqual(64, len(converted))
        self.assertEqual(b"am01ambl" + b"\xff" * 16, converted[12:36])

    def test_everything_else_is_kept(self):
        source = body(b"am01")
        converted, _ = amso.convert(source)
        self.assertEqual(source[:12], converted[:12])
        self.assertEqual(source[36:], converted[36:])

    def test_a_body_of_another_size_is_left_alone(self):
        converted, warnings = amso.convert(bytes(32))
        self.assertEqual(bytes(32), converted)
        self.assertTrue(warnings)


class TestOneBadTagDoesNotStopTheRest(unittest.TestCase):
    def test_a_converter_that_fails_copies_its_tag_and_reports_it(self):
        class Broken:
            @staticmethod
            def convert(body, context=None):
                raise struct.error("unpack requires a buffer of 8 bytes")

        tfl = reader.read_bytes(fixtures.build_tfl_mono([
            (b"hum", b"amso", b"am01", body(b"am01")),
            (b"wind", b"amso", b"am02", body(b"am02")),
        ]))
        original = tags.CONVERTERS[b"amso"]
        tags.CONVERTERS[b"amso"] = Broken
        try:
            sb, report = convert_plugin.convert_container(tfl)
        finally:
            tags.CONVERTERS[b"amso"] = original
        self.assertEqual(2, len([t for t in sb.tags if t.tag_type == b"amso"]))
        self.assertEqual(2, len(report.passed_through()))
        self.assertIn("could not be converted", report.passed_through()[0].warnings[0])


if __name__ == "__main__":
    unittest.main()
