"""The browser unit swapper's Python half."""

import io
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import reader, swap, webswap  # noqa: E402

from .test_swapstream import _Files  # noqa: E402


class TestScan(_Files):
    def scan(self):
        return webswap.scan(self.maps_path, [self.tagset_path], self.dir)

    def test_describes_the_units_the_maps_place(self):
        answer = self.scan()
        by_id = {u["id"]: u for u in answer["units"]}
        self.assertEqual({"@0sh", "@1cc", "warr"}, set(by_id))
        self.assertEqual(2, by_id["@0sh"]["maps"])
        self.assertEqual("@04-sergeant", by_id["@0sh"]["name"])
        self.assertEqual("@", by_id["@0sh"]["side"])
        self.assertEqual("maps", answer["name"])
        self.assertEqual(2, answer["maps"])

    def test_offers_the_base_games_units_and_says_which_the_tagset_redefined(self):
        stock = {u["id"]: u for u in self.scan()["choices"]["stock"]}
        self.assertEqual({"wam1", "ghol"}, set(stock))
        self.assertTrue(stock["wam1"]["restored"])
        self.assertFalse(stock["ghol"]["restored"])

    def test_offers_the_tagsets_own_units_too(self):
        own = {u["id"] for u in self.scan()["choices"]["tagset"]}
        self.assertEqual({"@0sh"}, own)

    def test_a_missing_tagset_is_explained(self):
        with self.assertRaises(webswap.Problem) as ctx:
            webswap.scan(self.maps_path, [], self.dir)
        self.assertIn("tagset", str(ctx.exception))

    def test_a_folder_without_myth_ii_files_is_explained(self):
        empty = self.dir / "elsewhere"
        empty.mkdir()
        with self.assertRaises(webswap.Problem) as ctx:
            webswap.scan(self.maps_path, [self.tagset_path], empty)
        self.assertIn("Myth II", str(ctx.exception))

    def test_a_fallen_lords_file_is_explained(self):
        from . import fixtures
        tfl = self.dir / "tfl"
        tfl.write_bytes(fixtures.build_tfl_mono([(b"x", b"text", b"abcd", b"body")]))
        with self.assertRaises(webswap.Problem) as ctx:
            webswap.scan(tfl, [self.tagset_path], self.dir)
        self.assertIn("Fallen Lords", str(ctx.exception))


class TestBuild(_Files):
    def build(self, swaps, name="ZZ my swap"):
        out = io.BytesIO()
        answer = webswap.build(self.maps_path, [self.tagset_path], self.dir, swaps, name, out.write)
        return answer, out.getvalue()

    def test_writes_a_plugin_with_the_units_swapped_and_restored(self):
        answer, data = self.build({"@0sh": "wam1"})
        new = reader.read_bytes(data)
        self.assertEqual("ZZ my swap", new.name)
        self.assertEqual(len(data), answer["bytes"])
        self.assertEqual(1, answer["restored"])
        self.assertEqual(1, answer["swapped"])
        self.assertEqual(2, answer["maps"])
        self.assertIn(b"wam1", swap.units_used(new))
        self.assertTrue(new.find(b"unit", b"wam1").body.startswith(b"wara"))

    def test_choosing_nothing_is_explained(self):
        with self.assertRaises(webswap.Problem):
            self.build({"@0sh": ""})
        with self.assertRaises(webswap.Problem):
            self.build({"@0sh": "@0sh"})

    def test_a_unit_id_must_be_four_characters(self):
        with self.assertRaises(webswap.Problem):
            self.build({"@0sh": "warrior"})

    def test_a_replacement_that_is_not_in_the_base_game_carries_nothing(self):
        answer, data = self.build({"warr": "@0sh"})
        self.assertEqual(0, answer["restored"])
        self.assertIn(b"@0sh", swap.units_used(reader.read_bytes(data)))

    def test_the_filename_is_cleaned_and_kept_to_32_characters(self):
        self.assertEqual("ZZ Swapped units", webswap.output_name(""))
        self.assertEqual("ab", webswap.output_name('a<b>:"/\|?*'))
        long = "x" * 50
        self.assertEqual(32, len(webswap.output_name(long)))
        answer, data = self.build({"@0sh": "wam1"}, name="a/b" + "y" * 40)
        self.assertLessEqual(len(answer["filename"]), 32)
        self.assertEqual(answer["filename"], reader.read_bytes(data).name)


if __name__ == "__main__":
    unittest.main()
