"""Convert an ``arti`` (artifact) tag body from TFL to Myth II.

mythextract declares both layouts (``mons_tag.ArtifactFmt(game_version)``),
which differ in exactly two places; everything else is shared:

    field                      TFL bytes   Myth II bytes
    header (flags .. pad)      0..52       0..52
    bonus_effect_modifiers     52..76      52..84     12 -> 16 slots
    override_attack            76..108     84..148    32 -> 64 bytes
    tail (string list .. types) 108..128   148..168

Stock TFL artifacts are 256 bytes, not 128: the declared layout followed by
128 zero bytes, which are dropped (and reported if they are ever not zero).

The attack is converted by the same `mons_module.convert_attack` the `mons`
converter uses.

**Effect modifiers.** All 12 are zero in every stock TFL artifact. Myth II
reads these as damage multipliers, where 0x0100 is 1.0 (normal) -- Magma's
untuned artifacts carry 0x0100 in the first 9 slots and 0 in the rest
(``bahe``, ``booi``, ``boos``), so copied zeros could leave a bearer immune to
everything. An all-zero TFL set therefore becomes that default; a set with
real values is copied into the first 12 slots. Measured against the 5 artifact
IDs in both the stock TFL tags and Magma (NOTES.md section 18).
"""

from ... import codec, mons as mons_module

HANDLES = (b"arti",)

TFL_SIZE = 128
SB_SIZE = 168

HEAD = slice(0, 52)
TFL_MODS = slice(52, 76)
TFL_ATTACK = slice(76, 108)
TFL_TAIL = slice(108, 128)

SB_MODS_COUNT = 16
UNTUNED_MODS = (0x0100,) * 9 + (0,) * 7

SB_ATTACK_AT = 84

# Myth II offsets of the artifact's own tag references.
REFERENCES = (
    (4, b"mons"),  # monster_restriction_tag
    (16, b".256"),  # collection_tag
    (28, b"proj"),  # projectile_tags[4]
    (32, b"proj"),
    (36, b"proj"),
    (40, b"proj"),
    (148, b"stli"),  # special_ability_string_list_tag
    (152, b"mons"),  # monster_override_tag
)


def convert(body, context=None):
    """Convert a TFL artifact body. Returns ``(new_body, warnings)``.

    ``context`` may carry ``id_map`` to remap the tag references.
    """
    warnings = []
    id_map = getattr(context, "id_map", None) if context else None

    if len(body) not in (TFL_SIZE, 2 * TFL_SIZE):
        return body, [
            f"arti body is {len(body)} bytes, not {TFL_SIZE} or {2 * TFL_SIZE}; "
            f"left unconverted"
        ]
    if any(body[TFL_SIZE:]):
        warnings.append(
            f"dropped {len(body) - TFL_SIZE} bytes after the {TFL_SIZE}-byte "
            f"artifact, not all zero"
        )

    mods = mons_module.struct_unpack_shorts(body[TFL_MODS], 12)
    if not any(mods):
        mods = UNTUNED_MODS
    else:
        mods = tuple(mods) + (0,) * (SB_MODS_COUNT - len(mods))

    attack = mons_module.convert_attack(body[TFL_ATTACK])
    attack = attack if isinstance(attack, (bytes, bytearray)) else attack.encode()

    out = bytearray(
        body[HEAD]
        + mons_module.struct_pack_shorts(mods)
        + attack
        + body[TFL_TAIL]
    )
    assert len(out) == SB_SIZE, len(out)

    if id_map is not None:
        for offset, tag_type in REFERENCES:
            value = bytes(out[offset : offset + 4])
            if codec.all_on(value) or codec.all_off(value):
                continue
            out[offset : offset + 4] = id_map.map_id(tag_type, value)
        # The attack's projectile sits after its flags and miss fraction.
        at = SB_ATTACK_AT + 4
        value = bytes(out[at : at + 4])
        if not (codec.all_on(value) or codec.all_off(value)):
            out[at : at + 4] = id_map.map_id(b"proj", value)

    return bytes(out), warnings
