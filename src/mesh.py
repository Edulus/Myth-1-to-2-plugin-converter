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
