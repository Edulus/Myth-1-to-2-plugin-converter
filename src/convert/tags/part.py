"""Convert a ``part`` (particle system: rain, snow, ash) tag body from TFL to
Myth II.

TFL's body is 128 bytes, Myth II's 132. mythextract declares the Myth II layout
(``myth_tags.ParticleSysFmt``); compared with the 4 particle systems present in
both the stock TFL tags and `Magma - The Fallen Lords v1.9`, the first 92 bytes
-- flags through ``splash_local_projectile_group_tag`` -- are the same layout in
both games (Magma retuned view distances and scale, nothing else). From 92 on,
Myth II has a splash box that TFL does not, and TFL's bytes there are zero.

A zero ``box_width`` is a divisor: in-engine, Tandem crashed with
EXCEPTION_INT_DIVIDE_BY_ZERO in ``_build_particle_system_surface_list``
(particle_systems.c:352) on its first frame. The box therefore gets the values
Magma's 7 particle systems agree on most (count of 7 in the comments).
"""

import struct

from ... import codec

HANDLES = (b"part",)

TFL_SIZE = 128
SB_SIZE = 132
SHARED = 92

SPLASH_BOX = struct.pack(
    ">HHhHH",
    4,  # box_width -- 4/7 (8 in the rest); never 0, it is divided by
    0x0800,  # box_top_height -- 5/7
    -0x200,  # box_bottom_height (0xfe00) -- 3/7, plurality
    1,  # max_splashes_per_cell -- 5/7
    8,  # time_between_building_effects -- 4/7
)

REFERENCES = (
    (4, b"core"),  # collection_reference_tag
    (84, b"amso"),  # ambient_sound_tag
    (88, b"lpgr"),  # splash_local_projectile_group_tag
)


def convert(body, context=None):
    """Convert a TFL particle system body. Returns ``(new_body, warnings)``.

    ``context`` may carry ``id_map`` to remap the tag references.
    """
    id_map = getattr(context, "id_map", None) if context else None

    if len(body) != TFL_SIZE:
        return body, [
            f"part body is {len(body)} bytes, not {TFL_SIZE}; left unconverted"
        ]

    warnings = []
    if any(body[SHARED:]):
        warnings.append(
            f"TFL bytes {SHARED}..{TFL_SIZE} are not zero; replaced by the "
            f"Myth II splash box defaults"
        )

    out = bytearray(body[:SHARED] + SPLASH_BOX)
    out += b"\0" * (SB_SIZE - len(out))

    if id_map is not None:
        for offset, tag_type in REFERENCES:
            value = bytes(out[offset : offset + 4])
            if codec.all_on(value) or codec.all_off(value):
                continue
            out[offset : offset + 4] = id_map.map_id(tag_type, value)

    return bytes(out), warnings
