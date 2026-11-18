"""Tests for the compare-with-a-reference command."""

import contextlib
import csv
import io
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import cli, compare, reader  # noqa: E402

from . import fixtures  # noqa: E402

NONE = b"\xff\xff\xff\xff"


def _tfl(tags):
    return reader.read_bytes(fixtures.build_tfl_mono(tags))


def _sb(tags):
    return reader.read_bytes(fixtures.build_sb_mono(tags))


def _amso(slots, radius=b"\x00\x10"):
    """A 64-byte amso-like body: zeros, six sound slots at 12..36, a value at 36."""
    body = bytearray(64)
    for i, slot in enumerate(slots):
        body[12 + 4 * i : 16 + 4 * i] = slot
    body[36:38] = radius
    return bytes(body)


def _amso_pair(n, ref_empty=NONE):
    """Ours: slots 0-1 name sounds, 2-5 zero. Ref: the same, unused slots as ``ref_empty``."""
    used = [b"snd%d" % n, b"snd%d" % (n + 1)]
    ours = _amso(used + [bytes(4)] * 4)
    ref = _amso(used + [ref_empty] * 4)
    return ours, ref


class TestPairing(unittest.TestCase):
    def test_pairs_by_type_and_id(self):
        ours = _tfl([(b"a", b"amso", b"0001", b"x" * 8), (b"b", b"amso", b"0002", b"y" * 8)])
        ref = _sb([(b"a", b"amso", b"0001", b"x" * 8), (b"c", b"amso", b"0003", b"z" * 8)])
        pairs, ours_only, ref_only = compare.pair_tags([ours], [ref])
        self.assertEqual([(b"0001", b"0001", "id")], [(a.tag_id, b.tag_id, h) for a, b, h in pairs])
        self.assertEqual([b"0002"], [t.tag_id for t in ours_only])
        self.assertEqual([b"0003"], [t.tag_id for t in ref_only])

    def test_by_name_pairs_what_ids_left_unpaired(self):
        ours = _tfl([(b"torch", b"amso", b"0001", b"x" * 8)])
        ref = _sb([(b"torch", b"amso", b"zz01", b"x" * 8), (b"torch", b"soun", b"zz02", b"q")])
        pairs, _, _ = compare.pair_tags([ours], [ref])
        self.assertEqual([], pairs)
        pairs, ours_only, ref_only = compare.pair_tags([ours], [ref], by_name=True)
        self.assertEqual([(b"0001", b"zz01", "name")], [(a.tag_id, b.tag_id, h) for a, b, h in pairs])
        self.assertEqual([], ours_only)
        self.assertEqual([b"soun"], [t.tag_type for t in ref_only])  # name match is per type

    def test_first_container_on_a_side_wins(self):
        first = _tfl([(b"a", b"amso", b"0001", b"first...")])
        second = _tfl([(b"a", b"amso", b"0001", b"second..")])
        ref = _sb([(b"a", b"amso", b"0001", b"first...")])
        result = compare.compare([first, second], [ref])
        self.assertEqual(1, result.get("amso").identical)

    def test_types_filter(self):
        ours = _tfl([(b"a", b"amso", b"0001", b"x"), (b"b", b"soun", b"0001", b"y")])
        ref = _sb([(b"a", b"amso", b"0001", b"x"), (b"b", b"soun", b"0001", b"y")])
        result = compare.compare([ours], [ref], types=compare.parse_types("soun"))
        self.assertEqual([b"soun"], list(result.types))


class TestCounts(unittest.TestCase):
    def test_identical_and_size_changes(self):
        ours = _tfl([
            (b"a", b"phys", b"0001", b"same" * 4),
            (b"b", b"phys", b"0002", bytes(96)),
            (b"c", b"phys", b"0003", bytes(96)),
            (b"d", b"phys", b"0004", bytes(8)),
        ])
        ref = _sb([
            (b"a", b"phys", b"0001", b"same" * 4),
            (b"b", b"phys", b"0002", bytes(128)),
            (b"c", b"phys", b"0003", bytes(128)),
            (b"d", b"phys", b"0004", bytes(16)),
        ])
        s = compare.compare([ours], [ref]).get("phys")
        self.assertEqual(4, s.pairs)
        self.assertEqual(1, s.same_size)
        self.assertEqual(1, s.identical)
        self.assertEqual({(96, 128): 2, (8, 16): 1}, dict(s.size_changes))
        self.assertEqual([], s.ranges)


class TestRanges(unittest.TestCase):
    def setUp(self):
        ours_tags, ref_tags = [], []
        for n in range(10):
            ours, ref = _amso_pair(n)
            if n < 2:  # two of ten keep zeros in the reference too
                ref = ours
            # Byte 50 differs in 3 of 10 pairs: below a 0.6 threshold.
            if n in (2, 3, 4):
                ref = ref[:50] + b"\x77" + ref[51:]
            tag_id = b"%04d" % n
            ours_tags.append((b"amso %d" % n, b"amso", tag_id, ours))
            ref_tags.append((b"amso %d" % n, b"amso", tag_id, ref))
        self.ours = _tfl(ours_tags)
        self.ref = _sb(ref_tags)
        self.result = compare.compare([self.ours], [self.ref], threshold=0.6)

    def test_systematic_difference_is_one_range(self):
        s = self.result.get("amso")
        self.assertEqual(10, s.same_size)
        self.assertEqual(2, s.identical)
        self.assertEqual([(20, 36)], [(r.start, r.end) for r in s.ranges])
        rng = s.ranges[0]
        self.assertEqual(8, rng.peak)
        self.assertEqual(10, rng.covering)
        top = rng.transitions[0]
        self.assertEqual(((bytes(16), NONE * 4), 8), top)
        self.assertEqual(((bytes(16), bytes(16)), 2), rng.transitions[1])

    def test_below_threshold_not_reported(self):
        s = self.result.get("amso")
        self.assertFalse(any(r.start <= 50 < r.end for r in s.ranges))
        # ... but a lower threshold picks it up.
        low = compare.compare([self.ours], [self.ref], threshold=0.3).get("amso")
        self.assertIn((50, 51), [(r.start, r.end) for r in low.ranges])

    def test_range_named_from_layout(self):
        rng = self.result.get("amso").ranges[0]
        self.assertEqual(
            ["sound_tags[2]", "sound_tags[3]", "sound_tags[4]", "sound_tags[5]"], rng.fields
        )

    def test_gap_of_one_byte_merges(self):
        # Every other byte differs (16-bit fields whose low byte goes 0 -> 1).
        ours = bytes(16)
        ref = bytes([0, 1] * 8)
        tags_a = [(b"g%d" % n, b"lpgr", b"%04d" % n, ours) for n in range(5)]
        tags_b = [(b"g%d" % n, b"lpgr", b"%04d" % n, ref) for n in range(5)]
        s = compare.compare([_tfl(tags_a)], [_sb(tags_b)]).get("lpgr")
        self.assertEqual([(1, 16)], [(r.start, r.end) for r in s.ranges])
        self.assertEqual(8, s.ranges[0].differing_bytes)

    def test_report_lines(self):
        lines = compare.format_report(self.result, ["ours.gor"], ["ref"])
        text = "\n".join(lines)
        self.assertIn("20-36", text)
        self.assertIn("00000000000000000000000000000000 -> " + "ff" * 16 + "  8/10", text)
        self.assertTrue(text.isascii())

    def test_field_registry_for_struct_types(self):
        # mons is declared through its codec.Struct; offset 0 is the flags field.
        self.assertEqual(["flags"], compare.field_names(b"mons", 0, 4))
        self.assertEqual([], compare.field_names(b"zzzz", 0, 4))

    def test_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "out.csv"
            compare.write_csv(self.result, path)
            rows = list(csv.DictReader(path.open(newline="")))
        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual(("amso", "20", "36"), (row["type"], row["start"], row["end"]))
        self.assertEqual("8", row["differing_pairs"])
        self.assertEqual("10", row["same_size_pairs"])
        self.assertEqual("ff" * 16, row["top_ref"])
        self.assertEqual("8", row["top_count"])


class TestCli(unittest.TestCase):
    def test_compare_command(self):
        ours_tags, ref_tags = [], []
        for n in range(4):
            ours, ref = _amso_pair(n)
            ours_tags.append((b"a%d" % n, b"amso", b"%04d" % n, ours))
            ref_tags.append((b"a%d" % n, b"amso", b"%04d" % n, ref))
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            (tmp / "ours.gor").write_bytes(fixtures.build_tfl_mono(ours_tags))
            (tmp / "ref").write_bytes(fixtures.build_sb_mono(ref_tags))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cli.main([
                    "compare", "--ours", str(tmp / "ours.gor"), "--ref", str(tmp / "ref"),
                    "--types", "amso", "--detail", "amso", "--csv", str(tmp / "r.csv"),
                ])
            self.assertEqual(0, code)
            self.assertTrue((tmp / "r.csv").exists())
        text = out.getvalue()
        self.assertIn("amso", text)
        self.assertIn("20-36", text)
        self.assertIn("4/4", text)


if __name__ == "__main__":
    unittest.main()
