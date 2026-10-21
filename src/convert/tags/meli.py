"""Convert a ``meli`` (mesh lighting) tag body from TFL to Myth II.

TFL's body is 128 bytes of mostly 32-bit IEEE floats; Myth II's is 64 bytes of
16.16 fixed point. Read as Myth II's, a TFL lighting tag gives nonsense --
incident light I = 17530, ambient -16742. Myth II's fields, in the Fear
manual's order: incident light I, J, K; ambient, maximum diffuse, model shading
diffuse and maximum total intensity (16.16 each); then maximum shadow distance,
smoothing Gaussian width and filter width (16-bit each).

Measured across all 8 stock TFL lighting tags and 28 distinct Myth II ones
(NOTES.md section 18):

* **Incident light I, J, K** are TFL's floats 16..18 -- 1.0, 1.0, -0.6 in all
  8; K matches Bungie's own Myth II tags exactly (``gras``: 0.95, 1.0, -0.6).
* **Maximum shadow distance** is TFL's first 16-bit word at byte 16 -- 64 in
  all 8, Myth II's usual value.
* **The intensities** have no clean one-to-one match among TFL's other floats,
  and Myth II's are near-uniform: Bungie's three base-game tags agree exactly
  (ambient 0.1, diffuse 1.0, model shading 0.3, total 0.95, smoothing 3, filter
  0x4000). Those are used. Per-map tone -- darker caves, brighter snow -- is not
  carried yet; TFL's float 9 is a candidate for maximum total (0.85 for moon
  light, as in Magma's moon) on too little evidence to use.
"""

import struct

HANDLES = (b"meli",)

TFL_SIZE = 128
SB_SIZE = 64

TFL_INCIDENT = 16 * 4  # floats 16..18
TFL_SHADOW_DISTANCE = 4 * 4  # first 16-bit word of the 5th 32-bit slot

# Bungie's base-game values, identical across gras, 16cs and lods.
AMBIENT = 0.1
MAXIMUM_DIFFUSE = 1.0
MODEL_SHADING = 0.3
MAXIMUM_TOTAL = 0.95
SMOOTHING_WIDTH = 3
FILTER_WIDTH = 0x4000


def _fixed(value):
    return max(-0x80000000, min(0x7FFFFFFF, int(round(value * 65536))))


def convert(body, context=None):
    """Convert a TFL mesh lighting body. Returns ``(new_body, warnings)``."""
    if len(body) != TFL_SIZE:
        return body, [
            f"meli body is {len(body)} bytes, not {TFL_SIZE}; left unconverted"
        ]

    i, j, k = struct.unpack_from(">3f", body, TFL_INCIDENT)
    (shadow_distance,) = struct.unpack_from(">h", body, TFL_SHADOW_DISTANCE)

    out = struct.pack(
        ">7i3h30x",
        _fixed(i),
        _fixed(j),
        _fixed(k),
        _fixed(AMBIENT),
        _fixed(MAXIMUM_DIFFUSE),
        _fixed(MODEL_SHADING),
        _fixed(MAXIMUM_TOTAL),
        shadow_distance,
        SMOOTHING_WIDTH,
        FILTER_WIDTH,
    )
    assert len(out) == SB_SIZE, len(out)
    return out, []
