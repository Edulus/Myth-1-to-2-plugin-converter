"""Tests for object (`obje`) conversion and the per-monster objects."""

import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import mons, reader  # noqa: E402
from src.convert import plugin as convert_plugin  # noqa: E402
from src.convert.tags import obje  # noqa: E402

from . import fixtures  # noqa: E402
from .test_mons import _tfl_mons_body  # noqa: E402


def unpack(body):
    flags, gravity, elasticity, terminal, vit, vit_d, scale, scale_d = struct.unpack_from(">8h", body)
    effects = struct.unpack_from(">9h", body, 16)
    return flags, (gravity, elasticity, terminal), (vit, vit_d), (scale, scale_d), effects


class TestObjectConversion(unittest.TestCase):
    def test_physics_kept_and_scale_never_zero(self):
        """A TFL object read as Myth II's has scale 0 -- in-engine, every unit
        and tree was invisible."""
        converted, warnings = obje.convert(struct.pack(">hhh", -2, 0x80, 0) + bytes(10))
        self.assertEqual(64, len(converted))
        self.assertEqual([], warnings)
        flags, physics, vitality, scale, effects = unpack(converted)
        self.assertEqual((-2, 0x80, 0), physics)
        self.assertEqual((0x100, 0), scale)
        self.assertEqual((0x100, 0), vitality)
        self.assertEqual((0x100,) * 9, effects)

    def test_a_body_of_another_size_is_left_alone(self):
        converted, warnings = obje.convert(bytes(64))
        self.assertEqual(bytes(64), converted)
        self.assertTrue(warnings)


class TestMonsterObjects(unittest.TestCase):
    def convert(self, **mons_fields):
        tags = [(b"warrior", b"mons", b"warr", _tfl_mons_body(**mons_fields))]
        tfl = reader.read_bytes(fixtures.build_tfl_mono(tags))
        return convert_plugin.convert_container(tfl)

    def test_each_monster_gets_its_own_object_with_its_tfl_values(self):
        effects = struct.pack(">7h", 256, 256, 128, 256, 256, 288, 256) + bytes(10)
        sb, report = self.convert(
            maximum_vitality=1408,
            object_scale_lower_bound=239,
            object_scale_delta=18,
            effect_modifiers=effects,
        )
        warrior = next(t for t in sb.tags if t.tag_type == b"mons")
        object_tag = mons.SBMonsHeader.unpack(warrior.body).object_tag
        objects = {t.tag_id: t.body for t in sb.tags if t.tag_type == b"obje"}
        self.assertIn(object_tag, objects)

        flags, _physics, vitality, scale, carried = unpack(objects[object_tag])
        self.assertEqual(3, flags)
        self.assertEqual((1408, 0), vitality)
        self.assertEqual((239, 18), scale)
        self.assertEqual((256, 256, 128, 256, 256, 288, 256, 256, 256), carried)

    def test_carried_fields_are_no_longer_reported_as_dropped(self):
        _, report = self.convert(maximum_vitality=1408)
        warnings = [w for o in report.outcomes if o.tag_type == b"mons" for w in o.warnings]
        self.assertFalse([w for w in warnings if "maximum_vitality" in w])

    def test_an_object_id_already_taken_is_not_reused(self):
        self.assertEqual(b"warr", convert_plugin._free_id(b"warr", set()))
        self.assertNotEqual(b"warr", convert_plugin._free_id(b"warr", {b"warr"}))


if __name__ == "__main__":
    unittest.main()
