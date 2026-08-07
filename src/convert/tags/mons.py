"""Convert a ``mons`` tag body from TFL to Myth II.

TFL's `mons` header is 512 bytes; Myth II's is 1024 (`src/mons.py`). As with
`mesh`, converting means rebuilding the header field by field, by name, not by
position -- a TFL body handed to Myth II unconverted parses as 512 bytes of one
struct read as a different, larger one.

Three groups of fields, same shape as the mesh converter:

**Shared** -- same name in both layouts (`SHARED_FIELDS`, computed by name
intersection), copied across unchanged. Two fields need help beyond that:

    size / intelligence   Same byte slot, renamed between the games (both
                           decode via mythextract's ``Size`` enum: small/man/
                           giant) -- mapped explicitly since the name differs.
    sequence_indexes,      Different sizes in the two games (32 vs 52 bytes,
    attacks                128 vs 256), so a same-name copy would silently
                           zero-pad rather than convert. Handled by
                           `mons_module.convert_sequence_indexes` and
                           `convert_attacks` instead.

**TFL-only** -- dropped, and reported when non-zero:

    visual_distance, object_scale_lower_bound/delta, sound_pitch_lower_bound/
    delta, maximum_vitality, melee_power    no Myth II destination
    effect_modifiers                        see the note below

**Myth II-only** -- synthesised from measuring 60 real converted `mons` tags in
`Magma - The Fallen Lords v1.9`. Most agree unanimously (60/60); a few are
recorded as majority values with their agreement count so the gap is visible
rather than hidden (`SB_ONLY_DEFAULTS`).

**What this still does not do.** TFL's `effect_modifiers` is a per-monster
damage-vulnerability profile (close/long-range physical, explosive, electric,
magical, paralysis, stone). Myth II moved this concept to the `obje` tag
(`obje.effect_modifiers`, 9 channels) and a single damage type per projectile
(`proj.ProjDmgFmt`) -- there is no field on `mons` itself to receive it. Wiring
that up means writing to a *different* tag (`mons.object_tag` -> `obje`), which
is out of scope here and is reported as a dropped field like any other, not
silently discarded.
"""

from ... import codec, formats
from ... import mons as mons_module

HANDLES = (b"mons",)

# Fields Myth II has and TFL does not. Values measured across the 60 `mons`
# tags of Magma - The Fallen Lords v1.9; the count is how many of the 60
# agreed. All but four are unanimous.
SB_ONLY_DEFAULTS = {
    "burning_death_projectile_group_tag": b"\xff\xff\xff\xff",  # 60/60 unset
    # 40/60 -- majority, not unanimous. HAS_BURNING_DEATH (the flag that gates
    # this) is never set by TFL content, so the type is inert either way; kept
    # as a measured default rather than a guess.
    "burning_death_projectile_group_type": -1,
    "experience_kill_bonus": 255,  # 60/60 -- 0xFF, i.e. "use enemy_experience_kill_bonus instead"
    "experience_bonus_radius": 255,  # 60/60
    "propelled_system_shock": 65535,  # 60/60 unset; gated by CAN_BE_PROPELLED, which TFL never sets
    "damage_to_propulsion": 65535,  # 60/60, same gating
    # 28/60 for the plurality value (77); the rest spread across dozens of
    # distinct values -- this is a per-monster "space bubble" radius with no
    # single meaningful default (see NOTES.md section 16). Kept as the
    # plurality so the field is never left at zero, which Fear treats as a
    # real (zero-radius) value rather than "unset".
    "pathfinding_radius": 77,
    "map_action_tag": b"\xff\xff\xff\xff",  # 60/60 unset
    "hack_flags": 0,  # 60/60
    # 23/60 vs 23/60 tied between 50 and 100, 13/60 at 0, 1/60 at 90. What this
    # controls is not documented anywhere found; 0 is chosen as the most
    # conservative of the four rather than picking a side of the tie.
    "more_hack_flags": 0,
    "maximum_mana": 0,  # 60/60 -- TFL predates the mana system entirely
    "mana_recharge_rate": 0,  # 60/60
    "berserk_system_shock": 0,  # 60/60
    "berserk_vitality": 0,  # 60/60
    "maximum_artifacts_carried": 0,  # 60/60
    "initial_artifacts_projectile_group_tag": b"\xff\xff\xff\xff",  # 43/60 majority unset
    "extra_flags": 0,  # 60/60
}

# TFL fields with no Myth II destination. Reported when they carry something.
TFL_ONLY_FIELDS = (
    "visual_distance",
    "object_scale_lower_bound",
    "object_scale_delta",
    "sound_pitch_lower_bound",
    "sound_pitch_delta",
    "maximum_vitality",
    "melee_power",
    "effect_modifiers",
)

# Fields present under the same name and the same size in both header layouts.
# `size`/`intelligence` share a byte slot under different names, so it is
# excluded here and mapped explicitly; `sequence_indexes`/`attacks` share a
# name but differ in size, so they are excluded too and rebuilt by dedicated
# converters instead of a same-name copy (which would silently zero-pad).
_TFL_FIELDS = set(mons_module.TFLMonsHeader.names)
_OPAQUE_FIELDS = {"sequence_indexes", "attacks"}
SHARED_FIELDS = tuple(
    f
    for f in mons_module.SBMonsHeader.names
    if f in _TFL_FIELDS and f not in _OPAQUE_FIELDS
)

# use_attack_frequency is forced on (see `convert`); every other SB-only field
# and the specially-handled ones make up the rest of the header.
SYNTHESISED = dict(SB_ONLY_DEFAULTS)


def convert(body, context=None):
    """Convert a TFL mons body. Returns ``(new_body, warnings)``.

    ``context`` may carry ``id_map`` to remap the tag references this header
    and its embedded attacks/sound-tag list carry.
    """
    warnings = []
    id_map = getattr(context, "id_map", None) if context else None

    if len(body) < mons_module.MONS_HEADER_SIZE[formats.TFL]:
        return body, [
            f"mons body is {len(body)} bytes, shorter than the "
            f"{mons_module.MONS_HEADER_SIZE[formats.TFL]}-byte TFL header; left unconverted"
        ]

    tfl = mons_module.TFLMonsHeader.unpack(body)

    for field in TFL_ONLY_FIELDS:
        value = getattr(tfl, field)
        carries = not codec.all_off(value) if isinstance(value, bytes) else bool(value)
        if carries:
            shown = value.hex() if isinstance(value, bytes) else value
            warnings.append(f"dropped TFL-only mons field {field}={shown}")

    values = {field: getattr(tfl, field) for field in SHARED_FIELDS}
    values["size"] = tfl.intelligence
    values.update(SB_ONLY_DEFAULTS)
    values["sequence_indexes"] = mons_module.convert_sequence_indexes(tfl.sequence_indexes)
    values["attacks"] = mons_module.convert_attacks(tfl.attacks, tfl.number_of_attacks)

    # TFL applied attack_frequency unconditionally -- it had no gating flag for
    # it. The real port's use_attack_frequency is split 37/60 off, 23/60 on,
    # which reflects per-monster editorial tuning done after the port, not a
    # technical default; forcing it on here preserves TFL's actual behaviour
    # rather than guessing at a majority that means something else.
    values["use_attack_frequency"] = 1

    reference_warnings = _remap_references(values, id_map)
    warnings.extend(reference_warnings)

    header = mons_module.SBMonsHeader.build(**values)
    converted = header.encode()
    assert len(converted) == mons_module.MONS_HEADER_SIZE[formats.SB]

    return converted, warnings


def _remap_references(values, id_map):
    """Rewrite every tag reference in ``values`` through ``id_map``, in place.

    Covers the header's direct reference fields (only those carrying real TFL
    data -- the synthesised SB-only ones are already unset), the 10-slot sound
    tag list, and each attack's projectile tag.
    """
    if id_map is None:
        return []
    warnings = []

    for field, tag_type in mons_module.REFERENCED_TAGS.items():
        if field not in values:
            continue
        value = values[field]
        if codec.all_on(value) or codec.all_off(value):
            continue
        values[field] = id_map.map_id(tag_type, value)

    sound_tags = bytearray(values["sound_tags"])
    for i in range(0, len(sound_tags), 4):
        tag_id = bytes(sound_tags[i : i + 4])
        if codec.all_on(tag_id) or codec.all_off(tag_id):
            continue
        mapped = id_map.map_id(b"soun", tag_id)
        if mapped != tag_id:
            sound_tags[i : i + 4] = mapped
    values["sound_tags"] = bytes(sound_tags)

    attacks = bytearray(values["attacks"])
    slot_size = mons_module.ATTACK_SIZE[formats.SB]
    for i in range(mons_module.MAX_ATTACKS):
        start = i * slot_size
        chunk = bytes(attacks[start : start + slot_size])
        attack = mons_module.SBAttackDef.unpack(chunk)
        tag_id = attack.projectile_tag
        if codec.all_on(tag_id) or codec.all_off(tag_id):
            continue
        mapped = id_map.map_id(b"proj", tag_id)
        if mapped != tag_id:
            # projectile_tag sits right after flags (H) + miss_fraction (H).
            attacks[start + 4 : start + 8] = mapped
    values["attacks"] = bytes(attacks)

    return warnings
