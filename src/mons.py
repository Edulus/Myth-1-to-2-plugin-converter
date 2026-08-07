"""Monster (`mons`), unit (`unit`), and attack-definition layouts for TFL and
Myth II.

A `mons` tag is a monster's *behaviour*: stats, attacks, sounds, damage
thresholds. TFL's is 512 bytes; Myth II's is 1024 -- unlike the mesh header
(same size, different layout), this one genuinely grew, because Myth II added
entire subsystems TFL never had: mana and berserking, knockback propulsion,
morale, per-monster ambient map actions, multi-artifact carrying.

Ported from mythextract ``scripts/mons_tag.py`` @ c747909 (``MonsTagFmt``,
``MonsTagFmtTFL``, ``AttackDefFmt``, ``AttackDefFmtTFL``, ``UnitTagFmt``).
Decoders (scale factors, enums) are dropped, matching `mesh.py` -- this
project's codec does not do value decoding, and a structural pass-through never
needs the scaled value, only the raw bytes.

``unit`` needs no porting at all: mythextract declares one ``UnitTagFmt`` (8
bytes: a `mons` reference and a `core` reference), no TFL variant, no
game-version branch. It is the second sub-structure found genuinely identical
between the games, after markers/palette/map-action-heads in `mesh.py`.
"""

import struct

from . import codec, formats

MONS_HEADER_SIZE = {formats.TFL: 512, formats.SB: 1024}
ATTACK_SIZE = {formats.TFL: 32, formats.SB: 64}
MAX_ATTACKS = 4
SB_SEQUENCE_SLOTS = 26
TFL_SEQUENCE_SLOTS = 16

# --- unit, 8 bytes, identical in both games -----------------------------------
# mythextract scripts/mons_tag.py:509-512 (``UnitTagFmt``).
UnitTag = codec.Struct(
    "UnitTag",
    [
        ("4s", "mons"),
        ("4s", "core"),
    ],
)
assert UnitTag.size == 8, UnitTag.size


# --- attack definitions -------------------------------------------------------
# mythextract scripts/mons_tag.py:88-104 (TFL) and :65-86 (SB). Embedded arrays
# in the mons header (``sequences`` in SB, one per attack), packed as opaque
# byte blocks here and converted by `convert_attacks` below -- this project's
# codec does not do nested/list decoding, matching how `mesh.py` treats markers
# as opaque blocks with dedicated converters rather than nested struct fields.

# mythextract scripts/mons_tag.py:58-63 (``AttackSequenceFmt``), 8 bytes.
AttackSequence = codec.Struct(
    "AttackSequence",
    [
        ("H", "flags"),
        ("h", "sequence_index"),
        ("H", "skip_fraction"),
        ("2x", None),
    ],
)
assert AttackSequence.size == 8, AttackSequence.size

TFLAttackDef = codec.Struct(
    "TFLAttackDef",
    [
        ("H", "miss_fraction"),
        ("H", "flags"),
        ("4s", "projectile_tag"),
        ("h", "minimum_range"),
        ("h", "maximum_range"),
        ("h", "sequence_index"),
        ("h", "repetitions"),
        ("h", "initial_velocity_lower_bound"),
        ("h", "initial_velocity_delta"),
        ("h", "initial_velocity_error"),
        ("h", "recovery_time"),
        ("h", "elevated_sequence_index"),
        ("h", "declined_sequence_index"),
        ("h", "recovery_time_experience_delta"),
        ("2x", None),
    ],
)

SBAttackDef = codec.Struct(
    "SBAttackDef",
    [
        ("H", "flags"),
        ("H", "miss_fraction"),
        ("4s", "projectile_tag"),
        ("h", "minimum_range"),
        ("h", "maximum_range"),
        ("32s", "sequences"),  # 4x AttackSequence, opaque here
        ("h", "repetitions"),
        ("h", "initial_velocity_lower_bound"),
        ("h", "initial_velocity_delta"),
        ("h", "initial_velocity_error"),
        ("h", "recovery_time"),
        ("h", "recovery_time_experience_delta"),
        ("h", "velocity_improvement_with_experience"),
        ("h", "mana_cost"),
        ("H", "extra_flags"),
        ("2x", None),
    ],
)

assert TFLAttackDef.size == ATTACK_SIZE[formats.TFL], TFLAttackDef.size
assert SBAttackDef.size == ATTACK_SIZE[formats.SB], SBAttackDef.size

# The sequence-role bit values, inferred rather than confirmed: mythextract
# does not name these bits (AttackSequenceFmt's `flags` has no decoder), so
# this assignment comes from the Fear manual's three attack-editing checkboxes
# (Normal, Elevated, Declinated). Corroborated by the 133 real non-empty
# sequence slots across 60 converted mons tags in Magma - The Fallen Lords
# v1.9: flags observed were {1: 114, 4: 10, 2: 8, 7: 1} -- a plurality of plain
# NORMAL, and one slot with all three bits set (7 = 1|2|4), meaning a single
# sequence can serve every role at once.
SEQ_NORMAL = 1
SEQ_ELEVATED = 2
SEQ_DECLINED = 4

# mythextract's own encoder default for an unused sequence slot
# (scripts/mons_tag.py:74): flags=1 (Normal), sequence_index=-1 (none), no skip.
EMPTY_SEQUENCE = AttackSequence.build(flags=SEQ_NORMAL, sequence_index=-1, skip_fraction=0)


def convert_attack(tfl_bytes):
    """Convert one TFL attack definition to Myth II's, expanding its single
    sequence trio into Myth II's 4-slot array.

    TFL names three sequence roles as separate fixed fields
    (``sequence_index``, ``elevated_sequence_index``, ``declined_sequence_index``);
    Myth II holds up to four ``(flags, index, skip_fraction)`` entries in one
    array, with the flags saying which role(s) a slot plays. This maps TFL's
    three roles onto the first three slots by role, and fills the fourth with
    mythextract's own empty-slot convention. A slot whose TFL index is -1
    (unset) is written as empty too, rather than as a hollow "normal" sequence.

    Returns raw Myth II attack-definition bytes, ``ATTACK_SIZE[formats.SB]``
    long.
    """
    tfl = TFLAttackDef.unpack(tfl_bytes)

    def slot(role_bit, index):
        if index is None or index < 0:
            return EMPTY_SEQUENCE.encode()
        return AttackSequence.build(
            flags=role_bit, sequence_index=index, skip_fraction=0
        ).encode()

    sequences = (
        slot(SEQ_NORMAL, tfl.sequence_index)
        + slot(SEQ_ELEVATED, tfl.elevated_sequence_index)
        + slot(SEQ_DECLINED, tfl.declined_sequence_index)
        + EMPTY_SEQUENCE.encode()
    )

    return SBAttackDef.build(
        flags=tfl.flags,
        miss_fraction=tfl.miss_fraction,
        projectile_tag=tfl.projectile_tag,
        minimum_range=tfl.minimum_range,
        maximum_range=tfl.maximum_range,
        sequences=sequences,
        repetitions=tfl.repetitions,
        initial_velocity_lower_bound=tfl.initial_velocity_lower_bound,
        initial_velocity_delta=tfl.initial_velocity_delta,
        initial_velocity_error=tfl.initial_velocity_error,
        recovery_time=tfl.recovery_time,
        recovery_time_experience_delta=tfl.recovery_time_experience_delta,
        velocity_improvement_with_experience=0,  # no TFL source; new in SB
        mana_cost=0,  # no TFL source -- TFL attacks never cost mana
        extra_flags=0,  # new SB-only bitfield (87/106 real attacks agree)
    ).encode()


EMPTY_ATTACK = SBAttackDef.build(
    flags=0,
    miss_fraction=0,
    projectile_tag=b"\x00\x00\x00\x00",
    minimum_range=0,
    maximum_range=0,
    sequences=EMPTY_SEQUENCE.encode() * 4,
    repetitions=0,
    initial_velocity_lower_bound=0,
    initial_velocity_delta=0,
    initial_velocity_error=0,
    recovery_time=0,
    recovery_time_experience_delta=0,
    velocity_improvement_with_experience=0,
    mana_cost=0,
    extra_flags=0,
).encode()


def convert_attacks(tfl_bytes, attack_count):
    """Convert up to `MAX_ATTACKS` attack definitions.

    ``tfl_bytes`` is the mons tag's whole attacks block (``MAX_ATTACKS *
    ATTACK_SIZE[TFL]`` bytes). Only the first ``attack_count`` slots are real;
    a TFL unused slot is zero-filled, and zero is not a valid TFL attack
    (``sequence_index`` would decode as 0 rather than -1/"none"), so slots at
    or past ``attack_count`` are written as `EMPTY_ATTACK` rather than run
    through `convert_attack`, which would otherwise turn raw zero bytes into a
    bogus "attack sequence 0, normal" entry.
    """
    attack_count = max(0, min(attack_count, MAX_ATTACKS))
    out = bytearray()
    for i in range(MAX_ATTACKS):
        if i < attack_count:
            start = i * ATTACK_SIZE[formats.TFL]
            out += convert_attack(tfl_bytes[start : start + ATTACK_SIZE[formats.TFL]])
        else:
            out += EMPTY_ATTACK
    return bytes(out)


def convert_sequence_indexes(tfl_bytes):
    """Expand TFL's 16-slot sequence-index array to Myth II's 26 slots.

    Slots 0-15 carry the same *role* in both games -- Bungie extended the
    array by appending new roles (Myth II added animations TFL never needed,
    such as ``propelled``, which only makes sense with the new knockback
    system) rather than renumbering existing ones. That is the ordinary way to
    grow a fixed, role-indexed array without breaking everything that already
    shipped, so slots 0-15 are copied as-is and 16-25 are set to -1 (no
    sequence for that role), which is what "TFL never had this role" means in
    practice.
    """
    values = list(struct_unpack_shorts(tfl_bytes, TFL_SEQUENCE_SLOTS))
    values += [-1] * (SB_SEQUENCE_SLOTS - TFL_SEQUENCE_SLOTS)
    return struct_pack_shorts(values)


def struct_unpack_shorts(data, count):
    return struct.unpack(f">{count}h", data[: count * 2])


def struct_pack_shorts(values):
    return struct.pack(f">{len(values)}h", *values)


# --- mons header ---------------------------------------------------------------
# mythextract scripts/mons_tag.py:412-484 (TFL) and :319-399 (SB). Field names
# match mythextract's exactly, so `SHARED_FIELDS` in the converter (computed by
# name, not position -- see mesh.py's identical mechanism) finds every field
# that carries across unchanged despite the two structs disagreeing on both
# size and field order.
#
# `sequence_indexes` and `attacks` are opaque byte blocks (see above) because
# they differ in size between the games and need dedicated conversion, exactly
# like markers/map-actions in mesh.py.

TFLMonsHeader = codec.Struct(
    "TFLMonsHeader",
    [
        ("L", "flags"),
        ("4s", "collection_tag"),
        ("32s", "sequence_indexes"),  # 16 x int16, opaque
        ("32x", None),
        ("16s", "terrain_costs"),
        ("14x", None),
        ("2x", None),  # runtime: terrain_impassability_flags
        ("16s", "movement_modifiers"),
        ("H", "absorbed_fraction"),
        ("h", "warning_distance"),
        ("h", "critical_distance"),
        ("h", "healing_fraction"),
        ("h", "initial_ammunition_lower_bound"),
        ("h", "initial_ammunition_delta"),
        ("h", "activation_distance"),
        ("h", "visual_distance"),  # TFL-only
        ("H", "turning_speed"),
        ("h", "base_movement_speed"),
        ("H", "left_handed_fraction"),
        ("h", "intelligence"),  # same slot as SB's "size"
        ("4s", "object_tag"),
        ("h", "number_of_attacks"),
        ("h", "desired_projectile_volume"),
        ("128s", "attacks"),  # 4 x TFLAttackDef, opaque
        ("h", "object_scale_lower_bound"),  # TFL-only
        ("h", "object_scale_delta"),  # TFL-only
        ("h", "sound_pitch_lower_bound"),  # TFL-only
        ("h", "sound_pitch_delta"),  # TFL-only
        ("h", "attack_frequency_lower_bound"),
        ("h", "attack_frequency_delta"),
        ("4s", "exploding_projectile_group_tag"),
        ("h", "maximum_vitality"),  # TFL-only
        ("h", "maximum_ammunition_count"),
        ("H", "hard_death_system_shock"),
        ("H", "flinch_system_shock"),
        ("4s", "melee_impact_projectile_group_tag"),
        ("4s", "dying_projectile_group_tag"),
        ("4s", "spelling_string_list_tag"),
        ("4s", "names_string_list_tag"),
        ("4s", "flavor_string_list_tag"),
        ("h", "melee_power"),  # TFL-only
        ("h", "monster_class"),
        ("h", "monster_allegiance"),
        ("h", "experience_point_value"),
        ("40s", "sound_tags"),  # 10 x 4s, same both games
        ("4s", "blocked_impact_projectile_group_tag"),
        ("4s", "absorbed_impact_projectile_group_tag"),
        ("4s", "ammunition_projectile_tag"),
        ("h", "visibility_type"),
        ("h", "combined_power"),
        ("h", "longest_range"),
        ("24s", "effect_modifiers"),  # TFL-only; see NOTES.md section 16
        ("h", "cost"),
        ("10s", "sound_types"),  # 10 x int8, same both games
        ("h", "enemy_experience_kill_bonus"),
        ("4s", "entrance_projectile_group_tag"),
        ("4s", "local_projectile_group_tag"),
        ("4s", "special_ability_string_list_tag"),
        ("4s", "exit_projectile_group_tag"),
        ("16x", None),
        ("52x", None),  # runtime
    ],
)

SBMonsHeader = codec.Struct(
    "SBMonsHeader",
    [
        ("L", "flags"),
        ("4s", "collection_tag"),
        ("52s", "sequence_indexes"),  # 26 x int16, opaque
        ("4s", "burning_death_projectile_group_tag"),  # SB-only
        ("h", "burning_death_projectile_group_type"),  # SB-only
        ("B", "experience_kill_bonus"),  # SB-only
        ("B", "experience_bonus_radius"),  # SB-only
        ("H", "propelled_system_shock"),  # SB-only
        ("H", "damage_to_propulsion"),  # SB-only
        ("16s", "terrain_costs"),
        ("2x", None),  # runtime: terrain_impassability_flags
        ("h", "pathfinding_radius"),  # SB-only
        ("16s", "movement_modifiers"),
        ("H", "absorbed_fraction"),
        ("h", "warning_distance"),
        ("h", "critical_distance"),
        ("h", "healing_fraction"),
        ("h", "initial_ammunition_lower_bound"),
        ("h", "initial_ammunition_delta"),
        ("h", "activation_distance"),
        ("2x", None),  # TFL's visual_distance has no SB destination
        ("H", "turning_speed"),
        ("h", "base_movement_speed"),
        ("H", "left_handed_fraction"),
        ("h", "size"),  # same slot as TFL's "intelligence"
        ("4s", "object_tag"),
        ("h", "number_of_attacks"),
        ("h", "desired_projectile_volume"),
        ("256s", "attacks"),  # 4 x SBAttackDef, opaque
        ("4s", "map_action_tag"),  # SB-only
        ("h", "attack_frequency_lower_bound"),
        ("h", "attack_frequency_delta"),
        ("4s", "exploding_projectile_group_tag"),
        ("h", "hack_flags"),  # SB-only
        ("h", "maximum_ammunition_count"),
        ("H", "hard_death_system_shock"),
        ("H", "flinch_system_shock"),
        ("4s", "melee_impact_projectile_group_tag"),
        ("4s", "dying_projectile_group_tag"),
        ("4s", "spelling_string_list_tag"),
        ("4s", "names_string_list_tag"),
        ("4s", "flavor_string_list_tag"),
        ("b", "use_attack_frequency"),  # SB-only
        ("b", "more_hack_flags"),  # SB-only
        ("h", "monster_class"),
        ("h", "monster_allegiance"),
        ("h", "experience_point_value"),
        ("40s", "sound_tags"),
        ("4s", "blocked_impact_projectile_group_tag"),
        ("4s", "absorbed_impact_projectile_group_tag"),
        ("4s", "ammunition_projectile_tag"),
        ("h", "visibility_type"),
        ("h", "combined_power"),
        ("h", "longest_range"),
        ("h", "cost"),
        ("10s", "sound_types"),
        ("h", "enemy_experience_kill_bonus"),
        ("4s", "entrance_projectile_group_tag"),
        ("4s", "local_projectile_group_tag"),
        ("4s", "special_ability_string_list_tag"),
        ("4s", "exit_projectile_group_tag"),
        ("h", "maximum_mana"),  # SB-only
        ("h", "mana_recharge_rate"),  # SB-only
        ("H", "berserk_system_shock"),  # SB-only
        ("H", "berserk_vitality"),  # SB-only
        ("h", "maximum_artifacts_carried"),  # SB-only
        ("2x", None),
        ("4s", "initial_artifacts_projectile_group_tag"),  # SB-only
        ("L", "extra_flags"),  # SB-only
        ("208x", None),
        ("264x", None),  # runtime
    ],
)

MONS_HEADER_BY_VERSION = {formats.TFL: TFLMonsHeader, formats.SB: SBMonsHeader}

assert TFLMonsHeader.size == MONS_HEADER_SIZE[formats.TFL], TFLMonsHeader.size
assert SBMonsHeader.size == MONS_HEADER_SIZE[formats.SB], SBMonsHeader.size


def parse_header(body, game_version):
    """Parse a `mons` tag body -- the whole body, since unlike a mesh, nothing
    meaningful follows the fixed-size header."""
    struct_def = MONS_HEADER_BY_VERSION[game_version]
    if len(body) < struct_def.size:
        raise ValueError(
            f"mons body is {len(body)} bytes, need at least {struct_def.size} "
            f"for {'TFL' if game_version == formats.TFL else 'Myth II'}"
        )
    return struct_def.unpack(body)


# Every field that carries a tag reference, and the tag type it refers to.
# Field-to-type mapping cross-checked against the Fear manual's own labels
# ("Melee Impact", "Blocked Impact", "Spelling", ...). Attack projectile_tag
# fields are handled separately since they live inside the opaque attacks
# block, not as top-level fields.
REFERENCED_TAGS = {
    "collection_tag": b".256",
    "object_tag": b"obje",
    "exploding_projectile_group_tag": b"prgr",
    "melee_impact_projectile_group_tag": b"prgr",
    "dying_projectile_group_tag": b"prgr",
    "spelling_string_list_tag": b"stli",
    "names_string_list_tag": b"stli",
    "flavor_string_list_tag": b"stli",
    "blocked_impact_projectile_group_tag": b"prgr",
    "absorbed_impact_projectile_group_tag": b"prgr",
    "ammunition_projectile_tag": b"proj",
    "entrance_projectile_group_tag": b"prgr",
    "local_projectile_group_tag": b"lpgr",
    "special_ability_string_list_tag": b"stli",
    "exit_projectile_group_tag": b"prgr",
    # Myth II only:
    "burning_death_projectile_group_tag": b"prgr",
    "map_action_tag": b"scri",
    "initial_artifacts_projectile_group_tag": b"prgr",
}


def referenced_tags(header):
    """Every ``(tag_type, tag_id, field)`` a mons header points at directly.

    Sound tags (10 slots) and attack projectile tags are not included here --
    they live in opaque array blocks and are walked separately.
    """
    found = []
    for field, tag_type in REFERENCED_TAGS.items():
        value = getattr(header, field, None)
        if value and not codec.all_on(value) and not codec.all_off(value):
            found.append((tag_type, value, field))
    return found


def sound_tag_refs(sound_tags_bytes):
    """The up-to-10 sound tag references packed in a mons header's
    ``sound_tags`` field. Unset slots (all-0xFF, mythextract's convention for
    this specific list) are skipped."""
    refs = []
    for i in range(0, len(sound_tags_bytes), 4):
        tag_id = sound_tags_bytes[i : i + 4]
        if len(tag_id) == 4 and not codec.all_on(tag_id):
            refs.append(tag_id)
    return refs


def attack_projectile_refs(attacks_bytes, game_version, attack_count):
    """The projectile tag each real attack (of up to `MAX_ATTACKS`) fires."""
    struct_def = TFLAttackDef if game_version == formats.TFL else SBAttackDef
    size = ATTACK_SIZE[game_version]
    refs = []
    for i in range(min(attack_count, MAX_ATTACKS)):
        chunk = attacks_bytes[i * size : (i + 1) * size]
        if len(chunk) < size:
            continue
        tag_id = struct_def.unpack(chunk).projectile_tag
        if not codec.all_on(tag_id) and not codec.all_off(tag_id):
            refs.append(tag_id)
    return refs
