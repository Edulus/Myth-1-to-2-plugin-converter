"""Tests for the model (`mode`) and geometry (`geom`) body converters."""

import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.convert import plugin as convert_plugin  # noqa: E402
from src.convert.tags import geom, mode  # noqa: E402
from src.idmap import IdMap  # noqa: E402


def tfl_mode(cells, vertex_flags=b"\x00\x00\x00\x07" * 2, permutations=b"p" * 64):
    """A TFL model body: header, vertex flags, permutations, then footprint."""
    footprint = b"".join(struct.pack(">hhhH", x, y, f, 0) for x, y, f in cells)
    head = mode.Model.build(
        flags=0, geometry_tag=b"gm01", geometry_index=0,
        vertex_flags_count=len(vertex_flags) // 4, permutation_count=1, mesh_cell_count=len(cells),
        geometry_vertex_offset=0, geometry_vertex_size=len(vertex_flags), geometry_vertex_ptr=0,
        permutations_offset=len(vertex_flags), permutations_size=len(permutations), permutations_ptr=0,
        mesh_cell_offset=len(vertex_flags) + len(permutations), mesh_cell_size=len(footprint), mesh_cell_ptr=0,
        data_offset=mode.Model.size, data_size=len(vertex_flags) + len(permutations) + len(footprint), data_ptr=0,
    )
    return head.encode() + vertex_flags + permutations + footprint


def footprint(body):
    head = mode.Model.unpack(body)
    at = head.data_offset + head.mesh_cell_offset
    return [struct.unpack_from(">hhh", body, at + i * 8) for i in range(head.mesh_cell_count)]


class TestMode(unittest.TestCase):
    def test_each_cell_becomes_a_2x2_block_in_rows(self):
        converted, warnings = mode.convert(tfl_mode([(3, 5, 7)]))
        self.assertEqual([], warnings)
        self.assertEqual([(6, 10, 7), (7, 10, 7), (6, 11, 7), (7, 11, 7)], footprint(converted))

    def test_cells_are_sorted_like_magmas_ports(self):
        converted, _ = mode.convert(tfl_mode([(1, 0, 1), (0, 1, 2)]))
        self.assertEqual((0, 2, 2), footprint(converted)[0])

    def test_header_sizes_follow_the_footprint(self):
        body = tfl_mode([(0, 0, 1), (1, 0, 1)])
        converted, _ = mode.convert(body)
        head = mode.Model.unpack(converted)
        self.assertEqual(8, head.mesh_cell_count)
        self.assertEqual(64, head.mesh_cell_size)
        self.assertEqual(head.mesh_cell_offset + 64, head.data_size)
        self.assertEqual(head.data_offset + head.data_size, len(converted))
        # Everything before the footprint is untouched.
        self.assertEqual(body[64 : 64 + head.mesh_cell_offset], converted[64 : 64 + head.mesh_cell_offset])

    def test_geometry_reference_follows_the_id_map(self):
        id_map = IdMap()
        id_map.add(b"geom", b"gm01", b"gm02")
        converted, _ = mode.convert(tfl_mode([(0, 0, 0)]), convert_plugin.ConversionContext(id_map=id_map))
        self.assertEqual(b"gm02", mode.Model.unpack(converted).geometry_tag)

    def test_a_short_body_is_reported_not_mangled(self):
        converted, warnings = mode.convert(b"\x01" * 10)
        self.assertEqual(b"\x01" * 10, converted)
        self.assertTrue(warnings)


def tfl_geom(points, center_z=50, extra=b"\x12\x34\x56\x78\x9a\xbc"):
    """A TFL geometry body: 96-byte header, then materials and vertices."""
    materials = b"m" * 64
    vertices = b"".join(struct.pack(">hhh", *p) for p in points)
    head = bytearray(96)
    struct.pack_into(">L4shhhhhhh", head, 0, 0, b"cr01", 1, len(points), 0, 0, 10, 20, center_z)
    head[22:28] = extra
    struct.pack_into(
        ">15L", head, 28,
        0, len(materials), 0,
        len(materials), len(vertices), 0,
        0, 0, 0,
        0, 0, 0,
        96, len(materials) + len(vertices), 0,
    )
    return bytes(head) + materials + vertices


class TestGeom(unittest.TestCase):
    POINTS = [(10, -20, 0), (300, 40, 900), (-5, 7, 450)]

    def test_header_grows_to_128_and_data_is_copied(self):
        body = tfl_geom(self.POINTS)
        converted, warnings = geom.convert(body)
        self.assertEqual([], warnings)
        self.assertEqual(128, geom.SBGeom.unpack(converted).data_offset)
        self.assertEqual(body[96:], converted[128:])

    def test_bounding_box_is_the_vertices_extent(self):
        converted, _ = geom.convert(tfl_geom(self.POINTS))
        h = geom.SBGeom.unpack(converted)
        self.assertEqual((-5, -20, 0), (h.bounds_min_x, h.bounds_min_y, h.bounds_min_z))
        self.assertEqual((300, 40, 900), (h.bounds_max_x, h.bounds_max_y, h.bounds_max_z))

    def test_center_z_is_zeroed_and_the_rest_of_the_header_kept(self):
        body = tfl_geom(self.POINTS)
        converted, _ = geom.convert(body)
        self.assertEqual(0, geom.SBGeom.unpack(converted).center_z)
        self.assertEqual(body[22:28], converted[22:28])
        self.assertEqual(body[:20], converted[:20])

    def test_collection_reference_follows_the_id_map(self):
        id_map = IdMap()
        id_map.add(b"core", b"cr01", b"cr02")
        converted, _ = geom.convert(tfl_geom(self.POINTS), convert_plugin.ConversionContext(id_map=id_map))
        self.assertEqual(b"cr02", converted[4:8])

    def test_a_short_body_is_reported_not_mangled(self):
        converted, warnings = geom.convert(b"\x01" * 50)
        self.assertEqual(b"\x01" * 50, converted)
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
