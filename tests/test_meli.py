"""Tests for the mesh lighting (`meli`) body converter."""

import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.convert.tags import meli  # noqa: E402


def tfl_grassland():
    """The stock TFL 'deml' (grassland), float for float."""
    floats = [1000.0, 1.0, 1.0, -0.3, None, 0.6, 0.0, 0.5, 0.65, 0.9, 0.0, 0.2,
              0.6, None, 0.6, 0.6, 1.0, 1.0, -0.6]
    body = bytearray(128)
    for n, value in enumerate(floats):
        if value is not None:
            struct.pack_into(">f", body, 4 * n, value)
    struct.pack_into(">2h", body, 16, 64, 63)
    struct.pack_into(">2h", body, 52, 2048, 0)
    return bytes(body)


def unpack(body):
    fixed = [v / 65536 for v in struct.unpack_from(">7i", body)]
    return fixed, struct.unpack_from(">3h", body, 28)


class TestMeshLighting(unittest.TestCase):
    def test_grassland_comes_out_like_bungies_grassland(self):
        """Myth II's base-game gras: I,J,K 0.95, 1.0, -0.6; 0.1, 1.0, 0.3, 0.95;
        64, 3, 0x4000. TFL's direction is 1.0, 1.0, -0.6."""
        out, warnings = meli.convert(tfl_grassland())
        self.assertEqual(64, len(out))
        self.assertEqual([], warnings)
        fixed, words = unpack(out)
        for got, want in zip(fixed, (1.0, 1.0, -0.6, 0.1, 1.0, 0.3, 0.95)):
            self.assertAlmostEqual(want, got, places=3)
        self.assertEqual((64, 3, 0x4000), words)
        self.assertEqual(bytes(30), out[34:])

    def test_values_are_fixed_point_not_floats(self):
        """Read unconverted, TFL's floats came out as I = 17530 in-engine."""
        fixed, _ = unpack(meli.convert(tfl_grassland())[0])
        self.assertTrue(all(abs(v) <= 1.0 for v in fixed))

    def test_a_body_of_another_size_is_left_alone(self):
        out, warnings = meli.convert(bytes(64))
        self.assertEqual(bytes(64), out)
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
