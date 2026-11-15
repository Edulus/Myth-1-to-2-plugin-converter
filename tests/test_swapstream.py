"""The streaming swap must do exactly what `swap` does, on the same inputs."""

import io
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import codec, formats, reader, swap, swapstream, writer  # noqa: E402

from . import fixtures  # noqa: E402
from .test_swap import UNIT, SCEN, _sb_mesh  # noqa: E402


class _Files(unittest.TestCase):
    """The same situation as `test_swap.TestRestoreStock`, as real files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        (self.dir / "tags").mkdir()

        def unit(mons):
            return mons + b"core" + bytes(120)

        self.stock_path = self.dir / "tags" / "small install"
        self.stock_path.write_bytes(fixtures.build_sb_mono([
            (b"M2-warrior", b"unit", b"wam1", unit(b"wara")),
            (b"M2-ghol", b"unit", b"ghol", unit(b"ghmo")),
            (b"warrior monster", b"mons", b"wara", b"stock warrior monster"),
        ]))
        self.tagset_path = self.dir / "tagset"
        self.tagset_path.write_bytes(fixtures.build_sb_mono([
            (b"M2-warrior", b"unit", b"wam1", unit(b"_zuv")),
            (b"M2-ghol", b"unit", b"ghol", unit(b"ghmo")),
            (b"union veteran", b"mons", b"_zuv", b"civil war soldier"),
            (b"@04-sergeant", b"unit", b"@0sh", unit(b"_zuv")),
        ]))
        self.maps_path = self.dir / "maps"
        self.maps_path.write_bytes(fixtures.build_sb_mono([
            (b"map one", b"mesh", b"map1", _sb_mesh([(UNIT, b"@0sh"), (UNIT, b"@1cc"), (SCEN, b"@0sh")])),
            (b"map two", b"mesh", b"map2", _sb_mesh([(UNIT, b"@0sh"), (UNIT, b"warr")])),
            (b"a unit", b"unit", b"@0sh", b"not a map"),
        ], entrypoints=[
            fixtures.entrypoint(b"one", b"map one", b"map1"),
        ] if hasattr(fixtures, "entrypoint") else (), body_gap=64, name=b"civil war maps"))

    def tearDown(self):
        self.tmp.cleanup()

    def stream(self, swaps, restore_units=(), name="ZZ swapped"):
        maps = swapstream.LazyContainer(self.maps_path)
        tagset = swapstream.Layered([self.tagset_path])
        stock = swapstream.Layered([self.stock_path])
        try:
            patches, changed = swapstream.palette_patches(maps, swaps)
            keys, unchanged = swapstream.Restorer(tagset, stock).closure(restore_units)
            carry = [
                (stock.header(k), stock.header(k).tag_data_size, lambda k=k: stock.body(k))
                for k in sorted(keys)
            ]
            out = io.BytesIO()
            written, added = swapstream.write_swapped(maps, out.write, patches, carry, name)
            return out.getvalue(), written, added, changed, unchanged
        finally:
            for c in (maps, tagset, stock):
                c.close() if hasattr(c, "close") else None


class TestLazyReading(_Files):
    def test_units_used_matches_swap(self):
        lazy = swapstream.LazyContainer(self.maps_path)
        try:
            mine = {k: v.maps for k, v in swapstream.units_used(lazy).items()}
        finally:
            lazy.close()
        theirs = {k: v.maps for k, v in swap.units_used(reader.read(self.maps_path)).items()}
        self.assertEqual(theirs, mine)

    def test_a_tfl_container_is_refused(self):
        path = self.dir / "tfl"
        path.write_bytes(fixtures.build_tfl_mono([(b"x", b"text", b"abcd", b"body")]))
        with self.assertRaises(swap.SwapError):
            swapstream.LazyContainer(path)

    def test_the_layered_tags_let_the_last_container_win(self):
        later = self.dir / "later"
        later.write_bytes(fixtures.build_sb_mono([(b"M2-ghol", b"unit", b"ghol", b"later")]))
        layered = swapstream.Layered([self.stock_path, later])
        try:
            self.assertEqual(b"later", layered.body((b"unit", b"ghol")))
        finally:
            layered.close()


class TestRestorer(_Files):
    def test_the_same_tags_are_carried_as_swap_carries(self):
        stock = swap.tag_index([self.stock_path])
        tagset = swap.tag_index([self.tagset_path])
        modified = swap.modified_stock_tags(tagset, stock)
        for units in ([b"wam1"], [b"ghol"], [b"wam1", b"ghol"]):
            expected = swap.restore_closure(units, stock, modified)
            lazy_tagset, lazy_stock = swapstream.Layered([self.tagset_path]), swapstream.Layered([self.stock_path])
            try:
                self.assertEqual(expected, swapstream.Restorer(lazy_tagset, lazy_stock).closure(units))
            finally:
                lazy_tagset.close(), lazy_stock.close()

    def test_a_unit_that_is_not_in_the_base_game_is_refused(self):
        with self.assertRaises(swap.SwapError):
            self.stream({}, restore_units=[b"@0sh"])


class TestWriteSwapped(_Files):
    swaps = {b"@0sh": b"wam1"}

    def old(self, restore):
        mono = reader.read(self.maps_path)
        swapped, changed = swap.swap_units(mono, self.swaps, name="ZZ swapped")
        report = None
        if restore:
            swapped, report = swap.restore_stock_units(swapped, [b"wam1"], [self.tagset_path], self.dir)
        return swapped, changed, report

    def test_without_restoring_it_is_byte_identical_to_the_old_pack(self):
        data, written, added, changed, _ = self.stream(self.swaps)
        old, old_changed, _ = self.old(restore=False)
        self.assertEqual(writer.pack(old, preserve_layout=True), data)
        self.assertEqual((len(data), 0, old_changed), (written, added, changed))

    def test_restoring_gives_the_same_tags_as_the_old_path(self):
        data, written, added, changed, _ = self.stream(self.swaps, restore_units=[b"wam1"])
        old, old_changed, report = self.old(restore=True)
        new = reader.read_bytes(data)
        self.assertEqual(report["carried"], added)
        self.assertEqual(len(data), written)
        self.assertEqual(len(data), new.header.size)
        self.assertEqual({t.key: t.body for t in old.tags}, {t.key: t.body for t in new.tags})
        self.assertEqual(old.entrypoints, new.entrypoints)
        self.assertEqual(old_changed, changed)
        self.assertEqual("ZZ swapped", new.name)

    def test_the_restored_unit_is_the_base_games(self):
        data, *_ = self.stream(self.swaps, restore_units=[b"wam1"])
        new = reader.read_bytes(data)
        self.assertTrue(new.find(b"unit", b"wam1").body.startswith(b"wara"))
        self.assertIn(b"wam1", swap.units_used(new))

    def test_restored_tags_get_unique_identifiers(self):
        data, *_ = self.stream(self.swaps, restore_units=[b"wam1"])
        tags = reader.read_bytes(data).tags
        original = {t.header.identifier for t in reader.read(self.maps_path).tags}
        added = [t.header.identifier for t in tags if t.key == (b"unit", b"wam1")]
        self.assertEqual(1, len(added))
        self.assertNotIn(added[0], original)

    def test_the_plugins_own_tag_beats_a_carried_one(self):
        maps = swapstream.LazyContainer(self.maps_path)
        stock = swapstream.Layered([self.stock_path])
        try:
            record = stock.header((b"unit", b"wam1"))
            mine = maps.records[2].replace(tag_id=b"wam1")  # same key as the carried tag
            # The maps plugin holds no wam1, so it is added once, never twice.
            carry = [(record, record.tag_data_size, lambda: stock.body((b"unit", b"wam1")))] * 2
            out = io.BytesIO()
            _, added = swapstream.write_swapped(maps, out.write, (), carry)
            self.assertEqual(1, added)
        finally:
            maps.close(), stock.close()

    def test_a_patch_spanning_a_chunk_boundary_is_applied_whole(self):
        old_chunk = swapstream.CHUNK
        swapstream.CHUNK = 7  # tiny chunks, so patches straddle them
        try:
            data, *_ = self.stream(self.swaps, restore_units=[b"wam1"])
        finally:
            swapstream.CHUNK = old_chunk
        reference, *_ = self.stream(self.swaps, restore_units=[b"wam1"])
        self.assertEqual(reference, data)


if __name__ == "__main__":
    unittest.main()
