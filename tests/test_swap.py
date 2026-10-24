"""Tests for swapping the units a Myth II plugin's maps place."""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import codec, mesh, reader, swap, writer  # noqa: E402

from . import fixtures  # noqa: E402


def _palette(entries):
    return b"".join(
        mesh.MarkerPaletteEntry.build(
            type=int(marker_type), flags=0, marker_tag=tag, team_index=-1, netgame_flags=0
        ).encode()
        for marker_type, tag in entries
    )


def _sb_mesh(entries):
    """A Myth II mesh body whose marker palette holds ``entries``, followed by
    a little trailing data so a rewrite that mis-sizes the palette shows up."""
    palette = _palette(entries)
    header = mesh.SBMeshHeader.unpack(bytes(mesh.MESH_HEADER_SIZE)).replace(
        marker_palette_offset=0, marker_palette_size=len(palette)
    )
    return header.encode() + palette + b"trailing map data"


UNIT, SCEN = mesh.MarkerType.UNIT, mesh.MarkerType.SCENERY


class TestSwap(unittest.TestCase):
    def setUp(self):
        self.mono = reader.read_bytes(fixtures.build_sb_mono([
            (b"map one", b"mesh", b"map1", _sb_mesh([(UNIT, b"@0sh"), (UNIT, b"@1cc"), (SCEN, b"@0sh")])),
            (b"map two", b"mesh", b"map2", _sb_mesh([(UNIT, b"@0sh"), (UNIT, b"warr")])),
            (b"a unit", b"unit", b"@0sh", b"not a map"),
        ]), filename="test")

    def test_lists_the_units_the_maps_place_and_where(self):
        used = swap.units_used(self.mono)
        self.assertEqual({b"@0sh", b"@1cc", b"warr"}, set(used))
        self.assertEqual(["map one", "map two"], used[b"@0sh"].maps)
        self.assertEqual(["map one"], used[b"@1cc"].maps)

    def test_scenery_with_the_same_id_is_not_a_unit(self):
        """Palette slots are typed; only unit slots may be swapped."""
        swapped, _ = swap.swap_units(self.mono, {b"@0sh": b"warr"})
        scenery = mesh.MarkerPaletteEntry.unpack(
            swapped.find(b"mesh", b"map1").body,
            mesh.MESH_HEADER_SIZE + 2 * mesh.MARKER_PALETTE_ENTRY_SIZE,
        )
        self.assertEqual(b"@0sh", scenery.marker_tag)

    def test_swaps_unit_slots_in_every_map(self):
        swapped, changed = swap.swap_units(self.mono, {b"@0sh": b"warr"})
        used = swap.units_used(swapped)
        self.assertNotIn(b"@0sh", used)
        self.assertEqual(["map one", "map two"], used[b"warr"].maps)
        self.assertEqual({"map one": 1, "map two": 1}, changed)

    def test_only_the_palette_changes(self):
        swapped, _ = swap.swap_units(self.mono, {b"@0sh": b"warr"})
        before, after = self.mono.find(b"mesh", b"map1").body, swapped.find(b"mesh", b"map1").body
        self.assertEqual(len(before), len(after))
        self.assertTrue(after.endswith(b"trailing map data"))
        self.assertEqual(before[: mesh.MESH_HEADER_SIZE], after[: mesh.MESH_HEADER_SIZE])
        self.assertEqual(b"not a map", swapped.find(b"unit", b"@0sh").body, "non-map tags are untouched")

    def test_an_empty_swap_changes_nothing(self):
        swapped, changed = swap.swap_units(self.mono, {})
        self.assertEqual({}, changed)
        self.assertEqual(writer.pack(self.mono), writer.pack(swapped))

    def test_the_plugin_can_be_given_its_own_name(self):
        swapped, _ = swap.swap_units(self.mono, {b"@0sh": b"warr"}, name="ZZ Swapped")
        self.assertEqual("ZZ Swapped", codec.decode_string(swapped.header.name))
        reread = reader.read_bytes(writer.pack(swapped))
        self.assertEqual("ZZ Swapped", reread.name)

    def test_a_tfl_container_is_refused(self):
        tfl = reader.read_bytes(fixtures.build_tfl_mono(fixtures.MESH_TAGS), filename="t")
        with self.assertRaises(swap.SwapError):
            swap.units_used(tfl)

    def test_ids_must_be_four_bytes(self):
        with self.assertRaises(swap.SwapError):
            swap.swap_units(self.mono, {b"@0sh": b"warrior"})

    def test_swap_file_round_trips_through_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = pathlib.Path(tmp) / "in", pathlib.Path(tmp) / "out"
            src.write_bytes(fixtures.build_sb_mono([
                (b"map one", b"mesh", b"map1", _sb_mesh([(UNIT, b"@0sh")])),
            ]))
            changed, written = swap.swap_file(src, out, {b"@0sh": b"warr"})
            self.assertEqual({"map one": 1}, changed)
            self.assertEqual(written, out.stat().st_size)
            self.assertIn(b"warr", swap.units_used(reader.read(out)))


if __name__ == "__main__":
    unittest.main()
