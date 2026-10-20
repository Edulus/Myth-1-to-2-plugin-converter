"""Convert a ``scen`` (scenery) tag body from TFL to Myth II.

Both games store scenery in 128 bytes, in different layouts. mythextract
declares only the Myth II one (``myth_tags.SceneryFmt``), so the TFL side was
measured: the 61 scenery IDs present both in the stock TFL tags and in
`Magma - The Fallen Lords v1.9` were aligned word by word (NOTES.md section 18).
Handed to Myth II unconverted, a TFL scenery tag reads its object reference out
of the wrong bytes -- in-engine, "couldn't read header for object definition"
and "collection reference definition '    '" for every bush, tree and barrel.

The fields move by different amounts, so the body is rebuilt from a map rather
than shifted:

    Myth II   field                         TFL bytes   agreement (of 61)
    0..4      flags                         0..4        43 (bits keep meaning)
    4..8      collection_reference_tag      8..12       56
    8..12     object_tag                    24..28      35 (Magma renamed many)
    12..16    projectile_tag                28..32      59
    24..40    projectile_group_tags[4]      44..60      anchored on references
    40..54    sequence_indexes[6] + 1 word  60..74      51-60

TFL bytes 32..44 hold six varied words with no Myth II destination -- Magma's
ports zero everything from 54 on -- and are dropped. ``valid_netgame_scoring_type``
is 0xFFFF in all 141 of Magma's scenery tags; ``netgame_flag_number`` is
per-map setup with no TFL source, and gets its majority value, 0xFFFF (56/141).
Unused tag references become 0xFFFF ("none"), as in every Myth II tag.

Converted, stock TFL scenery agrees with Magma's ports in 94.2% of bytes (60.8%
unconverted); the rest is Magma's own renaming and per-map editing.
"""

from ... import codec

HANDLES = (b"scen",)

SIZE = 128

# (Myth II offset, TFL offset, length)
MOVES = (
    (0, 0, 4),  # flags
    (4, 8, 4),  # collection_reference_tag
    (8, 24, 8),  # object_tag, projectile_tag
    (24, 44, 16),  # projectile_group_tags[4]
    (40, 60, 14),  # sequence_indexes[6], and the word after
)

NETGAME_FIELDS = slice(16, 20)  # valid_netgame_scoring_type, netgame_flag_number

# Myth II offsets of the tag references, with the type each names.
REFERENCES = (
    (4, b"core"),
    (8, b"obje"),
    (12, b"proj"),
    (24, b"prgr"),
    (28, b"prgr"),
    (32, b"prgr"),
    (36, b"prgr"),
)

NONE = b"\xff\xff\xff\xff"


def convert(body, context=None):
    """Convert a TFL scenery body. Returns ``(new_body, warnings)``.

    ``context`` may carry ``id_map`` to remap the tag references.
    """
    id_map = getattr(context, "id_map", None) if context else None

    if len(body) != SIZE:
        return body, [
            f"scen body is {len(body)} bytes, not {SIZE}; left unconverted"
        ]

    out = bytearray(SIZE)
    for to, frm, length in MOVES:
        out[to : to + length] = body[frm : frm + length]
    out[NETGAME_FIELDS] = b"\xff" * 4

    for offset, tag_type in REFERENCES:
        value = bytes(out[offset : offset + 4])
        if codec.all_off(value):
            out[offset : offset + 4] = NONE
        elif id_map is not None and not codec.all_on(value):
            out[offset : offset + 4] = id_map.map_id(tag_type, value)

    return bytes(out), []
