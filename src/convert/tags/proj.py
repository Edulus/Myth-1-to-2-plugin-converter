"""Convert a ``proj`` (projectile) tag body from TFL to Myth II.

Both games store a projectile in 256 bytes, but not in the same layout.
mythextract declares only the Myth II one (``myth_projectile.ProjFmt``), so the
TFL side was measured: the 104 projectile IDs present both in the stock TFL tags
and in `Magma - The Fallen Lords v1.9` were compared field by field (NOTES.md
section 18). Handed to Myth II unconverted, a TFL projectile reads a tag
reference out of the wrong bytes -- in-engine, "couldn't read header for
projectile definition '    '", which then takes down every projectile group,
media and mesh that uses it.

The differences, all mechanical:

* **TFL has 4 more bytes at offset 76..80**, just before the animation-rate
  pair. Everything after them sits 4 bytes later in TFL than in Myth II -- the
  tag references anchor it exactly (promoted projectile 96 -> 92, artifact
  124 -> 120, local projectile group 140 -> 136). Their meaning is unknown
  (0x01000000 in 270 of 365 stock projectiles); they are dropped, and the
  4 bytes are given back as zero padding at the end so the size stays 256.
* **Flag bit 1 means something else in TFL.** Myth II reads it as
  ``IS_GUIDED``; TFL sets it on 86 of 104 compared projectiles, all of them
  thrown physical debris -- body parts, bones, apples, barrel boards -- and
  never on melee swings, lightning or splashes. Copied across, every piece of
  debris would home in on a target. Myth II has no bit with TFL's meaning, so
  it is cleared. Every other flag bit keeps its meaning (88-104 of 104 agree).
* **"No tag" is spelled differently.** TFL zero-fills the reference fields it
  does not use; Myth II writes 0xFFFFFFFF ("none") -- geometry, for instance,
  in 102 of 104. Zero references become "none", except ``script_tag``, which
  is zero in every one of Magma's 273 projectiles.

What remains different after that is Magma's own editing, not format: renamed
objects and contrails, retuned accelerations, bloody flags added.
"""

from ... import codec

HANDLES = (b"proj",)

SIZE = 256

# TFL bytes with no Myth II destination (see the module docstring).
TFL_ONLY = slice(76, 80)

TFL_DEBRIS_FLAG = 1 << 1  # Myth II reads this bit as IS_GUIDED

# Myth II offsets of the projectile's tag references, with the type each
# names (mythextract myth_projectile.ProjFmt).
REFERENCES = (
    (4, b".256"),  # collection_tag
    (16, b"prgr"),  # detonation_projectile_group_tag
    (20, b"proj"),  # contrail_projectile_tag
    (28, b"obje"),  # object_tag
    (52, b"ligh"),  # lightning_tag
    (60, b"soun"),  # flight_sound_tag
    (64, b"soun"),  # rebound_sound_tag
    (68, b"soun"),  # sound_tag_3
    (72, b"soun"),  # sound_tag_4
    (92, b"proj"),  # promoted_projectile_tag
    (96, b"prgr"),  # promotion_projectile_group_tag
    (120, b"arti"),  # artifact_tag
    (124, b"prgr"),  # target_detonation_projectile_group_tag
    (128, b"geom"),  # geometry_tag
    (136, b"lpgr"),  # local_projectile_group_tag
    (144, b"unit"),  # promotion_unit_tag
)

NONE = b"\xff\xff\xff\xff"


def convert(body, context=None):
    """Convert a TFL projectile body. Returns ``(new_body, warnings)``.

    ``context`` may carry ``id_map`` to remap the tag references.
    """
    id_map = getattr(context, "id_map", None) if context else None

    if len(body) != SIZE:
        return body, [
            f"proj body is {len(body)} bytes, not {SIZE}; left unconverted"
        ]

    out = bytearray(body[: TFL_ONLY.start] + body[TFL_ONLY.stop :])
    out += b"\0" * (SIZE - len(out))

    flags = int.from_bytes(out[0:4], "big") & ~TFL_DEBRIS_FLAG
    out[0:4] = flags.to_bytes(4, "big")

    for offset, tag_type in REFERENCES:
        value = bytes(out[offset : offset + 4])
        if codec.all_off(value):
            out[offset : offset + 4] = NONE
        elif id_map is not None and not codec.all_on(value):
            out[offset : offset + 4] = id_map.map_id(tag_type, value)

    return bytes(out), []
