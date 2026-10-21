"""Tests for the mesh effect (`meef`) body converter."""

import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.convert.tags import meef  # noqa: E402


def tfl_meef(flags=0, amplitude=205, cutoff=256.0):
    """Shaped like the stock TFL wight explosion."""
    body = bytearray(32)
    struct.pack_into(">Lh", body, 0, flags, amplitude)
    struct.pack_into(">L", body, 8, 0x1998)
    struct.pack_into(">f", body, 12, cutoff)
    struct.pack_into(">h", body, 16, 4)
    return bytes(body)


def unpack(body):
    flags, amp, vel, cut, diss, epi, shake = struct.unpack_from(">L6h", body)
    return flags, amp, vel, cut, diss, epi, shake, body[16:20], struct.unpack_from(">4h", body, 20)


class TestMeshEffect(unittest.TestCase):
    def test_reproduces_bungies_own_port_of_the_wight_explosion(self):
        """Myth II's base-game wiex is Bungie's port of TFL's: amplitude 205 ->
        409 (doubled; 410 here), cutoff 256.0 -> 256, shockwave via inme."""
        out, warnings = meef.convert(tfl_meef())
        self.assertEqual(36, len(out))
        self.assertEqual([], warnings)
        flags, amp, vel, cut, diss, epi, shake, coll, shock = unpack(out)
        self.assertEqual(0, flags)
        self.assertEqual(410, amp)
        self.assertEqual((0x0800, 256, 0x0066, 0, -1), (vel, cut, diss, epi, shake))
        self.assertEqual(b"inme", coll)
        self.assertEqual((16, 32, 512, 512), shock)

    def test_the_collection_reference_is_never_tfl_bytes(self):
        """The in-engine failure: TFL bytes read as the shockwave collection."""
        _, _, _, _, _, _, _, coll, _ = unpack(meef.convert(tfl_meef(flags=1))[0])
        self.assertEqual(b"inme", coll)

    def test_flags_carry_over(self):
        self.assertEqual(1, unpack(meef.convert(tfl_meef(flags=1))[0])[0])

    def test_a_body_of_another_size_is_left_alone(self):
        out, warnings = meef.convert(bytes(36))
        self.assertEqual(bytes(36), out)
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
