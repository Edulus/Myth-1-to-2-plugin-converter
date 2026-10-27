"""Convert a ``mode`` (model: a placed building) tag body from TFL to Myth II.

Both games use mythextract's ``myth_tags.ModelFmt``: a 64-byte header, then
geometry vertex flags, permutations and the footprint, in that order. Only the
footprint changes. It lists the terrain cells the building covers as
(x, y, flags) records of 8 bytes, and Myth II's cells are half the size, so
each TFL cell becomes the 2x2 block of cells covering the same ground, in rows:
(2x, 2y), (2x+1, 2y), (2x, 2y+1), (2x+1, 2y+1), flags unchanged.

Measured against the stock TFL tags and Magma's ports, footprints are TFL's
split this way in 81 of 91 models, the rest hand-edited (NOTES.md section 17);
everything before the footprint is byte-identical in all 91.
"""

import struct

from ... import codec

HANDLES = (b"mode",)

Model = codec.Struct(
    "Model",
    [
        ("L", "flags"),
        ("4s", "geometry_tag"),
        ("h", "geometry_index"),
        ("H", "vertex_flags_count"),
        ("H", "permutation_count"),
        ("H", "mesh_cell_count"),
        ("L", "geometry_vertex_offset"),
        ("L", "geometry_vertex_size"),
        ("l", "geometry_vertex_ptr"),
        ("L", "permutations_offset"),
        ("L", "permutations_size"),
        ("L", "permutations_ptr"),
        ("L", "mesh_cell_offset"),
        ("L", "mesh_cell_size"),
        ("L", "mesh_cell_ptr"),
        ("L", "data_offset"),
        ("L", "data_size"),
        ("L", "data_ptr"),
    ],
)

CELL_SIZE = 8


def convert(body, context=None):
    """Convert a TFL model body. Returns ``(new_body, warnings)``.

    ``context`` may carry ``id_map`` to remap the geometry reference.
    """
    id_map = getattr(context, "id_map", None) if context else None

    if len(body) < Model.size:
        return body, [f"mode body is {len(body)} bytes, shorter than its header; left unconverted"]
    head = Model.unpack(body)
    cells_at = head.data_offset + head.mesh_cell_offset
    cells_end = cells_at + head.mesh_cell_count * CELL_SIZE
    if (
        head.mesh_cell_size != head.mesh_cell_count * CELL_SIZE
        or head.mesh_cell_offset + head.mesh_cell_size != head.data_size
        or cells_end > len(body)
    ):
        return body, ["mode footprint is not the last section of the body; left unconverted"]

    source = sorted(
        (struct.unpack_from(">hhh", body, cells_at + i * CELL_SIZE), body[cells_at + i * CELL_SIZE + 6 : cells_at + (i + 1) * CELL_SIZE])
        for i in range(head.mesh_cell_count)
    )
    cells = bytearray()
    for (x, y, flags), pad in source:
        for dy in (0, 1):
            for dx in (0, 1):
                cells += struct.pack(">hhh", 2 * x + dx, 2 * y + dy, flags) + pad

    geometry = head.geometry_tag
    if id_map is not None and not codec.all_off(geometry) and not codec.all_on(geometry):
        geometry = id_map.map_id(b"geom", geometry)

    new_head = head.replace(
        geometry_tag=geometry,
        mesh_cell_count=head.mesh_cell_count * 4,
        mesh_cell_size=len(cells),
        data_size=head.mesh_cell_offset + len(cells),
    )
    return new_head.encode() + bytes(body[Model.size : cells_at]) + bytes(cells) + bytes(body[cells_end:]), []
