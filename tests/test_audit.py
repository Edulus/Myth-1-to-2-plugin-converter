"""Tests for the field-by-field change list (`src.audit`)."""

import csv
import io
import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import reader  # noqa: E402
from src.convert import plugin as convert_plugin  # noqa: E402

from . import fixtures  # noqa: E402
from .test_mons import _tfl_mons_body  # noqa: E402


class TestChangeList(unittest.TestCase):
    def setUp(self):
        body = _tfl_mons_body(collection_tag=b"trra", maximum_vitality=7680,
                              object_scale_lower_bound=357, object_scale_delta=28)
        tfl = reader.read_bytes(fixtures.build_tfl_mono([(b"trow", b"mons", b"trow", body)]))
        _, report = convert_plugin.convert_container(tfl)
        self.rows = list(csv.DictReader(io.StringIO(report.audit_csv())))

    def row(self, tag_type, field):
        return next(r for r in self.rows if r["tag type"] == tag_type and r["field"] == field)

    def test_every_myth_ii_monster_field_is_listed(self):
        from src import mons
        listed = {r["field"] for r in self.rows if r["tag type"] == "mons"}
        self.assertTrue(set(mons.SBMonsHeader.names) <= listed)

    def test_a_per_unit_value_says_so(self):
        r = self.row("mons", "pathfinding_radius")
        self.assertEqual(("(not in TFL)", "154", "Myth II only: per unit"),
                         (r["value in TFL"], r["value in Myth II"], r["what happened"]))

    def test_a_dropped_field_shows_its_tfl_value(self):
        r = self.row("mons", "maximum_vitality")
        self.assertEqual(("7680", "moved"), (r["value in TFL"], r["what happened"]))

    def test_the_objects_scale_shows_both_values_and_the_rule(self):
        r = self.row("obje", "scale lower bound")
        self.assertEqual("357 (1.395)", r["value in TFL"])
        self.assertEqual("260 (1.016)", r["value in Myth II"])
        self.assertIn("0.728", r["why"])


if __name__ == "__main__":
    unittest.main()
