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

**What this does not convert.** Only the 1024-byte header. Everything after it —
terrain, marker palette, markers, map actions, media coverage, LOD data — is
copied verbatim. Map actions in particular are known to differ: mythextract's
``mesh_tag.ParamType.PROJECTILE_OR_WORLD_POINT_2D`` documents one parameter type
code meaning ``WORLD_POINT_2D`` in TFL and ``PROJECTILE`` in Myth II. Markers
carry tag IDs that an ID map would need to reach. Both are reported, not hidden.
"""

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
    "transition_point": 62259,  # 32/40 (varies with terrain; this is the mode)
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

_TFL_FIELDS = set(mesh_module.TFLMeshHeader.names)
_SB_FIELDS = set(mesh_module.SBMeshHeader.names)
SHARED_FIELDS = tuple(f for f in mesh_module.SBMeshHeader.names if f in _TFL_FIELDS)


def convert(body, context=None):
    """Convert a TFL mesh body. Returns ``(new_body, warnings)``.

    ``context`` may carry ``use_vtfl`` to set the mesh's vTFL compatibility flag
    (see `_convert_flags`).
    """
    warnings = []
    use_vtfl = bool(getattr(context, "use_vtfl", False)) if context else False

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
        if field not in SB_ONLY_DEFAULTS:
            warnings.append(
                f"decisions file overrides '{field}', which is not a synthesised "
                f"mesh field; ignored"
            )
            continue
        values[field] = value

    values["flags"], flag_warnings = _convert_flags(tfl.flags, use_vtfl)
    warnings.extend(flag_warnings)

    for field, width in (
        ("cutscene_file_pregame", 64),
        ("cutscene_file_success", 64),
        ("cutscene_file_failure", 64),
        ("plugin_name", 32),
    ):
        values[field] = values[field].ljust(width, b"\0")

    header = mesh_module.SBMeshHeader.build(**values)
    converted = header.encode()
    assert len(converted) == mesh_module.MESH_HEADER_SIZE

    trailing = body[mesh_module.MESH_HEADER_SIZE :]
    if tfl.map_action_count:
        warnings.append(
            f"{tfl.map_action_count} map actions copied unconverted -- parameter "
            f"type codes differ between the games (mythextract "
            f"ParamType.PROJECTILE_OR_WORLD_POINT_2D)"
        )
    if tfl.marker_count:
        warnings.append(
            f"{tfl.marker_count} markers copied unconverted -- they carry tag IDs "
            f"that ID remapping does not yet reach"
        )

    return converted + trailing, warnings


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
