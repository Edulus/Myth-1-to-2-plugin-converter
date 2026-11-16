"""Convert an ``amso`` (ambient sound) tag body from TFL to Myth II.

The layout is the same 64 bytes in both games (mythextract
``myth_sound.AmsoFmt``): flags, radii, period, six sound tag slots at bytes
12..36, a random-sound radius and six sound indexes. What differs is how an
unused sound slot is written: **TFL writes zero, Myth II writes ``FFFFFFFF``**.

Measured over the stock TFL ambient sounds also present in Myth II's own tags
(33) and in `Magma - The Fallen Lords v1.9` (22): of 220 slots that are zero in
TFL, 208 are ``FFFFFFFF`` in the Myth II copy; every slot that names a sound is
carried as it is (46 of 57 identical, the rest retuned by hand); bytes 38..64
are identical in all 55 pairs. Bungie also retuned some radii, which is tuning,
not format, and is not copied here. Same rule as the `proj` converter's "zero
references written as none".
"""

HANDLES = (b"amso",)

SIZE = 64
SOUND_TAGS_AT = 12
SOUND_SLOTS = 6
NONE = b"\xff\xff\xff\xff"


def convert(body, context=None):
    """Convert a TFL ambient sound body. Returns ``(new_body, warnings)``."""
    if len(body) != SIZE:
        return body, [f"amso body is {len(body)} bytes, not {SIZE}; left unconverted"]
    out = bytearray(body)
    for slot in range(SOUND_SLOTS):
        at = SOUND_TAGS_AT + 4 * slot
        if out[at : at + 4] == bytes(4):
            out[at : at + 4] = NONE
    return bytes(out), []
