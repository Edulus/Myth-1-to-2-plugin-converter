"""Convert a ``mesh`` tag body from TFL to Myth II.

Both mesh headers are exactly 1024 bytes, so a TFL mesh body *looks* valid to
Myth II and is silently misread from offset 76 onward. Converting means
rebuilding the header field by field, by name rather than by position.

Three groups of fields:

**Shared** — same name in both layouts, copied across. This includes every
offset/size pair pointing into the rest of the body (`mesh_offset`,
`markers_offset`, `map_actions_offset`, ...). Those stay valid unchanged because
they are relative to the end of the header and both headers are the same size.

**TFL-only** — dropped, and reported:

    render_variables_tag   Myth II has connector_tag at this offset instead
    teams_offset/size      TFL stores team data as a block in the body
    annotation_*           TFL-only annotations block

The blocks those point at are left in the body. They become unreachable rather
than corrupt, costing space but nothing else.

**Myth II-only** — nothing in TFL to translate from, so they are synthesised.
The values come from measuring `Magma - The Fallen Lords v1.9`, the faithful
community TFL→Myth II port, across its 40 meshes: `ceiling_height` is 2048 in
all 40, the three reverb values are identical in all 40, and the lighting
fractions and colours agree in 35-39 of 40. Using a real port's values beats
inventing plausible ones.

**What else this converts, and what it still does not.** Markers themselves and
marker-palette entries need no structural change at all -- both are the same
size and layout in TFL and Myth II (NOTES.md section 14) -- but a palette
entry's tag reference is remapped through the ID map, same as any other tag
reference. Map-action parameter **type codes** are corrected: TFL's numbering
is missing a slot Myth II uses for a standalone ``PROJECTILE`` type, so every
TFL code from 12 up means something different in Myth II
(`src.mesh.resolve_param_type`); left uncorrected, that mismatch cascades into
every later parameter in the buffer and is a plausible cause of the
``EXCEPTION_ACCESS_VIOLATION`` seen when loading an otherwise-converted mesh.

**What this still does not do:** tag references *inside* map-action parameter
data (a `SOUND` or `PROJECTILE`-typed parameter's element bytes) are not yet
remapped through the ID map, only the palette's. Terrain is upsampled by
copying each cell into a 2x2 block, media coverage is copied verbatim, and mesh
LOD data is zero-filled at the new size.
"""

import struct

from ... import codec, formats, mesh as mesh_module

HANDLES = (b"mesh",)

# Fields Myth II has and TFL does not. Values measured across the 40 meshes of
# Magma - The Fallen Lords v1.9; the count is how many of the 40 agreed.
SB_ONLY_DEFAULTS = {
    "connector_tag": b"\xff\xff\xff\xff",  # 40/40 unset
    "dark_fraction": 229,  # 39/40
    "light_fraction": 25,  # 38/40
    "dark_color": bytes.fromhex("000000000f5c0000"),  # 35/40
    "light_color": bytes.fromhex("ffffa14700000000"),  # 37/40
    # 32/40. Not terrain-derived, despite the variation: the Fear manual
    # defines it as "the zero point -- the illumination level at which there is
    # no lightening or darkening on the mesh", i.e. a global brightness control
    # (lower = brighter map, higher = darker). A per-map artistic choice, which
    # is exactly why it is worth a human's attention rather than a default.
    "transition_point": 62259,
    "ceiling_height": 2048,  # 40/40
    "min_vtfl_version": 0,  # 40/40
    "max_vtfl_version": 0,  # 40/40
    "reverb_environment": 0,  # 38/40
    "reverb_volume": 0.5,  # 40/40
    "reverb_decay_time": 1.4930000305175781,  # 40/40
    "reverb_damping": 0.5,  # 40/40
    "connector_count": 0,  # 40/40
    "connectors_offset": 0,  # size is 0, so the offset is unused
    "connectors_size": 0,  # 40/40
    "cutscene_file_pregame": b"",
    "cutscene_file_success": b"",
    "cutscene_file_failure": b"",
    "hints_string_list_tag": b"\xff\xff\xff\xff",  # 39/40 unset
    "fog_color": bytes(8),  # 38/40 zero
    "fog_density": 0.0,  # 40/40
    "difficulty_level_override_string_list_tag": b"\xff\xff\xff\xff",
    "team_names_override_string_list_tag": b"\xff\xff\xff\xff",
    "plugin_name": b"",  # 40/40 empty
    "extra_flags": 0,  # 40/40
    "win_narration_collection_tag": b"\xff\xff\xff\xff",
    "loss_narration_collection_tag": b"\xff\xff\xff\xff",
    "win_narration_storyline_tag_tag": b"\xff\xff\xff\xff",
    "loss_narration_storyline_tag": b"\xff\xff\xff\xff",
    "win_narration_caption_string_list_tag": b"\xff\xff\xff\xff",
    "loss_narration_caption_string_list_tag": b"\xff\xff\xff\xff",
    "win_narration_sound_tag": b"\xff\xff\xff\xff",
    "loss_narration_sound_tag": b"\xff\xff\xff\xff",
    "minimum_zoom_factor": 0.0,  # 40/40
    "editor_data_cookie": bytes(4),  # 40/40
    "editor_data_size": 0,  # 40/40
    "editor_data_offset": 0,  # 40/40
}

# TFL fields with no Myth II destination. Reported when they carry something.
TFL_ONLY_FIELDS = (
    "render_variables_tag",
    "teams_offset",
    "teams_size",
    "annotation_count",
    "annotation_offset",
    "annotation_size",
)

# Synthesised values that live in the terrain cells rather than the header.
# TFL cells simply do not have these, so like SB_ONLY_DEFAULTS they have to be
# invented -- but they are written per cell by the terrain converter, not
# packed into the mesh header.
CELL_DEFAULTS = {
    # The height of the water *surface*. Constant across virtually every native
    # Myth II mesh, and absent from TFL cells entirely, so a single value is
    # applied to the whole mesh. Zero is sea level, which is where TFL maps put
    # water in the absence of anywhere else to record it.
    "media_height": 0,
}

# Everything a decisions file may override, header and cell alike.
SYNTHESISED = {**SB_ONLY_DEFAULTS, **CELL_DEFAULTS}

_TFL_FIELDS = set(mesh_module.TFLMeshHeader.names)
_SB_FIELDS = set(mesh_module.SBMeshHeader.names)
SHARED_FIELDS = tuple(f for f in mesh_module.SBMeshHeader.names if f in _TFL_FIELDS)


def convert(body, context=None):
    """Convert a TFL mesh body. Returns ``(new_body, warnings)``.

    ``context`` may carry ``use_vtfl`` to set the mesh's vTFL compatibility flag
    (see `_convert_flags`) and ``id_map`` to remap marker-palette tag
    references.
    """
    warnings = []
    use_vtfl = bool(getattr(context, "use_vtfl", False)) if context else False
    id_map = getattr(context, "id_map", None) if context else None

    if len(body) < mesh_module.MESH_HEADER_SIZE:
        return body, [
            f"mesh body is {len(body)} bytes, shorter than the {mesh_module.MESH_HEADER_SIZE}"
            f"-byte header; left unconverted"
        ]

    tfl = mesh_module.TFLMeshHeader.unpack(body)

    for field in TFL_ONLY_FIELDS:
        value = getattr(tfl, field)
        carries = value not in (0, b"", None) and not codec.all_on(
            value if isinstance(value, bytes) else b""
        )
        if isinstance(value, bytes):
            carries = not codec.all_on(value) and not codec.all_off(value)
        if carries:
            shown = value.hex() if isinstance(value, bytes) else value
            warnings.append(f"dropped TFL-only mesh field {field}={shown}")

    values = {field: getattr(tfl, field) for field in SHARED_FIELDS}
    values.update(SB_ONLY_DEFAULTS)

    # A decisions file may override any synthesised field -- these are the
    # values with no TFL source, so a human who knows the level may well know
    # better than the measured mode.
    overrides = dict(getattr(context, "mesh_defaults", None) or {}) if context else {}
    for field, value in overrides.items():
        if field not in SYNTHESISED:
            warnings.append(
                f"decisions file overrides '{field}', which is not a synthesised "
                f"mesh field; ignored"
            )
            continue
        # Cell-level values are applied by the terrain converter, not packed
        # into the header, so they must not reach SBMeshHeader.build.
        if field in SB_ONLY_DEFAULTS:
            values[field] = value

    values["flags"], flag_warnings = _convert_flags(tfl.flags, use_vtfl)
    warnings.extend(flag_warnings)

    # The header's own tag references (media, lighting, string lists...) follow
    # the ID map too -- otherwise a decisions-file mapping fixes the report but
    # not the file, and the engine still asks for the TFL id.
    if id_map is not None:
        for tag_type, tag_id, field in mesh_module.referenced_tags(tfl, formats.TFL):
            if field in values:
                values[field] = id_map.map_id(tag_type, tag_id)

    for field, width in (
        ("cutscene_file_pregame", 64),
        ("cutscene_file_success", 64),
        ("cutscene_file_failure", 64),
        ("plugin_name", 32),
    ):
        values[field] = values[field].ljust(width, b"\0")

    trailing = body[mesh_module.MESH_HEADER_SIZE :]
    blocks, block_warnings = _convert_blocks(tfl, trailing, id_map, context)
    warnings.extend(block_warnings)

    # Terrain changes size, so every block after it moves. Rather than patch
    # offsets one by one, the body is laid out afresh in a known order and the
    # header is told where everything ended up.
    data, offsets = _lay_out_body(blocks)
    values.update(offsets)
    values["data_offset"] = mesh_module.MESH_HEADER_SIZE
    values["data_size"] = len(data)

    header = mesh_module.SBMeshHeader.build(**values)
    converted = header.encode()
    assert len(converted) == mesh_module.MESH_HEADER_SIZE

    return converted + data, warnings


def _slice(trailing, offset, size):
    """A block out of the mesh body, or None if it does not fit."""
    if size <= 0:
        return b""
    end = offset + size
    if offset < 0 or end > len(trailing):
        return None
    return bytes(trailing[offset:end])


def _convert_blocks(tfl, trailing, id_map, context):
    """Convert each variable-length block of a TFL mesh body.

    Returns ``({name: bytes}, warnings)``. A block that cannot be read is
    reported and replaced with an empty one rather than aborting the mesh --
    losing scenery placement is bad, losing the level entirely is worse.
    """
    warnings = []
    blocks = {}

    # -- terrain: the one block whose size changes --------------------------
    terrain = _slice(trailing, tfl.mesh_offset, tfl.mesh_size)
    media_height = int(_override(context, "media_height", 0))
    if terrain is None:
        blocks["terrain"] = b""
        warnings.append(
            f"terrain block at {tfl.mesh_offset}+{tfl.mesh_size} lies outside the "
            f"mesh body; the level will have no ground"
        )
    else:
        try:
            blocks["terrain"] = mesh_module.upsample_terrain(
                terrain, tfl.submesh_width, tfl.submesh_height, media_height
            )
        except (ValueError, struct.error) as exc:
            blocks["terrain"] = b""
            warnings.append(f"terrain could not be converted: {exc}")

    # -- marker palette: tag references may need remapping -------------------
    palette = _slice(trailing, tfl.marker_palette_offset, tfl.marker_palette_size)
    if palette is None:
        blocks["palette"] = b""
        warnings.append("marker palette lies outside the mesh body; dropped")
    elif tfl.marker_palette_entries:
        try:
            blocks["palette"], palette_warnings = mesh_module.remap_marker_palette(
                palette, tfl.marker_palette_entries, id_map
            )
            warnings.extend(palette_warnings)
        except struct.error as exc:
            blocks["palette"] = palette
            warnings.append(f"marker palette left unremapped: {exc}")
    else:
        blocks["palette"] = palette

    # -- markers: same layout in both games, copied verbatim -----------------
    markers = _slice(trailing, tfl.markers_offset, tfl.markers_size)
    if markers is None:
        blocks["markers"] = b""
        warnings.append("markers lie outside the mesh body; dropped")
    else:
        blocks["markers"] = markers

    # -- map actions: parameter type codes need correcting -------------------
    actions = _slice(trailing, tfl.map_actions_offset, tfl.map_action_buffer_size)
    if actions is None:
        blocks["actions"] = b""
        warnings.append("map actions lie outside the mesh body; dropped")
    elif tfl.map_action_count:
        try:
            blocks["actions"], action_warnings = mesh_module.convert_tfl_map_actions(
                actions, tfl.map_action_count
            )
            warnings.extend(action_warnings)
        except (struct.error, ValueError) as exc:
            blocks["actions"] = actions
            warnings.append(f"map actions left unconverted: {exc}")
    else:
        blocks["actions"] = actions

    # -- media coverage: where the water is, copied verbatim -----------------
    # Not resolution-dependent after all: measured against Magma's faithful
    # port of Crow's Bridge (TFL `ambu`, The Fallen Levels v2 `30cb`), its
    # 6-byte records already count on Myth II's scale, and Magma's block is
    # TFL's re-traced, each value within 1. Dropping it left water uncharted.
    coverage = _slice(
        trailing, tfl.media_coverage_region_offset, tfl.media_coverage_region_size
    )
    if coverage is None:
        blocks["coverage"] = b""
        warnings.append("media coverage lies outside the mesh body; dropped")
    else:
        blocks["coverage"] = coverage

    # -- level of detail: must exist, and must match the new cell count ------
    blocks["lod"] = mesh_module.build_lod_data(tfl.submesh_width, tfl.submesh_height)

    return blocks, warnings


def _lay_out_body(blocks):
    """Concatenate the blocks and report where each landed.

    Order follows what TFL and Myth II meshes both use in practice: terrain,
    marker palette, markers, map actions, media coverage, then level-of-detail
    data.
    """
    order = ["terrain", "palette", "markers", "actions", "coverage", "lod"]
    data = bytearray()
    at = {}
    for name in order:
        at[name] = len(data)
        data += blocks[name]

    return bytes(data), {
        "mesh_offset": at["terrain"],
        "mesh_size": len(blocks["terrain"]),
        "marker_palette_offset": at["palette"],
        "marker_palette_size": len(blocks["palette"]),
        "markers_offset": at["markers"],
        "markers_size": len(blocks["markers"]),
        "map_actions_offset": at["actions"],
        "map_action_buffer_size": len(blocks["actions"]),
        "media_coverage_region_offset": at["coverage"],
        "media_coverage_region_size": len(blocks["coverage"]),
        "mesh_LOD_data_offset": at["lod"],
        "mesh_LOD_data_size": len(blocks["lod"]),
    }


def _override(context, field, default):
    """A synthesised value, honouring a decisions-file override."""
    overrides = getattr(context, "mesh_defaults", None) if context else None
    if overrides and field in overrides:
        return overrides[field]
    return default


def _convert_flags(flags, use_vtfl):
    """Carry the mesh flags across, optionally enabling vTFL compatibility.

    ``USES_VTFL`` puts Myth II into TFL gameplay emulation for this mesh. Real
    ports disagree on whether to use it: `Magma - The Fallen Lords v1.9` sets it
    on all 40 of its meshes, while `Magma - The Fallen Lords DX 1.3` (49 meshes)
    and `Magma - TFL Multipack v2.6` (60) set it on none. It is off by default
    here because it makes the plugin depend on a vTFL "Unity" tagset being
    loaded (mythextract ``loadtags.py`` PluginFlag.VTFL), and this converter's
    output already has unresolved dependencies without adding another.
    """
    warnings = []
    converted = flags

    if use_vtfl:
        converted |= mesh_module.MeshFlags.USES_VTFL
        warnings.append(
            "set USES_VTFL: the level will need a vTFL Unity tagset loaded alongside it"
        )
    elif flags & mesh_module.MeshFlags.USES_VTFL:
        warnings.append("mesh already had USES_VTFL set; left alone")

    # KING_OF_THE_HILL_TFL is a distinct bit from KING_OF_THE_HILL and Myth II
    # treats it as legacy (mythextract mesh_tag.py:519-523 rewrites between the
    # two). Flagged rather than silently rewritten -- which of the two the game
    # wants has not been measured.
    if flags & mesh_module.MeshFlags.KING_OF_THE_HILL_TFL:
        warnings.append(
            "netgame flag KING_OF_THE_HILL_TFL carried across unchanged; Myth II "
            "may expect KING_OF_THE_HILL instead"
        )

    return int(converted), warnings
