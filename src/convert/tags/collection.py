"""Convert a ``.256`` sprite collection from TFL to Myth II.

mythextract reads both games' collections with one layout
(``myth_collection.Header256Fmt`` and friends), and it is right that the
*records* are the same. What differs is where the data starts, and what TFL
left behind in its files. Measured against the 198 collections present both in
the stock TFL tags and `Magma - The Fallen Lords v1.9` (NOTES.md section 18):

* **Myth II's data block starts with 32 bytes the sections come after.** In
  191 of Magma's 198 it holds ``"This tag was saved by Amber 2.0"`` -- an editor
  stamp, not engine data; zeros are written here. Every section offset in the
  header moves 32 later (an empty section's offset is 0), as do the offsets in
  each bitmap reference and sequence reference, which count from the start of
  the data block too. ``data_size`` grows by 32.
* **TFL saved runtime memory addresses into its files; Myth II stores zeros.**
  The header's section pointers, bitmap and sequence references' runtime words,
  each bitmap's metadata after ``encoding``, and the bitmap's row address table
  (one 4-byte address per pixel row, before the pixels).

Pixels, colour tables, sequences and shadow maps are otherwise untouched. With
these rules, 48 of the 79 shared collections Magma left unedited reproduce
byte-for-byte and the rest agree in 99.989% of bytes. In-engine, unconverted
collections drew units' and scenery's shadows but not the sprites themselves.

**A landscape -- a level's ground texture -- keeps only its tiles.** It is the
one kind of collection with no sequences, and is two 256x256 tiles per
submesh. Seven of TFL's 34 landscapes (Crow's Bridge, Traitor, Bagrada in
Winter, ...) end with one more, smaller bitmap; *The Fallen Levels v2* drops it
from every one it ports. A converted Crow's Bridge that still had it crashed Myth II
while building ground tiles at the map's edge, which this is meant to fix. The
reference is dropped from the count; its bytes stay, unreferenced, so no other
offset moves.
"""

import struct

HANDLES = (b".256",)

HEADER_SIZE = 320
INSERTED = 32

SECTIONS = 8  # colour tables, hue changes, bitmap refs, instances, sequence refs, shadows, blends, remaps
SECTION_AT = 64  # each: count, offset, size, runtime pointer (4 x u32)
DATA_SIZE_AT = 252

BITMAP_REFS, SEQUENCE_REFS = 2, 4
REFERENCE_SIZE = 128  # BitmapReferenceFmt, SequenceRefFmt
REFERENCE_OFFSET_AT = 64

BITMAP_META_SIZE = 52
BITMAP_META_RUNTIME = slice(18, 52)
NO_ROW_ADDRESS_TABLE = 1 << 5

LANDSCAPE_TILE = (256, 256)


def _u32(buf, at):
    return struct.unpack_from(">I", buf, at)[0]


def convert(body, context=None):
    """Convert a TFL collection body. Returns ``(new_body, warnings)``."""
    if len(body) < HEADER_SIZE:
        return body, [
            f".256 body is {len(body)} bytes, shorter than the {HEADER_SIZE}-byte "
            f"header; left unconverted"
        ]

    data_size = _u32(body, DATA_SIZE_AT)
    sections = [struct.unpack_from(">3I", body, SECTION_AT + 16 * k) for k in range(SECTIONS)]
    for count, offset, size in sections:
        if (count or size) and HEADER_SIZE + offset + size > len(body):
            return body, [
                f".256 section at {offset}+{size} lies outside the "
                f"{len(body)}-byte body; left unconverted"
            ]

    out = bytearray(body[:HEADER_SIZE]) + bytes(INSERTED) + body[HEADER_SIZE:]

    for k, (count, offset, size) in enumerate(sections):
        at = SECTION_AT + 16 * k
        struct.pack_into(">I", out, at + 4, offset + INSERTED if (count or size) else 0)
        struct.pack_into(">I", out, at + 12, 0)
    struct.pack_into(">I", out, DATA_SIZE_AT, data_size + INSERTED)

    data = HEADER_SIZE + INSERTED
    for kind in (BITMAP_REFS, SEQUENCE_REFS):
        count, offset, _size = sections[kind]
        for r in range(count):
            at = data + offset + REFERENCE_SIZE * r
            if at + REFERENCE_SIZE > len(out):
                break
            target = _u32(out, at + REFERENCE_OFFSET_AT)
            struct.pack_into(">I", out, at + REFERENCE_OFFSET_AT, target + INSERTED)
            if kind == SEQUENCE_REFS:
                out[at + 72 : at + REFERENCE_SIZE] = bytes(REFERENCE_SIZE - 72)
                continue
            out[at + 72 : at + 76] = bytes(4)

            meta = data + target
            if meta + BITMAP_META_SIZE > len(out):
                continue
            out[meta + BITMAP_META_RUNTIME.start : meta + BITMAP_META_RUNTIME.stop] = bytes(
                BITMAP_META_RUNTIME.stop - BITMAP_META_RUNTIME.start
            )
            height, _bpr, flags = struct.unpack_from(">HhH", out, meta + 2)
            if not flags & NO_ROW_ADDRESS_TABLE and height > 1:
                table = meta + BITMAP_META_SIZE
                out[table : table + 4 * (height - 1)] = bytes(4 * (height - 1))

    warnings = _trim_landscape(out, sections)
    return bytes(out), warnings


def _trim_landscape(out, sections):
    """Drop the bitmaps after a landscape's tiles, in place. Returns warnings."""
    count, offset, _size = sections[BITMAP_REFS]
    if sections[SEQUENCE_REFS][0] or not count:
        return []
    data = HEADER_SIZE + INSERTED
    sizes = []
    for r in range(count):
        at = data + offset + REFERENCE_SIZE * r
        if at + REFERENCE_SIZE > len(out):
            return []
        meta = HEADER_SIZE + _u32(out, at + REFERENCE_OFFSET_AT)  # already moved by INSERTED
        if meta + 4 > len(out):
            return []
        sizes.append(struct.unpack_from(">HH", out, meta))
    tiles = 0
    while tiles < count and sizes[tiles] == LANDSCAPE_TILE:
        tiles += 1
    if not tiles or tiles == count or LANDSCAPE_TILE in sizes[tiles:]:
        return []
    at = SECTION_AT + 16 * BITMAP_REFS
    struct.pack_into(">I", out, at, tiles)
    struct.pack_into(">I", out, at + 8, tiles * REFERENCE_SIZE)
    shown = ", ".join(f"{w}x{h}" for w, h in sizes[tiles:])
    return [f"landscape: dropped {count - tiles} bitmap(s) after its {tiles} tiles ({shown})"]
