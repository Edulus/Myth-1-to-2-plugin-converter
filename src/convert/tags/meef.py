"""Convert a ``meef`` (mesh effect: the ground ripple of an explosion) tag body
from TFL to Myth II.

TFL's body is 32 bytes, Myth II's 36. Myth II's layout, in the Fear manual's
order: flags, amplitude, velocity, cutoff radius, dissipation, epicenter offset,
camera shaking type, then a shockwave block -- collection reference, sequence,
radial points, thickness, height offset -- which TFL does not have. Read as
Myth II's, TFL bytes land in the collection reference: in-engine, "couldn't
read header for collection reference definition" for the satchel charge, which
took the dwarves and the shade's magic down with it (NOTES.md section 18).

Evidence is thin -- 4 stock TFL mesh effects, 13 Myth II ones (Magma's 3 plus
the base game's 10) -- but one pair is decisive: Bungie's own Myth II port of
TFL's wight explosion (``wiex``).

* **Flags** carry over (Bungie's ``wiex`` and Magma's ports agree).
* **Amplitude** doubles: TFL 205, Bungie's port 409 -- Myth II halved the world
  unit (the Fear manual), and Bungie doubled the value. Magma did not, for its
  satchel charge; Bungie's own port is the authority used here.
* **Cutoff radius** is a 32-bit float in TFL (bytes 12..16) and an integer in
  Myth II: 256.0 -> 256 in Bungie's ``wiex`` and Magma's ``sace``.
* No TFL field has been tied to **velocity**: it gets Bungie's ``wiex`` value,
  0x0800, also the median of the 13. TFL's word at 16 (16, 1, 8, 4 across the
  four) and its constant 0x1998 at 10 are not carried.
* **Dissipation** 0x0066 (9/13), **epicenter offset** 0 (10/13), **camera
  shaking** none (-1, 9/13), and the shockwave block -- collection ``inme``,
  sequence 16, 32 radial points, thickness and height 512 -- as on 12 of 13.
"""

import struct

HANDLES = (b"meef",)

TFL_SIZE = 32
SB_SIZE = 36

VELOCITY = 0x0800
DISSIPATION = 0x0066
EPICENTER_OFFSET = 0
NO_CAMERA_SHAKE = -1
SHOCKWAVE_COLLECTION = b"inme"
SHOCKWAVE = (16, 32, 512, 512)  # sequence, radial points, thickness, height offset


def convert(body, context=None):
    """Convert a TFL mesh effect body. Returns ``(new_body, warnings)``.

    ``context`` may carry ``id_map``, which may rename the shockwave collection.
    """
    id_map = getattr(context, "id_map", None) if context else None

    if len(body) != TFL_SIZE:
        return body, [
            f"meef body is {len(body)} bytes, not {TFL_SIZE}; left unconverted"
        ]

    flags, amplitude = struct.unpack_from(">Lh", body, 0)
    (cutoff,) = struct.unpack_from(">f", body, 12)
    collection = SHOCKWAVE_COLLECTION
    if id_map is not None:
        collection = id_map.map_id(b"core", collection)

    out = struct.pack(
        ">L6h4s4h8x",
        flags,
        max(-0x8000, min(0x7FFF, amplitude * 2)),
        VELOCITY,
        max(0, min(0x7FFF, int(round(cutoff)))),
        DISSIPATION,
        EPICENTER_OFFSET,
        NO_CAMERA_SHAKE,
        collection,
        *SHOCKWAVE,
    )
    assert len(out) == SB_SIZE, len(out)
    return out, []
