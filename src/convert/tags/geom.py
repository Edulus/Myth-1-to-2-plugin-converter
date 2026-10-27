"""Convert a ``geom`` (a model's 3D geometry) tag body from TFL to Myth II.

The header grows from 96 bytes to Myth II's 128 (mythextract
``myth_tags.GeomFmt``); every count, section offset and size is unchanged, and
the data after the header is copied as it is. Measured against the stock TFL
tags and Magma's ports (NOTES.md section 17):

- ``data_offset`` follows the header, 96 -> 128.
- The bounding box Myth II adds is the min/max of the vertices, which are
  (x, y, z) int16 triples; it matches Magma's in 90 of 91 geometries.
- ``center_z`` is 0 in 90 of 91 of Magma's (TFL holds half the height).

Myth II-only defaults, agreed and recorded in NOTES.md section 20: the tails of
material records (bytes 58..63) and the surface flag bits Magma sometimes adds
are left as TFL has them. 43 of Magma's 91 geometries are byte-identical to
TFL's in that data, so Myth II accepts it.
"""

import struct

from ... import codec

HANDLES = (b"geom",)

_HEAD = [
    ("L", "flags"),
    ("4s", "collection_reference_tag"),
    ("h", "material_count"),
    ("h", "vertex_count"),
    ("h", "surface_count"),
    ("h", "dependency_count"),
    ("h", "center_x"),
    ("h", "center_y"),
    ("h", "center_z"),
    ("6x", None),
    ("L", "materials_offset"),
    ("L", "materials_size"),
    ("L", "materials_ptr"),
    ("L", "vertex_offset"),
    ("L", "vertex_size"),
    ("L", "vertex_ptr"),
    ("L", "surface_offset"),
    ("L", "surface_size"),
    ("L", "surface_ptr"),
    ("L", "dependency_offset"),
    ("L", "dependency_size"),
    ("L", "dependency_ptr"),
    ("L", "data_offset"),
    ("L", "data_size"),
    ("L", "data_ptr"),
]
TFLGeom = codec.Struct("TFLGeom", _HEAD + [("8x", None)])
SBGeom = codec.Struct(
    "SBGeom",
    _HEAD
    + [
        ("h", "bounds_min_x"),
        ("h", "bounds_min_y"),
        ("h", "bounds_min_z"),
        ("h", "bounds_max_x"),
        ("h", "bounds_max_y"),
        ("h", "bounds_max_z"),
        ("28x", None),
    ],
)

VERTEX_SIZE = 6


def convert(body, context=None):
    """Convert a TFL geometry body. Returns ``(new_body, warnings)``.

    ``context`` may carry ``id_map`` to remap the collection reference.
    """
    id_map = getattr(context, "id_map", None) if context else None

    if len(body) < TFLGeom.size:
        return body, [f"geom body is {len(body)} bytes, shorter than its header; left unconverted"]
    head = TFLGeom.unpack(body)
    if head.data_offset != TFLGeom.size:
        return body, [f"geom data starts at {head.data_offset}, not {TFLGeom.size}; left unconverted"]
    data = bytes(body[head.data_offset : head.data_offset + head.data_size])
    vertices_end = head.vertex_offset + head.vertex_count * VERTEX_SIZE
    if len(data) != head.data_size or head.vertex_count < 1 or vertices_end > len(data):
        return body, ["geom vertices lie outside its data; left unconverted"]

    points = [struct.unpack_from(">hhh", data, head.vertex_offset + i * VERTEX_SIZE) for i in range(head.vertex_count)]
    low = [min(p[axis] for p in points) for axis in range(3)]
    high = [max(p[axis] for p in points) for axis in range(3)]

    collection = head.collection_reference_tag
    if id_map is not None and not codec.all_off(collection) and not codec.all_on(collection):
        collection = id_map.map_id(b"core", collection)

    # The bytes mythextract calls padding after center_z are not padding:
    # Magma's ports keep TFL's values there, so the original header is the base.
    padded = bytes(body[: TFLGeom.size]) + bytes(SBGeom.size - TFLGeom.size)
    new_head = SBGeom.unpack(padded).replace(
        collection_reference_tag=collection,
        center_z=0,
        data_offset=SBGeom.size,
        bounds_min_x=low[0], bounds_min_y=low[1], bounds_min_z=low[2],
        bounds_max_x=high[0], bounds_max_y=high[1], bounds_max_z=high[2],
    )
    return new_head.encode() + data + bytes(body[head.data_offset + head.data_size :]), []
