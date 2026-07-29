"""Mesh (`mesh`) tag headers for TFL and Myth II.

A mesh is a playable map. Its 1024-byte header sits at the start of the tag body
and points at everything else the map needs -- terrain, markers, map actions,
and the string lists the game shows in its menus.

Ported from mythextract ``scripts/mesh_tag.py`` @ c747909 (``MeshHeaderFmt`` and
``MeshHeaderFmtTFL``). Both are 1024 bytes, which makes the difference between
them easy to miss: **the same offset means different things in the two games.**
The divergence starts 76 bytes in --

    offset 76   TFL: render_variables_tag     Myth II: connector_tag

-- and the two layouts never re-converge. TFL has `teams_*` and `annotation_*`
blocks where Myth II has team/lighting colour fields, and Myth II adds a long
run of fields (reverb, connectors, cutscene filenames, fog, narration) that TFL
has no room for, ending in 730 bytes of padding on the TFL side.

Offsets stored *inside* the body are relative to the end of this header
(mythextract ``get_offset``: ``TAG_HEADER_SIZE + MESH_HEADER_SIZE + offset``),
which is why moving a mesh tag between containers does not require rewriting it.
"""

import enum
import struct

from . import codec, formats

MESH_HEADER_SIZE = 1024


class MeshFlags(enum.IntFlag):
    """mythextract scripts/mesh_tag.py:125-155 (``MeshFlags``).

    The low bits are the netgame types the map supports; the useful one here is
    ``SINGLE_PLAYER_MAP``.
    """

    BODY_COUNT = 1 << 0
    STEAL_THE_BACON = 1 << 1
    LAST_MAN_ON_THE_HILL = 1 << 2
    SCAVENGER_HUNT = 1 << 3
    FLAG_RALLY = 1 << 4
    CAPTURE_THE_FLAG = 1 << 5
    BALLS_ON_PARADE = 1 << 6
    TERRITORIES = 1 << 7
    CAPTURES = 1 << 8
    KING_OF_THE_HILL = 1 << 9
    STAMPEDE = 1 << 10
    ASSASSIN = 1 << 11
    HUNTING = 1 << 12
    CUSTOM = 1 << 13
    KING_OF_THE_HILL_TFL = 1 << 14
    KING_OF_THE_MAP = 1 << 15
    SINGLE_PLAYER_MAP = 1 << 16
    SUPPORTS_UNIT_TRADING = 1 << 17
    SUPPORTS_VETERANS = 1 << 18
    HAS_LIMITED_TERRAIN_VISIBILITY = 1 << 19
    IS_COMPLETE = 1 << 20
    CAN_BE_USED_BY_DEMO = 1 << 21
    LEAVES_OVERHEAD_MAP_CLOSED = 1 << 22
    IS_TRAINING_MAP = 1 << 23
    CAN_CATCH_FIRE = 1 << 24
    HAS_CEILING = 1 << 25
    HAS_TERRAIN_FOLLOWING_CAMERA = 1 << 26
    OVERHEAD_MAP_DOESNT_SCROLL = 1 << 27
    MODELS_DONT_LIMIT_RENDERING = 1 << 28
    USES_ANTICLUMP = 1 << 29
    USES_VTFL = 1 << 30
    REQUIRES_PLUGIN = 1 << 31


NETGAME_FLAGS = (
    MeshFlags.BODY_COUNT
    | MeshFlags.STEAL_THE_BACON
    | MeshFlags.LAST_MAN_ON_THE_HILL
    | MeshFlags.SCAVENGER_HUNT
    | MeshFlags.FLAG_RALLY
    | MeshFlags.CAPTURE_THE_FLAG
    | MeshFlags.BALLS_ON_PARADE
    | MeshFlags.TERRITORIES
    | MeshFlags.CAPTURES
    | MeshFlags.KING_OF_THE_HILL
    | MeshFlags.STAMPEDE
    | MeshFlags.ASSASSIN
    | MeshFlags.HUNTING
    | MeshFlags.CUSTOM
    | MeshFlags.KING_OF_THE_HILL_TFL
    | MeshFlags.KING_OF_THE_MAP
)

# --- TFL mesh header, 1024 bytes ---------------------------------------------
# mythextract scripts/mesh_tag.py:277-353 (``MeshHeaderFmtTFL``).
TFLMeshHeader = codec.Struct(
    "TFLMeshHeader",
    [
        ("4s", "landscape_collection_tag"),
        ("4s", "media_tag"),
        ("H", "submesh_width"),
        ("H", "submesh_height"),
        ("L", "mesh_offset"),
        ("L", "mesh_size"),
        ("4x", None),  # runtime: mesh_ptr
        ("L", "data_offset"),
        ("L", "data_size"),
        ("4x", None),  # runtime: data_ptr
        ("L", "marker_palette_entries"),
        ("L", "marker_palette_offset"),
        ("L", "marker_palette_size"),
        ("4x", None),  # runtime: marker_palette_ptr
        ("L", "marker_count"),
        ("L", "markers_offset"),
        ("L", "markers_size"),
        ("4x", None),  # runtime: markers_ptr
        ("4s", "mesh_lighting_tag"),
        ("4s", "render_variables_tag"),  # <- Myth II has connector_tag here
        ("L", "flags"),
        ("4s", "particle_system_tag"),
        ("L", "team_count"),
        ("L", "teams_offset"),  # TFL only
        ("L", "teams_size"),  # TFL only
        ("4x", None),  # runtime: teams_ptr
        ("L", "annotation_count"),  # TFL only
        ("L", "annotation_offset"),  # TFL only
        ("L", "annotation_size"),  # TFL only
        ("4x", None),  # runtime: annotations_ptr
        ("8s", "edge_of_mesh_buffer_zones"),
        ("4s", "global_ambient_sound_tag"),
        ("L", "map_action_count"),
        ("L", "map_actions_offset"),
        ("L", "map_action_buffer_size"),
        ("4s", "map_description_string_list_tag"),
        ("4s", "postgame_collection_tag"),
        ("4s", "pregame_collection_tag"),
        ("4s", "overhead_map_collection_tag"),
        ("4s", "next_mesh"),
        ("4s", "next_mesh_alternate"),
        ("4s", "cutscene_tag_pregame"),
        ("4s", "cutscene_tag_success"),
        ("4s", "cutscene_tag_failure"),
        ("4s", "pregame_storyline_tag"),
        ("4s", "storyline_string_tags_2"),
        ("4s", "storyline_string_tags_3"),
        ("4s", "storyline_string_tags_4"),
        ("L", "media_coverage_region_offset"),
        ("L", "media_coverage_region_size"),
        ("4x", None),  # runtime: media_coverage_region_ptr
        ("L", "mesh_LOD_data_offset"),
        ("L", "mesh_LOD_data_size"),
        ("4x", None),  # runtime: mesh_LOD_data_ptr
        ("8s", "global_tint_color"),
        ("h", "global_tint_fraction"),
        ("H", "pad"),
        ("4s", "wind_tag"),
        ("4s", "screen_collection_tags_1"),
        ("4s", "screen_collection_tags_2"),
        ("4s", "screen_collection_tags_3"),
        ("8s", "blood_color"),
        ("4s", "picture_caption_string_list_tag"),
        ("4s", "narration_sound_tag"),
        ("4s", "win_ambient_sound_tag"),
        ("4s", "loss_ambient_sound_tag"),
        ("730x", None),  # unused -- Myth II fills this region with real fields
        ("2x", None),  # runtime: map_description_string_index
        ("2x", None),  # runtime: overhead_map_collection_index
        ("2x", None),  # runtime: landscape_collection_index
        ("2x", None),  # runtime: global_ambient_sound_index
        ("2x", None),  # runtime: media_type
        ("16x", None),  # editor_data
    ],
)

# --- Myth II mesh header, 1024 bytes -----------------------------------------
# mythextract scripts/mesh_tag.py:165-276 (``MeshHeaderFmt``).
SBMeshHeader = codec.Struct(
    "SBMeshHeader",
    [
        ("4s", "landscape_collection_tag"),
        ("4s", "media_tag"),
        ("H", "submesh_width"),
        ("H", "submesh_height"),
        ("L", "mesh_offset"),
        ("L", "mesh_size"),
        ("4x", None),  # runtime: mesh_ptr
        ("L", "data_offset"),
        ("L", "data_size"),
        ("4x", None),  # runtime: data_ptr
        ("L", "marker_palette_entries"),
        ("L", "marker_palette_offset"),
        ("L", "marker_palette_size"),
        ("4x", None),  # runtime: marker_palette_ptr
        ("L", "marker_count"),
        ("L", "markers_offset"),
        ("L", "markers_size"),
        ("4x", None),  # runtime: markers_ptr
        ("4s", "mesh_lighting_tag"),
        ("4s", "connector_tag"),  # <- TFL has render_variables_tag here
        ("L", "flags"),
        ("4s", "particle_system_tag"),
        ("L", "team_count"),
        ("h", "dark_fraction"),
        ("h", "light_fraction"),
        ("8s", "dark_color"),
        ("8s", "light_color"),
        ("l", "transition_point"),
        ("h", "ceiling_height"),
        ("B", "min_vtfl_version"),
        ("B", "max_vtfl_version"),
        ("8s", "edge_of_mesh_buffer_zones"),
        ("4s", "global_ambient_sound_tag"),
        ("L", "map_action_count"),
        ("L", "map_actions_offset"),
        ("L", "map_action_buffer_size"),
        ("4s", "map_description_string_list_tag"),
        ("4s", "postgame_collection_tag"),
        ("4s", "pregame_collection_tag"),
        ("4s", "overhead_map_collection_tag"),
        ("4s", "next_mesh"),
        ("4s", "next_mesh_alternate"),
        ("4s", "cutscene_tag_pregame"),
        ("4s", "cutscene_tag_success"),
        ("4s", "cutscene_tag_failure"),
        ("4s", "pregame_storyline_tag"),
        ("4s", "storyline_string_tags_2"),
        ("4s", "storyline_string_tags_3"),
        ("4s", "storyline_string_tags_4"),
        ("L", "media_coverage_region_offset"),
        ("L", "media_coverage_region_size"),
        ("4x", None),  # runtime: media_coverage_region_ptr
        ("L", "mesh_LOD_data_offset"),
        ("L", "mesh_LOD_data_size"),
        ("4x", None),  # runtime: mesh_LOD_data_ptr
        ("8s", "global_tint_color"),
        ("h", "global_tint_fraction"),
        ("H", "pad"),
        ("4s", "wind_tag"),
        ("4s", "screen_collection_tags_1"),
        ("4s", "screen_collection_tags_2"),
        ("4s", "screen_collection_tags_3"),
        ("8s", "blood_color"),
        ("4s", "picture_caption_string_list_tag"),
        ("4s", "narration_sound_tag"),
        ("4s", "win_ambient_sound_tag"),
        ("4s", "loss_ambient_sound_tag"),
        # Everything from here down is Myth II only; TFL has padding.
        ("L", "reverb_environment"),
        ("f", "reverb_volume"),
        ("f", "reverb_decay_time"),
        ("f", "reverb_damping"),
        ("L", "connector_count"),
        ("l", "connectors_offset"),
        ("L", "connectors_size"),
        ("4x", None),  # runtime: connectors_ptr
        ("64s", "cutscene_file_pregame"),
        ("64s", "cutscene_file_success"),
        ("64s", "cutscene_file_failure"),
        ("4s", "hints_string_list_tag"),
        ("8s", "fog_color"),
        ("f", "fog_density"),
        ("4s", "difficulty_level_override_string_list_tag"),
        ("4s", "team_names_override_string_list_tag"),
        ("32s", "plugin_name"),
        ("L", "extra_flags"),
        ("4s", "win_narration_collection_tag"),
        ("4s", "loss_narration_collection_tag"),
        ("4s", "win_narration_storyline_tag_tag"),
        ("4s", "loss_narration_storyline_tag"),
        ("4s", "win_narration_caption_string_list_tag"),
        ("4s", "loss_narration_caption_string_list_tag"),
        ("4s", "win_narration_sound_tag"),
        ("4s", "loss_narration_sound_tag"),
        ("f", "minimum_zoom_factor"),
        ("406x", None),  # unused
        ("2x", None),  # runtime: connector_type
        ("2x", None),  # runtime: map_description_string_index
        ("2x", None),  # runtime: overhead_map_collection_index
        ("2x", None),  # runtime: landscape_collection_index
        ("2x", None),  # runtime: global_ambient_sound_index
        ("2x", None),  # runtime: media_type
        ("2x", None),  # runtime: hints_string_list_index
        ("4s", "editor_data_cookie"),
        ("L", "editor_data_size"),
        ("L", "editor_data_offset"),
        ("4x", None),  # editor_data_unused
    ],
)

MESH_HEADER_BY_VERSION = {formats.TFL: TFLMeshHeader, formats.SB: SBMeshHeader}

assert TFLMeshHeader.size == MESH_HEADER_SIZE, TFLMeshHeader.size
assert SBMeshHeader.size == MESH_HEADER_SIZE, SBMeshHeader.size


def parse_header(body, game_version):
    """Parse the mesh header from the *body* of a mesh tag.

    The body already excludes the 64-byte tag header, so the mesh header starts
    at offset 0 here -- unlike mythextract, which parses from whole tag files and
    so offsets everything by ``TAG_HEADER_SIZE``.
    """
    if len(body) < MESH_HEADER_SIZE:
        raise ValueError(
            f"mesh body is {len(body)} bytes, need at least {MESH_HEADER_SIZE}"
        )
    return MESH_HEADER_BY_VERSION[game_version].unpack(body)


def is_single_player(header):
    """mythextract scripts/mesh_tag.py:745-746."""
    return bool(header.flags & MeshFlags.SINGLE_PLAYER_MAP)


def netgame_types(header):
    """The multiplayer game types this mesh supports."""
    return [flag for flag in MeshFlags if flag & NETGAME_FLAGS and header.flags & flag]


def body_offset(offset):
    """Resolve an offset stored inside a mesh header to a position in the body.

    Offsets are relative to the end of the mesh header (mythextract
    ``get_offset``, which adds ``TAG_HEADER_SIZE`` on top because it works with
    whole tag files; we work with bodies).
    """
    return MESH_HEADER_SIZE + offset


def referenced_tags(header, game_version):
    """Every ``(tag_type, tag_id)`` this mesh header points at directly.

    Only the fixed header fields -- markers and map actions carry more IDs in
    variable-length blocks, which the mesh *body* converter will need to walk.
    Field-to-type mapping follows mythextract ``scripts/tag2local.py:157-176``.
    Unset IDs (all 0xFF or all 0x00) are skipped.
    """
    fields = [
        (b"stli", "map_description_string_list_tag"),
        (b"text", "pregame_storyline_tag"),
        (b"stli", "picture_caption_string_list_tag"),
        (b".256", "landscape_collection_tag"),
        (b".256", "overhead_map_collection_tag"),
        (b".256", "postgame_collection_tag"),
        (b".256", "pregame_collection_tag"),
        (b"wind", "wind_tag"),
        (b"meli", "mesh_lighting_tag"),
        (b"soun", "narration_sound_tag"),
        (b"amso", "global_ambient_sound_tag"),
        (b"part", "particle_system_tag"),
        (b"medi", "media_tag"),
    ]
    if game_version == formats.SB:
        fields += [
            (b"conn", "connector_tag"),
            (b"stli", "hints_string_list_tag"),
            (b"stli", "difficulty_level_override_string_list_tag"),
            (b"stli", "team_names_override_string_list_tag"),
        ]

    found = []
    for tag_type, field in fields:
        value = getattr(header, field, None)
        if value and not codec.all_on(value) and not codec.all_off(value):
            found.append((tag_type, value, field))
    return found


# --- Markers, marker palette, map actions -------------------------------------
#
# Everything below is *shared* between TFL and Myth II -- one struct each, no
# TFL/SB variant -- which is the opposite of the header above. Verified three
# ways: mythextract's own struct declarations (``MarkerHeadFmt``,
# ``MarkerPaletteEntryFmt``, ``ActionHeadFmt``, all read without a
# game-version branch), and two independent community tools that ported real
# TFL levels to Myth II by copying these three structures byte-for-byte --
# "Iron's Mesh Converter" (Mac and Windows builds, both with source,
# distributed with permission at
# tain.totalcodex.net/items/show/mesh-converter-mac-and-windows-w-source-code).
# See NOTES.md section 14.
#
# What is *not* shared: the map-action **parameter type codes**. TFL's
# ``ParamType`` numbering is missing the slot Myth II uses for a standalone
# ``PROJECTILE`` type, so every TFL code from 12 up means something different
# from the same numeric code in Myth II. That mismatch is a plausible direct
# cause of the ``EXCEPTION_ACCESS_VIOLATION`` inside the engine's
# ``byte_swap_data`` seen when loading an otherwise-converted mesh: a
# misread parameter type means a misread element count, which desyncs every
# subsequent read in the buffer. ``resolve_param_type`` and
# ``param_data_length`` exist to fix exactly that, ported from mythextract's
# own (read-side) handling of it in ``parse_map_actions``
# (scripts/mesh_tag.py:1285-1296) and cross-checked against both community
# tools' independently-arrived-at ``type++`` fixups for the same value range.

MARKER_HEAD_SIZE = 64
MARKER_PALETTE_ENTRY_SIZE = 32
MAP_ACTION_HEAD_SIZE = 64

# mythextract scripts/mesh_tag.py:658-673 (``MarkerHeadFmt``). Decoders for
# position/angle scale factors are dropped -- this project's codec does not
# do value decoding (see codec.py) -- since a structural pass-through never
# needs the scaled float value, only the raw bytes.
MarkerHead = codec.Struct(
    "MarkerHead",
    [
        ("L", "flags"),
        ("H", "type"),  # MarkerType
        ("H", "palette_index"),
        ("H", "id"),
        ("H", "min_difficulty"),
        ("L", "pos_x"),
        ("L", "pos_y"),
        ("l", "pos_z"),
        ("8x", None),
        ("H", "yaw"),
        ("2x", None),
        ("2x", None),
        ("20x", None),
        ("6x", None),
    ],
)

# mythextract scripts/mesh_tag.py:677-686 (``MarkerPaletteEntryFmt``).
MarkerPaletteEntry = codec.Struct(
    "MarkerPaletteEntry",
    [
        ("H", "type"),  # MarkerType
        ("H", "flags"),
        ("4s", "marker_tag"),  # the tag reference this palette slot resolves to
        ("h", "team_index"),
        ("2x", None),
        ("L", "netgame_flags"),
        ("10x", None),
        ("6x", None),
    ],
)

# mythextract scripts/mesh_tag.py:111-122 (``ActionHeadFmt``).
MapActionHead = codec.Struct(
    "MapActionHead",
    [
        ("H", "id"),
        ("H", "expiration_mode"),
        ("4s", "type"),  # the action kind, e.g. b'soun' -- not a tag reference
        ("L", "flags"),
        ("L", "trigger_time_lower_bound"),
        ("L", "trigger_time_delta"),
        ("H", "num_params"),
        ("H", "size"),
        ("L", "offset"),
        ("H", "indent"),
        ("34x", None),
    ],
)

assert MarkerHead.size == MARKER_HEAD_SIZE, MarkerHead.size
assert MarkerPaletteEntry.size == MARKER_PALETTE_ENTRY_SIZE, MarkerPaletteEntry.size
assert MapActionHead.size == MAP_ACTION_HEAD_SIZE, MapActionHead.size


class MarkerType(enum.IntEnum):
    """mythextract scripts/mesh_tag.py:402-414. 12 valid values (0-11); a
    stored type of 12 or more marks the end of real data in at least one
    community tool's experience with loose TFL mesh files (Iron's Mesh
    Converter, ``load_tfl``) -- consistent with this being one past the
    highest valid member, ``ANIMATION``."""

    OBSERVER = 0
    SCENERY = 1
    UNKNOWN_1 = 2
    UNIT = 3
    UNKNOWN_2 = 4
    AMBIENT_SOUND = 5
    MODEL = 6
    UNKNOWN_3 = 7
    UNKNOWN_4 = 8
    PROJECTILE = 9
    LOCAL_PROJECTILE_GROUP = 10
    ANIMATION = 11


# mythextract scripts/mesh_tag.py:415-423 (``Marker2Tag``). Types absent here
# (OBSERVER, the UNKNOWN_* slots) have no palette tag to look up.
MARKER_TYPE_TO_TAG = {
    MarkerType.SCENERY: b"scen",
    MarkerType.UNIT: b"unit",
    MarkerType.AMBIENT_SOUND: b"amso",
    MarkerType.MODEL: b"mode",
    MarkerType.PROJECTILE: b"proj",
    MarkerType.LOCAL_PROJECTILE_GROUP: b"lpgr",
    MarkerType.ANIMATION: b"anim",
}


class ParamType(enum.IntEnum):
    """mythextract scripts/mesh_tag.py:688-709 (``ParamType``). This is Myth
    II's numbering; a raw TFL value needs `resolve_param_type` first."""

    FLAG = 0
    STRING = 1
    MONSTER_IDENTIFIER = 2
    ACTION_IDENTIFIER = 3
    ANGLE = 4
    INTEGER = 5
    WORLD_DISTANCE = 6
    FIELD_NAME = 7
    FIXED = 8
    PROJECTILE = 9
    STRING_LIST = 10
    SOUND = 11
    PROJECTILE_OR_WORLD_POINT_2D = 12  # TFL = WORLD_POINT_2D / SB = PROJECTILE
    WORLD_POINT_2D = 13
    WORLD_RECTANGLE_2D = 14
    OBJECT_IDENTIFIER = 15
    MODEL_IDENTIFIER = 16
    SOUND_SOURCE_IDENTIFIER = 17
    WORLD_POINT_3D = 18
    LOCAL_PROJECTILE_GROUP_IDENTIFIER = 19
    MODEL_ANIMATION_IDENTIFIER = 20


# Parameter types that hold a tag reference as their element data, and the
# marker/tag type that reference resolves against. mythextract
# scripts/mesh_tag.py:424-435 (``param_id_marker``); STRING_LIST and
# ACTION_IDENTIFIER are deliberately excluded -- a string-list reference is a
# stli tag id but is looked up directly, and an action identifier refers to
# another map action in the same mesh, never a tag.
PARAM_TYPE_TAG = {
    ParamType.MONSTER_IDENTIFIER: b"unit",
    ParamType.SOUND_SOURCE_IDENTIFIER: b"amso",
    ParamType.OBJECT_IDENTIFIER: b"proj",
    ParamType.MODEL_IDENTIFIER: b"mode",
    ParamType.LOCAL_PROJECTILE_GROUP_IDENTIFIER: b"lpgr",
    ParamType.MODEL_ANIMATION_IDENTIFIER: b"anim",
    ParamType.PROJECTILE: b"proj",
    ParamType.SOUND: b"soun",
}


def resolve_param_type(raw_type, game_version):
    """The true semantic `ParamType` for a stored raw type code.

    TFL and Myth II share one enum, but TFL's on-disk numbering omits the slot
    Myth II uses for a standalone ``PROJECTILE`` type, so every TFL code from
    12 up means something different from the same numeric code in Myth II.
    Ported from mythextract's ``parse_map_actions``
    (scripts/mesh_tag.py:1285-1296), which already gets this right for
    *reading* a TFL mesh; this is the same table.

    Raises ``ValueError`` if ``raw_type`` is not a known code at all (not just
    a TFL/SB ambiguity) -- that is data we do not understand, not data we can
    silently reinterpret.
    """
    canonical = ParamType(raw_type)
    if game_version != formats.TFL:
        return canonical
    if canonical == ParamType.PROJECTILE_OR_WORLD_POINT_2D:
        return ParamType.WORLD_POINT_2D
    if canonical == ParamType.WORLD_RECTANGLE_2D:
        return ParamType.OBJECT_IDENTIFIER
    if canonical == ParamType.MODEL_IDENTIFIER:
        return ParamType.SOUND_SOURCE_IDENTIFIER
    if canonical == ParamType.WORLD_POINT_3D:
        return ParamType.LOCAL_PROJECTILE_GROUP_IDENTIFIER
    return canonical


def _align(boundary, value):
    """mythextract scripts/mesh_tag.py:722-723 (``align``)."""
    return (value + boundary - 1) & ~(boundary - 1)


def param_data_length(param_type, count):
    """Bytes of parameter data following a param's 8-byte header (type, count,
    name), given its true semantic type and stored element count.

    Ported from mythextract's sizing rules in ``parse_map_actions``
    (scripts/mesh_tag.py:1298-1335). Deliberately returns only a byte count,
    not decoded values: converting a param never needs to touch its data,
    only (sometimes) its type code, so there is nothing to gain from decoding
    the numbers only to re-encode them unchanged. Cross-checked against the
    three worked examples in docs/ActionParamElementFormat.txt.
    """
    if param_type == ParamType.STRING:
        return _align(4, count)
    if param_type in (ParamType.SOUND, ParamType.FIELD_NAME, ParamType.PROJECTILE):
        return count * 4
    if param_type == ParamType.WORLD_POINT_2D:
        return count * 2 * 4
    if param_type == ParamType.WORLD_POINT_3D:
        return count * 3 * 4
    if param_type in (ParamType.FIXED, ParamType.INTEGER, ParamType.WORLD_DISTANCE):
        return count * 4
    if param_type == ParamType.FLAG:
        return _align(4, count)
    return _align(2, count) * 2  # ANGLE and the default 2-byte-element types


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
