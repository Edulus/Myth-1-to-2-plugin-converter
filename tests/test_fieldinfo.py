"""Tests for the mesh field semantics taken from the Fear manual.

These pin down the two things `src/fieldinfo.py` exists to do: turn a stored
scaled integer into a quantity a map-maker would recognise, and say when a
value is outside what the manual calls usual.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import fieldinfo  # noqa: E402
from src.convert.tags import mesh as mesh_converter  # noqa: E402


class TestScaling(unittest.TestCase):
    def test_short_fixed_fraction(self):
        """229 is not an opaque number: it is 0.895 of full intensity."""
        info = fieldinfo.get("dark_fraction")
        self.assertAlmostEqual(0.89453125, info.scaled(229))
        self.assertEqual("0.895 of 1.0", info.describe(229))

    def test_fixed_fraction(self):
        info = fieldinfo.get("transition_point")
        self.assertEqual("0.95 of 1.0", info.describe(62259))

    def test_world_distance(self):
        info = fieldinfo.get("ceiling_height")
        self.assertEqual("4 world units", info.describe(2048))

    def test_float_artefacts_are_rounded_away(self):
        """reverb_decay_time is a float32, so its repr is 1.4930000305175781 --
        precision that is not really there and should not be shown."""
        info = fieldinfo.get("reverb_decay_time")
        self.assertEqual("1.493", info.describe(1.4930000305175781))

    def test_unscaled_fields_render_plainly(self):
        info = fieldinfo.get("reverb_environment")
        self.assertEqual("0", info.describe(0))

    def test_unknown_field_has_no_info(self):
        self.assertIsNone(fieldinfo.get("not_a_real_field"))


class TestRangeChecking(unittest.TestCase):
    def test_value_inside_the_documented_range_is_quiet(self):
        # 0.75-0.90 per the manual; 229/256 = 0.895.
        self.assertIsNone(fieldinfo.check("dark_fraction", 229))

    def test_value_outside_the_range_is_reported(self):
        warning = fieldinfo.check("dark_fraction", 64)  # 0.25, well under 0.75
        self.assertIsNotNone(warning)
        self.assertIn("Dark Color Fraction", warning)
        self.assertIn("not an error", warning, "advice, not enforcement")

    def test_documented_unset_sentinel_is_not_flagged(self):
        """minimum_zoom_factor's valid range is negative, but 0 means unset and
        is what every mesh in the reference port uses."""
        self.assertIsNone(fieldinfo.check("minimum_zoom_factor", 0.0))
        self.assertIsNotNone(fieldinfo.check("minimum_zoom_factor", 12.0))

    def test_fields_without_a_documented_range_are_never_flagged(self):
        for value in (0, 1, 999999, -5):
            self.assertIsNone(fieldinfo.check("transition_point", value))

    def test_unknown_field_is_never_flagged(self):
        self.assertIsNone(fieldinfo.check("not_a_real_field", 1))


class TestAgainstOurOwnDefaults(unittest.TestCase):
    """The manual is a second opinion on the values measured in section 12."""

    def test_every_documented_field_is_a_real_synthesised_field(self):
        """Guards against documenting a field the converter does not set --
        which would put text in the UI next to a control that does nothing.
        Checked against SYNTHESISED, which covers both the header fields and
        the per-cell ones like media_height."""
        unknown = set(fieldinfo.MESH_FIELDS) - set(mesh_converter.SYNTHESISED)
        self.assertEqual(set(), unknown)

    def test_the_numeric_defaults_are_all_documented(self):
        """Every value a user is asked to judge should come with an explanation."""
        numeric = {
            name
            for name, value in mesh_converter.SYNTHESISED.items()
            if isinstance(value, (int, float, bool))
        }
        # Structural bookkeeping is computed, not chosen, so it needs no prose.
        structural = {"connectors_offset", "editor_data_size", "editor_data_offset"}
        undocumented = numeric - set(fieldinfo.MESH_FIELDS) - structural
        self.assertEqual(set(), undocumented)

    def test_measured_defaults_mostly_agree_with_the_manual(self):
        """Only light_fraction should trip the range check -- a known, recorded
        disagreement between the manual and what real ports actually ship."""
        tripped = {
            name
            for name, value in mesh_converter.SYNTHESISED.items()
            if isinstance(value, (int, float, bool))
            and fieldinfo.check(name, value)
        }
        self.assertEqual({"light_fraction"}, tripped)


if __name__ == "__main__":
    unittest.main()
