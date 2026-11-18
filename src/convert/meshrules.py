"""Conversion rules for meshes: what changes when a TFL mesh becomes a Myth II one.

The mesh layouts (headers, marker, palette and map-action structs, terrain cell
formats) live in `src/mesh.py`; this module holds the policy built on them --
terrain upsampling, grounding and anchoring of markers, ground lowering, LOD data,
netgame masks, map-action fix-ups and tag-ID remapping. Each rule cites its notes
section (``documentation/notes/<file>.md section N``) where it has one.
"""

import struct

from .. import codec, formats
from ..mesh import (
    CELL_FLAGS_OFFSET,
    MAP_ACTION_HEAD_SIZE,
    MARKER_HEAD_SIZE,
    MARKER_PALETTE_ENTRY_SIZE,
    MARKER_TYPE_TO_TAG,
    NO_MODEL_INDEX,
    SB_CELL_SIZE,
    SB_CELL_WORLD_SIZE,
    TFL_CELL_SIZE,
    MapActionHead,
    MarkerHead,
    MarkerPaletteEntry,
    MarkerType,
    cell_counts,
    ground_height,
    map_action_tag_refs,
    param_data_length,
    resolve_param_type,
)

def convert_tfl_map_actions(action_buffer, action_count):
    """Rewrite parameter type codes in a TFL map-action buffer to Myth II's.

    ``action_buffer`` is exactly ``map_action_buffer_size`` bytes, starting at
    a mesh's ``map_actions_offset`` (mythextract ``parse_map_actions`` slices
    the same span before walking it). Only the 2-byte type discriminator at
    the front of each parameter is ever rewritten; every other byte --
    counts, names, and all parameter data -- is copied unchanged, because a
    TFL-vs-Myth-II type mismatch changes what a code *means*, never how the
    data behind it is encoded.

    Returns ``(new_buffer, warnings)``. On an unrecognised parameter type,
    the rest of that action's parameters are left untouched and a warning is
    recorded, since the byte length of an unrecognised type cannot be
    trusted and guessing risks desyncing every later parameter.
    """
    warnings = []
    out = bytearray(action_buffer)
    action_head_end = action_count * MAP_ACTION_HEAD_SIZE

    for action in MapActionHead.unpack_many(action_buffer, 0, action_count):
        offset = action_head_end + action.offset
        remaining = action.num_params
        while remaining > 0:
            raw_type, count = struct.unpack_from(">HH", action_buffer, offset)
            try:
                semantic = resolve_param_type(raw_type, formats.TFL)
            except ValueError:
                warnings.append(
                    f"map action {action.id} ({codec.decode_string(action.type)}): "
                    f"unrecognised parameter type {raw_type}; left unconverted from "
                    f"here on, along with {remaining - 1} later parameter(s) in "
                    f"this action"
                )
                break
            new_raw = int(semantic)
            if new_raw != raw_type:
                struct.pack_into(">H", out, offset, new_raw)
            offset += 8 + param_data_length(semantic, count)
            remaining -= 1

    return bytes(out), warnings


def remap_map_action_tags(action_buffer, action_count, id_map):
    """Rename the tag ids in a Myth II map-action buffer's ``SOUND`` and
    ``PROJECTILE`` parameters through ``id_map`` (improvement plan item A3).

    Run after `convert_tfl_map_actions`, so type codes are already Myth II's.
    Same size in, same size out. Returns ``(new_buffer, renamed_count)``.
    """
    out = bytearray(action_buffer)
    renamed = 0
    for at, tag_type, tag_id in map_action_tag_refs(action_buffer, action_count, formats.SB):
        mapped = id_map.map_id(tag_type, tag_id)
        if mapped != tag_id:
            out[at : at + 4] = mapped
            renamed += 1
    return bytes(out), renamed


# TFL cell flags -> Myth II cell flags. The byte sits at the same offset in
# both games but does not mean the same: copied unchanged, TFL's 0x21 on
# Crow's Bridge's deck made Myth II leave the deck undrawn, so units on it
# walked on air (Keep, Q7). Each entry is the value Project Magma's ports
# (*The Fallen Levels v2*) most often hold where TFL holds the key, over all
# four Myth II cells of each TFL cell on the 11 levels they share with TFL.
# It matches their flags on 95.5% of cells, against 84.2% copied (documentation/notes/maps.md
# section 23). Values not listed (0x00 among them) are kept.
TFL_TO_SB_CELL_FLAGS = {
    0x01: 0x00,
    0x10: 0x38,
    0x11: 0x3D,
    0x15: 0x3D,
    0x18: 0x00,
    0x19: 0x00,
    0x1D: 0x3D,
    0x20: 0x00,
    0x21: 0x20,
    0x28: 0x20,
    0x29: 0x20,
    0x3D: 0x00,
}


def upsample_terrain(terrain, submesh_width, submesh_height, media_height=0):
    """Convert a TFL terrain block into a Myth II one.

    Each TFL cell becomes the 2x2 block of Myth II cells covering the same
    ground. The top-left cell keeps the TFL height; the other three take the
    average of the TFL heights at their corners, so slopes stay slopes instead
    of becoming 2x2 steps. The flags are translated through
    `TFL_TO_SB_CELL_FLAGS`; every other field is copied unchanged.

    This matches Project Magma's hand port of Crow's Bridge (*The Fallen Levels
    v2*): their heights equal TFL's at the original points and sit halfway
    between them elsewhere, while their normals are copied, not blended or
    recomputed. Blending brought our mean height gap to their port from 48 to
    21 (documentation/notes/maps.md section 20).

    ``media_height`` is a Myth II-only per-cell field with no TFL source. It is
    the height of the water *surface*, and is a single constant across nearly
    every native mesh, so it is passed in as one value rather than derived.

    Returns the new terrain bytes.
    """
    columns, rows = cell_counts(submesh_width, submesh_height, formats.TFL)
    expected = columns * rows * TFL_CELL_SIZE
    if len(terrain) < expected:
        raise ValueError(
            f"terrain block is {len(terrain)} bytes, need {expected} for a "
            f"{submesh_width}x{submesh_height}-submesh TFL mesh "
            f"({columns}x{rows} cells)"
        )

    # The four bytes Myth II adds to every cell. Identical for all of them, so
    # built once.
    suffix = struct.pack(">hH", media_height, NO_MODEL_INDEX)

    def cell(x, y):
        start = (y * columns + x) * TFL_CELL_SIZE
        source = bytearray(terrain[start : start + TFL_CELL_SIZE])
        flags = source[CELL_FLAGS_OFFSET]
        source[CELL_FLAGS_OFFSET] = TFL_TO_SB_CELL_FLAGS.get(flags, flags)
        return bytes(source)

    heights = [
        [struct.unpack_from(">h", terrain, (y * columns + x) * TFL_CELL_SIZE)[0] for x in range(columns)]
        for y in range(rows)
    ]

    def with_height(source, height):
        return struct.pack(">h", height) + source[2:] + suffix

    out = bytearray()
    for y in range(rows):
        below = min(y + 1, rows - 1)  # the last row has nothing below to blend with
        top = bytearray()
        bottom = bytearray()
        for x in range(columns):
            right = min(x + 1, columns - 1)
            source = cell(x, y)
            here, east = heights[y][x], heights[y][right]
            south, southeast = heights[below][x], heights[below][right]
            top += source + suffix
            top += with_height(source, (here + east) // 2)
            bottom += with_height(source, (here + south) // 2)
            bottom += with_height(source, (here + east + south + southeast) // 4)
        out += top
        out += bottom

    return bytes(out)


# Markers whose height is the ground under them. TFL appears to have placed
# these on the ground whatever pos_z said; Myth II uses pos_z, so a stale value
# leaves a bush floating or buried. Project Magma's port of Crow's Bridge puts
# all of them on its ground and leaves sounds, models and projectile groups be.
GROUNDED_MARKER_TYPES = {MarkerType.OBSERVER, MarkerType.SCENERY, MarkerType.UNIT}


def place_markers_on_ground(markers, count, terrain, submesh_width, submesh_height):
    """Set each grounded marker's pos_z to the ground under it.

    ``markers`` is a mesh's marker block and ``terrain`` its converted Myth II
    terrain block. Returns ``(markers, moved)``: the new block, and how many
    markers changed height.
    """
    columns, rows = cell_counts(submesh_width, submesh_height, formats.SB)
    out = bytearray(markers)
    moved = 0
    for i, marker in enumerate(MarkerHead.unpack_many(markers, 0, count)):
        if marker.type not in GROUNDED_MARKER_TYPES:
            continue
        z = round(ground_height(terrain, columns, rows, marker.pos_x, marker.pos_y))
        if z != marker.pos_z:
            start = i * MARKER_HEAD_SIZE
            out[start : start + MARKER_HEAD_SIZE] = marker.replace(pos_z=z).encode()
            moved += 1
    return bytes(out), moved


def place_models_by_centre(markers, count, palette, palette_entries, centres):
    """Move each model marker from where TFL anchors a model to where Myth II
    does.

    TFL places a model by a corner, Myth II by its geometry's centre. Across
    the 17 levels of *The Fallen Levels v2* that pair with stock TFL levels,
    Magma moved every copy of a model by the same amount, and for nearly every
    model that amount is the geometry's (center_x, center_y) rounded to a whole
    Myth II cell, whatever way the model faces (documentation/notes/models.md section 17).

    ``palette`` is the mesh's marker palette, whose model entries are indexed
    by a model marker's ``palette_index``; ``centres`` maps a TFL model id to
    its geometry's centre. Returns ``(markers, moved, missing)``, ``missing``
    being the model ids with no known centre, whose markers are left alone.
    """
    entries = MarkerPaletteEntry.unpack_many(palette, 0, palette_entries)
    models = [e.marker_tag for e in entries if e.type == MarkerType.MODEL]
    out = bytearray(markers)
    moved, missing = 0, set()
    for i, marker in enumerate(MarkerHead.unpack_many(markers, 0, count)):
        if marker.type != MarkerType.MODEL or marker.palette_index >= len(models):
            continue
        model = models[marker.palette_index]
        if model not in centres:
            missing.add(model)
            continue
        dx, dy = (_whole_cells(c) for c in centres[model])
        if dx or dy:
            start = i * MARKER_HEAD_SIZE
            shifted = marker.replace(pos_x=marker.pos_x + dx, pos_y=marker.pos_y + dy)
            out[start : start + MARKER_HEAD_SIZE] = shifted.encode()
            moved += 1
    return bytes(out), moved, sorted(missing)


MODEL_WALL_STEP = 400
MODEL_BASE_TOLERANCE = 32


def lower_ground_beside_models(
    terrain, submesh_width, submesh_height, markers, count, palette, palette_entries, reaches
):
    """Drop the blended ground off a model's walls to the model's base.

    TFL drew a model over its ground, so a slope running up the side of a
    model left the model's wall in view. Myth II hides whatever is below the
    ground, and the points `upsample_terrain` blends in between TFL's put a
    slope a little higher than the wall: Crow's Bridge's bridge showed only
    its railings, the ground sagging away from them (Keep, Q7). Magma's port
    drops those points to the foot of the wall.

    So an in-between point inside a model's reach, whose TFL corners step at
    least `MODEL_WALL_STEP` and whose lowest corner is the model's base (its
    marker height, within `MODEL_BASE_TOLERANCE`), takes that lowest height.
    Across the 17 levels of *The Fallen Levels v2* that pair with stock TFL
    levels, this brings Crow's Bridge's 14 such points from a mean of 351
    off Magma's to 48 and Forest Heart's ent bridge's 44 from 2,339 to 1,885;
    under the other five models it touches it is a little nearer on the
    whole (documentation/notes/maps.md section 22). Without the base condition, or with a
    gentler step, it is further off on most of them.

    ``markers`` must already be placed by centre; ``reaches`` maps a TFL
    model id to how far its geometry reaches from its centre, either way, in
    world units (`src.convert.plugin.model_reaches`). Returns
    ``(terrain, lowered)``.
    """
    columns, rows = cell_counts(submesh_width, submesh_height, formats.SB)

    def height(x, y):
        return struct.unpack_from(">h", terrain, (y * columns + x) * SB_CELL_SIZE)[0]

    def corners(i, size):
        # An odd index lies between two TFL points; at the far edge
        # `upsample_terrain` blended the last point with itself.
        return (i,) if i % 2 == 0 else (i - 1, min(i + 1, size - 2))

    entries = MarkerPaletteEntry.unpack_many(palette, 0, palette_entries)
    models = [e.marker_tag for e in entries if e.type == MarkerType.MODEL]
    out = bytearray(terrain)
    lowered = set()
    for marker in MarkerHead.unpack_many(markers, 0, count):
        if marker.type != MarkerType.MODEL or marker.palette_index >= len(models):
            continue
        reach = reaches.get(models[marker.palette_index])
        if not reach:
            continue
        # Strictly inside the reach: a point on its edge is the model's rim.
        x0 = max(int((marker.pos_x - reach) // SB_CELL_WORLD_SIZE) + 1, 0)
        x1 = min(-int(-(marker.pos_x + reach) // SB_CELL_WORLD_SIZE), columns)
        y0 = max(int((marker.pos_y - reach) // SB_CELL_WORLD_SIZE) + 1, 0)
        y1 = min(-int(-(marker.pos_y + reach) // SB_CELL_WORLD_SIZE), rows)
        for y in range(y0, y1):
            for x in range(x0, x1):
                if x % 2 == 0 and y % 2 == 0:
                    continue  # a TFL point, kept as it is
                around = [height(cx, cy) for cy in corners(y, rows) for cx in corners(x, columns)]
                low = min(around)
                if max(around) - low < MODEL_WALL_STEP or abs(low - marker.pos_z) > MODEL_BASE_TOLERANCE:
                    continue
                struct.pack_into(">h", out, (y * columns + x) * SB_CELL_SIZE, low)
                lowered.add((x, y))
    return bytes(out), len(lowered)


def _whole_cells(distance):
    """``distance`` rounded to the nearest whole Myth II cell, halves up."""
    return (distance + SB_CELL_WORLD_SIZE // 2) // SB_CELL_WORLD_SIZE * SB_CELL_WORLD_SIZE


def build_lod_data(submesh_width, submesh_height):
    """A Myth II mesh level-of-detail block, sized to the cell count.

    Every one of the 87 Myth II meshes surveyed -- 47 native campaign meshes and
    40 from a community TFL port -- carries this block at exactly half a byte
    per cell, and none has it empty, so it cannot simply be omitted.

    It is one 16-bit word per four cells. Across 157 real Myth II meshes
    (Bungie's 65, Magma's 92; 1.35 million words) **no word is zero**: the
    second byte's high nibble is 0xF in 99.3% of them, the first byte 0x00 or
    0xFF, and the low nibble holds flag bits (``00f0``, ``00ff``, ``00f1``,
    ``00f4``, ...) whose meaning is not known. Up to 0.13 the converter wrote
    zeros, and explosions left black, streaky ground; saving the same mesh in
    Loathing with a trivial change cured it (Keep, Q7). Keep's before-and-after
    pair of one converted mesh shows Loathing writing ``00f0`` in 5,892 of 6,400
    words and ``fff0`` in the rest, with no height, water or model changed
    (documentation/notes/maps.md section 27). So every word is written as ``00f0``, Loathing's
    base value.
    """
    columns, rows = cell_counts(submesh_width, submesh_height, formats.SB)
    return LOD_BASE_WORD * ((columns * rows) // 4)


LOD_BASE_WORD = b"\x00\xf0"


# A palette entry says which netgame types it appears in, one bit per type (the
# "Appears in Netgame Type" list in Loathing: Body Count, Steal the Bacon, Last
# Man on the Hill, Scavenger Hunt, Flag Rally, Capture the Flag, Balls on
# Parade, Territories, Captures, King of the Hill, ...). TFL's maps leave the
# field 0 on every ordinary entry, and Myth II reads 0 as "appears in no game
# type": a converted free-for-all map loads with no teams, flags, balls or
# scenery, and plays only when marked a single-player map (Keep, Q7). Bungie's
# own Myth II maps and Magma's ports mark ordinary entries for every type.
NETGAME_ALL_TYPES = 0xFFFF
# Types whose entries get "every game type"; the rest (observers, sounds,
# projectiles) are left as they were, 0 in most of Bungie's netgame maps.
NETGAME_MARKED_TYPES = (
    MarkerType.SCENERY,
    MarkerType.UNIT,
    MarkerType.MODEL,
    MarkerType.ANIMATION,
)
# The netgame objects belong to one game type each. The masks are Bungie's own:
# 0xC000 plus the type's bit, as Bungie's maps and Magma's ports mark them
# (Myth II's ids for these are neb1.., nef1.., nest, nelf, netf, neko; TFL's are
# below). TFL's rugby ball and goal have no Myth II game type, so appear in none.
NETGAME_OBJECT_MASKS = {
    b"neto": 0xC002,  # steal the bacon ball
    b"nefl": 0xC004,  # last man flag
    b"neb1": 0xC008, b"neb2": 0xC008, b"neb3": 0xC008, b"neb4": 0xC008, b"neb5": 0xC008,  # scavenger hunt balls
    b"nef1": 0xC010, b"nef2": 0xC010, b"nef3": 0xC010, b"nef4": 0xC010, b"nef5": 0xC010,  # flag rally flags
    b"nect": 0xC020,  # capture the flag flag
    b"nebo": 0xC040,  # balls on parade ball
    b"nedf": 0xC080,  # territories flag
    b"necb": 0xC100,  # captures ball
    b"nelm": 0xC200,  # king of the hill flag
    b"nerb": 0,  # rugby ball
    b"nerg": 0,  # rugby goal flag
}


# Myth II already has every netgame object but the rugby ones, and its engine
# recognises a flag or ball by its own tag. TFL's copies are not recognised:
# bundled, `nef1` overrides Myth II's with a body that lacks the netgame marking
# (a flag word that is 4 in Myth II's and 0 in the converted one), and four have
# ids Myth II does not know at all (Keep, Q7). So the converter leaves them out
# and points maps at Myth II's own, under the ids it uses.
NETGAME_OBJECT_IDS = {
    b"neto": b"nest",  # steal the bacon ball
    b"nefl": b"nelf",  # last man flag
    b"nedf": b"netf",  # territories flag
    b"nelm": b"neko",  # king of the hill flag
}
MYTH_II_NETGAME_SCENERY = frozenset(NETGAME_OBJECT_MASKS) - {b"nerb", b"nerg"}


def mark_netgame_types(palette_buffer, entry_count):
    """Set each palette entry's netgame types, which TFL leaves empty.

    ``palette_buffer`` is a TFL palette (its tag ids still TFL's). Scenery,
    units, models and animations appear in every game type, except the netgame
    objects (flags and balls), which appear only in theirs and are pointed at
    Myth II's own (`NETGAME_OBJECT_IDS`). Returns the new buffer, the same size.
    """
    out = bytearray(palette_buffer)
    for i in range(entry_count):
        offset = i * MARKER_PALETTE_ENTRY_SIZE
        entry = MarkerPaletteEntry.unpack(palette_buffer, offset)
        try:
            marker_type = MarkerType(entry.type)
        except ValueError:
            continue
        if marker_type not in NETGAME_MARKED_TYPES:
            continue
        mask, tag = NETGAME_ALL_TYPES, entry.marker_tag
        if marker_type == MarkerType.SCENERY:
            mask = NETGAME_OBJECT_MASKS.get(tag, mask)
            tag = NETGAME_OBJECT_IDS.get(tag, tag)
        out[offset:offset + MARKER_PALETTE_ENTRY_SIZE] = entry.replace(netgame_flags=mask, marker_tag=tag).encode()
    return bytes(out)


def remap_marker_palette(palette_buffer, entry_count, id_map):
    """Rewrite each marker-palette entry's tag reference through ``id_map``.

    ``palette_buffer`` is exactly ``marker_palette_size`` bytes, starting at a
    mesh's ``marker_palette_offset``. The entry structure itself needs no
    conversion (see module note); only the 4-byte tag id each entry carries
    may need remapping, and only entries whose type resolves to a known tag
    type via `MARKER_TYPE_TO_TAG` carry one at all.

    Returns ``(new_buffer, warnings)``.
    """
    out = bytearray(palette_buffer)
    warnings = []

    for i in range(entry_count):
        offset = i * MARKER_PALETTE_ENTRY_SIZE
        entry = MarkerPaletteEntry.unpack(palette_buffer, offset)

        try:
            marker_type = MarkerType(entry.type)
        except ValueError:
            continue
        tag_type = MARKER_TYPE_TO_TAG.get(marker_type)
        if tag_type is None:
            continue
        if codec.all_on(entry.marker_tag) or codec.all_off(entry.marker_tag):
            continue

        mapped = id_map.map_id(tag_type, entry.marker_tag) if id_map else entry.marker_tag
        if mapped != entry.marker_tag:
            out[offset + 4 : offset + 8] = mapped

    return bytes(out), warnings
