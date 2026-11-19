"""Tests for mons/unit header parsing and TFL -> Myth II body conversion."""

import os
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import codec, formats, idmap, mons, reader  # noqa: E402
from src.convert import plugin as convert_plugin  # noqa: E402
from src.convert.tags import mons as mons_converter  # noqa: E402
from src.convert.tags import unit as unit_converter  # noqa: E402


# --- a minimal, structurally valid TFL mons body, built from the real struct
# definitions rather than independently hand-picked offsets (as `mesh_body` is)
# -- `src/mons.py`'s field layout is itself the thing under test elsewhere
# (against a real 93 MB TFL plugin, see TestRealPluginMonsBodies below), so
# reusing it here is no more circular than the mesh tests reusing
# `mesh.MapActionHead.build` for their own sub-structures.
def _tfl_mons_body(**overrides):
    values = {name: 0 for name in mons.TFLMonsHeader.names}
    for field in mons.TFLMonsHeader.names:
        if field.endswith("_tag"):
            values[field] = b"\xff\xff\xff\xff"
    values["sequence_indexes"] = bytes(32)
    values["terrain_costs"] = bytes(16)
    values["movement_modifiers"] = bytes(16)
    values["attacks"] = bytes(128)
    values["sound_tags"] = b"\xff\xff\xff\xff" * 10
    values["sound_types"] = bytes(10)
    values["effect_modifiers"] = bytes(24)
    values.update(overrides)
    return mons.TFLMonsHeader.build(**values).encode()


class TestMonsHeaderLayout(unittest.TestCase):
    def test_header_sizes(self):
        """TFL grew from 512 to 1024 bytes -- unlike mesh, this one really did
        change size, so a naive pass-through corrupts the tag directory too."""
        self.assertEqual(512, mons.TFLMonsHeader.size)
        self.assertEqual(1024, mons.SBMonsHeader.size)
        self.assertEqual(mons.MONS_HEADER_SIZE[formats.TFL], mons.TFLMonsHeader.size)
        self.assertEqual(mons.MONS_HEADER_SIZE[formats.SB], mons.SBMonsHeader.size)

    def test_attack_and_sequence_sizes(self):
        self.assertEqual(8, mons.AttackSequence.size)
        self.assertEqual(32, mons.TFLAttackDef.size)
        self.assertEqual(64, mons.SBAttackDef.size)
        self.assertEqual(8, mons.UnitTag.size)

    def test_unit_tag_is_identical_in_both_games(self):
        """mythextract declares a single UnitTagFmt with no TFL/SB split."""
        self.assertEqual(("mons", "core"), mons.UnitTag.names)

    def test_size_and_intelligence_share_a_slot_under_different_names(self):
        tfl_fields = set(mons.TFLMonsHeader.names)
        sb_fields = set(mons.SBMonsHeader.names)
        self.assertIn("intelligence", tfl_fields)
        self.assertNotIn("intelligence", sb_fields)
        self.assertIn("size", sb_fields)
        self.assertNotIn("size", tfl_fields)

    def test_sb_only_fields_are_not_in_tfl(self):
        tfl_fields = set(mons.TFLMonsHeader.names)
        for field in (
            "maximum_mana", "berserk_vitality", "pathfinding_radius",
            "map_action_tag", "use_attack_frequency",
        ):
            self.assertNotIn(field, tfl_fields)

    def test_tfl_only_fields_are_not_in_sb(self):
        sb_fields = set(mons.SBMonsHeader.names)
        for field in (
            "visual_distance", "maximum_vitality", "melee_power", "effect_modifiers",
        ):
            self.assertNotIn(field, sb_fields)

    def test_parses_a_body(self):
        body = _tfl_mons_body(number_of_attacks=1)
        header = mons.parse_header(body, formats.TFL)
        self.assertEqual(1, header.number_of_attacks)

    def test_rejects_a_truncated_body(self):
        with self.assertRaises(ValueError):
            mons.parse_header(b"\0" * 100, formats.TFL)

    def test_referenced_tags_skips_unset_ids(self):
        body = _tfl_mons_body(object_tag=b"obj1")
        header = mons.parse_header(body, formats.TFL)
        found = {field: (t, v) for t, v, field in mons.referenced_tags(header)}
        self.assertEqual((b"obje", b"obj1"), found["object_tag"])
        self.assertNotIn("collection_tag", found, "still unset (0xFFFFFFFF)")

    def test_sound_tag_refs_skips_unset_slots(self):
        sound_tags = b"soa1" + b"\xff\xff\xff\xff" * 9
        self.assertEqual([b"soa1"], mons.sound_tag_refs(sound_tags))


class TestAttackConversion(unittest.TestCase):
    def _tfl_attack(self, **overrides):
        values = dict(
            miss_fraction=0, flags=0, projectile_tag=b"proj",
            minimum_range=0, maximum_range=100, sequence_index=0,
            repetitions=1, initial_velocity_lower_bound=0,
            initial_velocity_delta=0, initial_velocity_error=0,
            recovery_time=30, elevated_sequence_index=-1,
            declined_sequence_index=-1, recovery_time_experience_delta=0,
        )
        values.update(overrides)
        return mons.TFLAttackDef.build(**values).encode()

    def test_convert_attack_maps_the_three_roles_into_the_first_three_slots(self):
        raw = self._tfl_attack(
            sequence_index=2, elevated_sequence_index=5, declined_sequence_index=9
        )
        converted = mons.convert_attack(raw)
        self.assertEqual(mons.SBAttackDef.size, len(converted))

        sb = mons.SBAttackDef.unpack(converted)
        slots = [mons.AttackSequence.unpack(sb.sequences, i * 8) for i in range(4)]
        self.assertEqual((mons.SEQ_NORMAL, 2), (slots[0].flags, slots[0].sequence_index))
        self.assertEqual((mons.SEQ_ELEVATED, 5), (slots[1].flags, slots[1].sequence_index))
        self.assertEqual((mons.SEQ_DECLINED, 9), (slots[2].flags, slots[2].sequence_index))
        self.assertEqual(-1, slots[3].sequence_index, "fourth slot is always empty")

    def test_an_unset_role_becomes_an_empty_slot_not_a_hollow_normal(self):
        raw = self._tfl_attack(sequence_index=-1, elevated_sequence_index=-1)
        sb = mons.SBAttackDef.unpack(mons.convert_attack(raw))
        first = mons.AttackSequence.unpack(sb.sequences, 0)
        self.assertEqual(-1, first.sequence_index)
        self.assertEqual(mons.SEQ_NORMAL, first.flags, "still mythextract's empty-slot flag")

    def test_scalar_fields_carry_across(self):
        raw = self._tfl_attack(minimum_range=10, maximum_range=200, recovery_time=45)
        sb = mons.SBAttackDef.unpack(mons.convert_attack(raw))
        self.assertEqual(10, sb.minimum_range)
        self.assertEqual(200, sb.maximum_range)
        self.assertEqual(45, sb.recovery_time)
        self.assertEqual(b"proj", sb.projectile_tag)
        self.assertEqual(0, sb.mana_cost, "TFL attacks never cost mana")

    def test_a_negative_velocity_delta_becomes_zero(self):
        """The dwarven hero's bottle throw: 92 and -81 in TFL. No Myth II attack
        has a negative delta, and Magma's port of this throw has 0."""
        raw = self._tfl_attack(initial_velocity_lower_bound=92, initial_velocity_delta=-81)
        sb = mons.SBAttackDef.unpack(mons.convert_attack(raw))
        self.assertEqual((92, 0), (sb.initial_velocity_lower_bound, sb.initial_velocity_delta))

    def test_a_positive_velocity_delta_is_kept(self):
        raw = self._tfl_attack(initial_velocity_lower_bound=66, initial_velocity_delta=8)
        sb = mons.SBAttackDef.unpack(mons.convert_attack(raw))
        self.assertEqual((66, 8), (sb.initial_velocity_lower_bound, sb.initial_velocity_delta))

    def test_convert_attacks_only_converts_real_slots(self):
        """A regression test for a real bug: unused TFL attack slots are
        zero-filled, and zero is not a valid TFL sequence_index (it decodes as
        slot 0, not 'none') -- so slots beyond attack_count must not be run
        through convert_attack, or they turn into bogus real attacks."""
        real = self._tfl_attack(sequence_index=3)
        blob = real + bytes(mons.ATTACK_SIZE[formats.TFL] * 3)  # 3 zero-filled slots

        converted = mons.convert_attacks(blob, attack_count=1)
        self.assertEqual(mons.ATTACK_SIZE[formats.SB] * mons.MAX_ATTACKS, len(converted))

        slot0 = mons.SBAttackDef.unpack(converted, 0)
        self.assertEqual(b"proj", slot0.projectile_tag)

        for i in range(1, mons.MAX_ATTACKS):
            slot = mons.SBAttackDef.unpack(converted, i * mons.ATTACK_SIZE[formats.SB])
            self.assertEqual(b"\x00\x00\x00\x00", slot.projectile_tag)
            for s in range(4):
                seq = mons.AttackSequence.unpack(slot.sequences, s * 8)
                self.assertEqual(-1, seq.sequence_index, "unused slot has no real sequence")

    def test_convert_sequence_indexes_expands_16_to_26(self):
        import struct

        tfl_values = list(range(16))
        blob = struct.pack(">16h", *tfl_values)
        converted = mons.convert_sequence_indexes(blob)

        self.assertEqual(52, len(converted))
        out = struct.unpack(">26h", converted)
        self.assertEqual(tuple(tfl_values), out[:16])
        self.assertEqual((-1,) * 10, out[16:])

    def test_empty_pause_and_turning_take_idle_and_moving(self):
        """Bungie's own ports of TFL units fill these; left empty, units
        jogged on the spot after stopping."""
        import struct

        tfl = [7, 8] + [-1] * 14
        out = struct.unpack(">26h", mons.convert_sequence_indexes(struct.pack(">16h", *tfl)))
        self.assertEqual((7, 8, -1, 7, 8), out[:5])

    def test_a_pause_tfl_has_is_kept(self):
        import struct

        tfl = [7, 8, -1, 5, 6] + [-1] * 11
        out = struct.unpack(">26h", mons.convert_sequence_indexes(struct.pack(">16h", *tfl)))
        self.assertEqual((7, 8, -1, 5, 6), out[:5])


class TestMonsBodyConversion(unittest.TestCase):
    def test_output_is_a_valid_myth_ii_mons_header(self):
        body = _tfl_mons_body(object_tag=b"obj1", monster_class=2)
        converted, warnings = mons_converter.convert(body)

        self.assertEqual(mons.MONS_HEADER_SIZE[formats.SB], len(converted))
        header = mons.parse_header(converted, formats.SB)
        self.assertEqual(b"obj1", header.object_tag)
        self.assertEqual(2, header.monster_class)

    def test_shared_fields_survive_the_round_trip(self):
        body = _tfl_mons_body(monster_allegiance=3, cost=250, longest_range=400)
        converted, _ = mons_converter.convert(body)

        before = mons.parse_header(body, formats.TFL)
        after = mons.parse_header(converted, formats.SB)
        checked = 0
        for field in mons_converter.SHARED_FIELDS:
            checked += 1
            self.assertEqual(
                getattr(before, field), getattr(after, field), f"{field} changed"
            )
        self.assertGreater(checked, 30, "should still be checking most fields")

    def test_size_is_man_unless_the_unit_is_a_giant(self):
        """TFL's `intelligence` is 2 for 40 of 46 stock units, and is not Myth
        II's size: Bungie's and Magma's versions are men, but for the forest
        giants and trow."""
        for collection, expected in ((b"warr", 1), (b"thra", 1), (b"zzzz", 1), (b"ent.", 2), (b"trra", 2)):
            with self.subTest(collection=collection):
                converted, _ = mons_converter.convert(_tfl_mons_body(intelligence=2, collection_tag=collection))
                self.assertEqual(expected, mons.parse_header(converted, formats.SB).size)

    def test_myth_ii_only_fields_get_the_measured_defaults(self):
        converted, _ = mons_converter.convert(_tfl_mons_body())
        after = mons.parse_header(converted, formats.SB)

        self.assertEqual(0, after.maximum_mana)  # 60/60 in the port
        self.assertEqual(255, after.experience_kill_bonus)  # 60/60
        self.assertEqual(b"\xff\xff\xff\xff", after.map_action_tag)  # 60/60 unset
        self.assertEqual(1, after.use_attack_frequency, "forced on -- see module note")

    def test_tfl_only_fields_are_reported_when_they_carry_something(self):
        body = _tfl_mons_body(melee_power=100, visual_distance=16384)
        _, warnings = mons_converter.convert(body)
        joined = "\n".join(warnings)
        self.assertIn("melee_power=100", joined)
        self.assertIn("visual_distance=16384", joined)

    def test_effect_modifiers_gap_is_reported_not_silently_dropped(self):
        body = _tfl_mons_body(effect_modifiers=bytes([1]) + bytes(23))
        _, warnings = mons_converter.convert(body)
        self.assertTrue([w for w in warnings if "effect_modifiers" in w])

    def test_short_body_is_left_alone_and_reported(self):
        converted, warnings = mons_converter.convert(b"too short")
        self.assertEqual(b"too short", converted)
        self.assertTrue([w for w in warnings if "shorter than" in w])

    def test_number_of_attacks_gates_which_slots_are_real(self):
        attack = mons.TFLAttackDef.build(
            miss_fraction=0, flags=0, projectile_tag=b"prj1",
            minimum_range=0, maximum_range=50, sequence_index=0,
            repetitions=1, initial_velocity_lower_bound=0,
            initial_velocity_delta=0, initial_velocity_error=0,
            recovery_time=10, elevated_sequence_index=-1,
            declined_sequence_index=-1, recovery_time_experience_delta=0,
        ).encode()
        attacks_block = attack + bytes(mons.ATTACK_SIZE[formats.TFL] * 3)
        body = _tfl_mons_body(number_of_attacks=1, attacks=attacks_block)

        converted, _ = mons_converter.convert(body)
        after = mons.parse_header(converted, formats.SB)
        refs = mons.attack_projectile_refs(after.attacks, formats.SB, after.number_of_attacks)
        self.assertEqual([b"prj1"], refs)

    def test_references_are_remapped_through_the_id_map(self):
        id_map = idmap.IdMap()
        id_map.add(b"obje", b"old1", b"new1")
        id_map.add(b"soun", b"olds", b"news")
        id_map.add(b"proj", b"oldp", b"newp")

        attack = mons.TFLAttackDef.build(
            miss_fraction=0, flags=0, projectile_tag=b"oldp",
            minimum_range=0, maximum_range=50, sequence_index=0,
            repetitions=1, initial_velocity_lower_bound=0,
            initial_velocity_delta=0, initial_velocity_error=0,
            recovery_time=10, elevated_sequence_index=-1,
            declined_sequence_index=-1, recovery_time_experience_delta=0,
        ).encode()
        attacks_block = attack + bytes(mons.ATTACK_SIZE[formats.TFL] * 3)
        sound_tags = b"olds" + b"\xff\xff\xff\xff" * 9

        body = _tfl_mons_body(
            object_tag=b"old1", number_of_attacks=1,
            attacks=attacks_block, sound_tags=sound_tags,
        )
        context = convert_plugin.ConversionContext(id_map=id_map)
        converted, _ = mons_converter.convert(body, context)
        after = mons.parse_header(converted, formats.SB)

        self.assertEqual(b"new1", after.object_tag)
        self.assertEqual(b"news", mons.sound_tag_refs(after.sound_tags)[0])
        self.assertEqual(
            [b"newp"],
            mons.attack_projectile_refs(after.attacks, formats.SB, after.number_of_attacks),
        )

    def test_malformed_trailing_bytes_never_raise(self):
        """A converter that crashes on one bad monster takes the whole plugin
        down with it -- garbage in, warning out, never an exception."""
        garbage = bytes(range(256)) * 2  # 512 bytes, not a coherent mons header
        converted, warnings = mons_converter.convert(garbage)
        self.assertEqual(mons.MONS_HEADER_SIZE[formats.SB], len(converted))


class TestUnitBodyConversion(unittest.TestCase):
    def test_round_trips_unchanged_with_no_id_map(self):
        body = mons.UnitTag.build(mons=b"mon1", core=b"core").encode()
        converted, warnings = unit_converter.convert(body)
        self.assertEqual(body, converted)
        self.assertEqual([], warnings)

    def test_references_are_remapped_through_the_id_map(self):
        id_map = idmap.IdMap()
        id_map.add(b"mons", b"mon1", b"mon2")
        body = mons.UnitTag.build(mons=b"mon1", core=b"core").encode()

        context = convert_plugin.ConversionContext(id_map=id_map)
        converted, _ = unit_converter.convert(body, context)
        after = mons.UnitTag.unpack(converted)
        self.assertEqual(b"mon2", after.mons)
        self.assertEqual(b"core", after.core, "unmapped id passes through unchanged")

    def test_bytes_after_the_references_are_kept(self):
        """Real unit tags are 128 bytes in both games, not 8. Truncating them
        made Myth II fail with "couldn't read unit definition" (in-engine,
        'mits - Minos the Shade')."""
        body = mons.UnitTag.build(mons=b"mon1", core=b"core").encode() + bytes(range(120))
        id_map = idmap.IdMap()
        id_map.add(b"mons", b"mon1", b"mon2")
        context = convert_plugin.ConversionContext(id_map=id_map)

        converted, _ = unit_converter.convert(body, context)
        self.assertEqual(128, len(converted))
        self.assertEqual(b"mon2", converted[:4])
        self.assertEqual(body[8:], converted[8:])

    def test_short_body_is_left_alone_and_reported(self):
        converted, warnings = unit_converter.convert(b"tiny")
        self.assertEqual(b"tiny", converted)
        self.assertTrue([w for w in warnings if "shorter than" in w])


class TestRealPluginMonsBodies(unittest.TestCase):
    """The gate that actually matters: every mons/unit tag in a real 93 MB TFL
    plugin must convert without error. Skips cleanly without a sample, same
    convention as tests/test_roundtrip.py and tests/test_mesh.py."""

    def _sample_path(self):
        single = os.environ.get("MYTH_SAMPLE_PLUGIN")
        if single and pathlib.Path(single).is_file():
            return pathlib.Path(single)
        directory = os.environ.get("MYTH_SAMPLE_DIR")
        if directory:
            for entry in sorted(pathlib.Path(directory).iterdir()):
                if entry.is_file() and entry.suffix.lower() == ".gor":
                    return entry
        return None

    def test_every_mons_and_unit_tag_converts_cleanly(self):
        path = self._sample_path()
        if not path:
            self.skipTest(
                "No sample supplied. Set MYTH_SAMPLE_PLUGIN=<file.gor> or "
                "MYTH_SAMPLE_DIR=<dir> to run this gate."
            )

        m = reader.read(path)
        if m.is_sb:
            self.skipTest(f"{path.name} is a Myth II container, not TFL")

        mons_tags = m.by_type(b"mons")
        unit_tags = m.by_type(b"unit")
        self.assertGreater(len(mons_tags), 0, "sample has no mons tags")
        self.assertGreater(len(unit_tags), 0, "sample has no unit tags")

        for tag in mons_tags:
            converted, warnings = mons_converter.convert(tag.body)
            self.assertEqual(
                mons.MONS_HEADER_SIZE[formats.SB], len(converted),
                f"mons.{codec.decode_string(tag.tag_id)} wrong output size",
            )
            unexpected = [
                w for w in warnings
                if "shorter than" in w or "cannot pack" in w
            ]
            self.assertEqual(
                [], unexpected, f"mons.{codec.decode_string(tag.tag_id)}: {unexpected}"
            )

        for tag in unit_tags:
            converted, warnings = unit_converter.convert(tag.body)
            self.assertEqual(
                mons.UnitTag.size, len(converted),
                f"unit.{codec.decode_string(tag.tag_id)} wrong output size",
            )
            self.assertEqual([], warnings, f"unit.{codec.decode_string(tag.tag_id)}: {warnings}")

    def test_whole_plugin_converts_and_survives_a_round_trip(self):
        """The end-to-end gate: convert_container must not raise on every mons
        and unit tag in the sample, and the result must read back unchanged."""
        from src import writer

        path = self._sample_path()
        if not path:
            self.skipTest(
                "No sample supplied. Set MYTH_SAMPLE_PLUGIN=<file.gor> or "
                "MYTH_SAMPLE_DIR=<dir> to run this gate."
            )

        m = reader.read(path)
        if m.is_sb:
            self.skipTest(f"{path.name} is a Myth II container, not TFL")

        sb_mono, report = convert_plugin.convert_container(m)
        mons_outcomes = [o for o in report.outcomes if o.tag_type == b"mons"]
        unit_outcomes = [o for o in report.outcomes if o.tag_type == b"unit"]
        self.assertGreater(len(mons_outcomes), 0)
        self.assertTrue(all(o.status == "converted" for o in mons_outcomes))
        self.assertTrue(all(o.status == "converted" for o in unit_outcomes))

        data = writer.pack(sb_mono, preserve_layout=False)
        verify = reader.read_bytes(data, filename="verify")
        self.assertEqual(len(sb_mono.tags), len(verify.tags))
        for expected, actual in zip(sb_mono.tags, verify.tags):
            self.assertEqual(expected.body, actual.body)


if __name__ == "__main__":
    unittest.main()


class TestPerUnitValues(unittest.TestCase):
    """Two Myth II-only fields differ unit by unit in Magma's port, so they
    come from a table keyed by the monster's collection, not one default."""

    def convert(self, collection):
        converted, _ = mons_converter.convert(_tfl_mons_body(collection_tag=collection))
        return mons.SBMonsHeader.unpack(converted)

    def test_forest_giant_and_trow_take_magmas_values(self):
        giant = self.convert(b"ent.")
        self.assertEqual((220, 0), (giant.pathfinding_radius, giant.more_hack_flags))
        trow = self.convert(b"trra")
        self.assertEqual((154, 90), (trow.pathfinding_radius, trow.more_hack_flags))

    def test_a_unit_on_thrall_sprites_gets_the_thralls_values(self):
        thrall = self.convert(b"thra")
        self.assertEqual((169, 0), (thrall.pathfinding_radius, thrall.more_hack_flags))

    def test_an_unknown_collection_keeps_the_default(self):
        custom = self.convert(b"zzzz")
        self.assertEqual(
            (mons_converter.SB_ONLY_DEFAULTS["pathfinding_radius"], mons_converter.SB_ONLY_DEFAULTS["more_hack_flags"]),
            (custom.pathfinding_radius, custom.more_hack_flags),
        )


class TestAttackFlags(unittest.TestCase):
    """TFL's attack flag word is not Myth II's: TFL has a "choose sequences
    randomly" bit at 11 that Myth II lacks, so its giant bits sit one place lower."""

    def attack(self, flags):
        import struct
        body = struct.pack(">HH4s11h", 0, flags, b"proj", 0, 0, 3, 1, 0, 0, 0, 0, 4, 5, 0) + bytes(2)
        return mons.SBAttackDef.unpack(mons.convert_attack(body))

    def test_vs_giant_stays_vs_giant(self):
        # TFL 0x1b00: random sequences + vs giant-sized (the forest giant's first attack)
        self.assertEqual(0x0B00, self.attack(0x1B00).flags)

    def test_prohibited_vs_giant_stays_prohibited(self):
        self.assertEqual(0x1300, self.attack(0x2300).flags)

    def test_the_random_sequences_bit_is_dropped(self):
        self.assertEqual(0x0300, self.attack(0x0B00).flags)

    def test_the_low_bits_are_kept(self):
        self.assertEqual(0x0700, self.attack(0x0700).flags)

    def test_the_forest_giant_ends_up_like_bungies(self):
        """First attack giants-only, second not against giants: 0xb00 and 0x1300
        in the forest giants and trow of Bungie's tags and Magma's port."""
        import struct
        def tfl_attack(flags):
            return struct.pack(">HH4s11h", 0, flags, b"proj", 0, 0, 3, 1, 0, 0, 0, 0, 4, 5, 0) + bytes(2)
        block = tfl_attack(0x1B00) + tfl_attack(0x0B00) + bytes(64)
        converted = mons.convert_attacks(block, 2)
        flags = [struct.unpack_from(">H", converted, i * 64)[0] for i in range(4)]
        self.assertEqual([0x0B00, 0x1300], flags[:2])

    def test_a_unit_with_no_giant_attack_is_left_alone(self):
        import struct
        def tfl_attack(flags):
            return struct.pack(">HH4s11h", 0, flags, b"proj", 0, 0, 3, 1, 0, 0, 0, 0, 4, 5, 0) + bytes(2)
        converted = mons.convert_attacks(tfl_attack(0x0B00) + tfl_attack(0x0300) + bytes(64), 2)
        self.assertEqual([0x0300, 0x0300], [struct.unpack_from(">H", converted, i * 64)[0] for i in range(2)])


class TestHealingAttacks(unittest.TestCase):
    """A heal must be allowed on friendly units, which Myth II needs a flag for
    and TFL never had."""

    def attack(self, flags, projectile=b"jo#2"):
        import struct
        return struct.pack(">HH4s11h", 0, flags, projectile, 0, 0, 3, 1, 0, 0, 0, 0, 4, 5, 0) + bytes(2)

    def converted(self, *attacks, healing=(b"jo#2",)):
        import struct
        converted = bytearray(mons.convert_attacks(b"".join(attacks) + bytes(128), len(attacks)))
        changed = mons.allow_healing_friendlies(converted, len(attacks), set(healing))
        extra = [struct.unpack_from(">H", converted, i * 64 + 60)[0] for i in range(len(attacks))]
        return changed, extra

    def test_a_special_ability_firing_a_healing_projectile_may_target_friends(self):
        changed, extra = self.converted(self.attack(0x0200, b"joss"), self.attack(0x0290))
        self.assertEqual((1, [0, 1]), (changed, extra))

    def test_an_ordinary_attack_is_left_alone(self):
        changed, extra = self.converted(self.attack(0x0200))
        self.assertEqual((0, [0]), (changed, extra))

    def test_a_special_ability_that_does_not_heal_is_left_alone(self):
        changed, extra = self.converted(self.attack(0x00D0, b"dw#2"))
        self.assertEqual((0, [0]), (changed, extra))

    def test_ids_of_healing_projectiles_come_from_the_damage_type(self):
        import struct
        def proj(tag_id, damage_type):
            body = bytearray(256); struct.pack_into(">h", body, 108, damage_type)
            return reader.Tag(header=None, body=bytes(body)) if False else type("T", (), {"tag_type": b"proj", "tag_id": tag_id, "body": bytes(body)})()
        tags = [proj(b"jo#2", 3), proj(b"fire", 9), proj(b"hurt", 1)]
        self.assertEqual({b"jo#2"}, mons.healing_projectile_ids(tags))

    def test_the_converter_uses_the_context(self):
        from src.convert import plugin as convert_plugin
        context = convert_plugin.ConversionContext()
        context.healing_projectiles = {b"jo#2"}
        body = _tfl_mons_body(number_of_attacks=1, attacks=self.attack(0x0290) + bytes(96))
        converted, _ = mons_converter.convert(body, context)
        import struct
        self.assertEqual(1, struct.unpack_from(">H", mons.parse_header(converted, formats.SB).attacks, 60)[0])
