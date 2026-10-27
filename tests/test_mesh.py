"""Tests for mesh header parsing and entrypoint synthesis."""

import os
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import codec, formats, idmap, mesh, reader  # noqa: E402
from src.convert import entrypoints, plugin as convert_plugin  # noqa: E402

from . import fixtures  # noqa: E402


class TestMeshHeaderLayout(unittest.TestCase):
    def test_both_headers_are_1024_bytes(self):
        """TFL and Myth II mesh headers are the same size -- which is exactly why
        the differing field meanings are easy to miss."""
        self.assertEqual(1024, mesh.TFLMeshHeader.size)
        self.assertEqual(1024, mesh.SBMeshHeader.size)
        self.assertEqual(mesh.MESH_HEADER_SIZE, mesh.TFLMeshHeader.size)

    def test_field_offsets_match_the_fixtures(self):
        """The fixtures hardcode offsets independently; if these drift apart, one
        of the two is wrong."""
        for struct_def in (mesh.TFLMeshHeader, mesh.SBMeshHeader):
            offsets = {name: start for _, name, start, _ in struct_def._layout if name}
            self.assertEqual(fixtures.MESH_OFFSET_FLAGS, offsets["flags"])
            self.assertEqual(
                fixtures.MESH_OFFSET_MAP_DESCRIPTION_STLI,
                offsets["map_description_string_list_tag"],
            )
            self.assertEqual(
                fixtures.MESH_OFFSET_PREGAME_STORYLINE, offsets["pregame_storyline_tag"]
            )

    def test_the_layouts_diverge_where_expected(self):
        """Offset 76 is render_variables_tag in TFL and connector_tag in Myth II.
        Same size, same offset, different meaning."""
        tfl = {n for _, n, _, _ in mesh.TFLMeshHeader._layout if n}
        sb = {n for _, n, _, _ in mesh.SBMeshHeader._layout if n}
        self.assertIn("render_variables_tag", tfl)
        self.assertNotIn("render_variables_tag", sb)
        self.assertIn("connector_tag", sb)
        self.assertNotIn("connector_tag", tfl)
        # TFL-only blocks, and Myth II-only fields with nowhere to go in TFL.
        self.assertIn("teams_offset", tfl)
        self.assertNotIn("teams_offset", sb)
        self.assertIn("reverb_environment", sb)
        self.assertNotIn("reverb_environment", tfl)

    def test_parses_a_body_and_reads_flags(self):
        body = fixtures.mesh_body(
            description_tag=b"30cc", flags=fixtures.MESH_FLAG_SINGLE_PLAYER_MAP
        )
        header = mesh.parse_header(body, formats.TFL)
        self.assertEqual(b"30cc", header.map_description_string_list_tag)
        self.assertTrue(mesh.is_single_player(header))

        plain = mesh.parse_header(fixtures.mesh_body(flags=0), formats.TFL)
        self.assertFalse(mesh.is_single_player(plain))

    def test_rejects_a_truncated_body(self):
        with self.assertRaises(ValueError):
            mesh.parse_header(b"\0" * 100, formats.TFL)

    def test_referenced_tags_skips_unset_ids(self):
        body = fixtures.mesh_body(description_tag=b"30cc", storyline_tag=b"\xff" * 4)
        header = mesh.parse_header(body, formats.TFL)
        found = {(t, i) for t, i, _ in mesh.referenced_tags(header, formats.TFL)}
        self.assertIn((b"stli", b"30cc"), found)
        self.assertNotIn((b"text", b"\xff" * 4), found)


class TestMarkerAndMapActionStructs(unittest.TestCase):
    """The pure structural facts from NOTES.md section 14: markers, marker
    palette entries and map-action heads are byte-identical between TFL and
    Myth II. Sizes cross-checked against mythextract's own declared formats
    and two independent community tools that ported real levels this way."""

    def test_sizes_match_the_reference_structs(self):
        self.assertEqual(64, mesh.MarkerHead.size)
        self.assertEqual(32, mesh.MarkerPaletteEntry.size)
        self.assertEqual(64, mesh.MapActionHead.size)


class TestParamTypeResolution(unittest.TestCase):
    def test_sb_never_reinterprets(self):
        for raw in range(21):
            self.assertEqual(
                mesh.ParamType(raw), mesh.resolve_param_type(raw, formats.SB)
            )

    def test_tfl_ambiguous_codes_resolve_per_notes_section_14(self):
        cases = {
            12: mesh.ParamType.WORLD_POINT_2D,
            14: mesh.ParamType.OBJECT_IDENTIFIER,
            16: mesh.ParamType.SOUND_SOURCE_IDENTIFIER,
            18: mesh.ParamType.LOCAL_PROJECTILE_GROUP_IDENTIFIER,
        }
        for raw, expected in cases.items():
            self.assertEqual(expected, mesh.resolve_param_type(raw, formats.TFL))

    def test_tfl_unambiguous_codes_pass_through(self):
        """Codes TFL and Myth II agree on (everything except 12/14/16/18) are
        unaffected by the TFL branch."""
        for raw in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 20):
            self.assertEqual(
                mesh.ParamType(raw), mesh.resolve_param_type(raw, formats.TFL)
            )

    def test_unknown_code_raises_rather_than_guesses(self):
        with self.assertRaises(ValueError):
            mesh.resolve_param_type(99, formats.TFL)


class TestParamDataLength(unittest.TestCase):
    """Every case here is one of the three worked examples in mythextract's
    docs/ActionParamElementFormat.txt, so the byte counts are not guesses."""

    def test_string_is_1_byte_per_char_aligned_to_4(self):
        # "Villagers OBJE\0": 15 bytes incl. null, padded to 16.
        self.assertEqual(16, mesh.param_data_length(mesh.ParamType.STRING, 15))

    def test_action_identifier_is_2_bytes_per_element_padded_to_even_count(self):
        # 3 elements x 2 bytes + 2 pad bytes = 8.
        self.assertEqual(
            8, mesh.param_data_length(mesh.ParamType.ACTION_IDENTIFIER, 3)
        )

    def test_world_point_2d_is_8_bytes_per_pair(self):
        self.assertEqual(8, mesh.param_data_length(mesh.ParamType.WORLD_POINT_2D, 1))
        self.assertEqual(16, mesh.param_data_length(mesh.ParamType.WORLD_POINT_2D, 2))

    def test_tag_reference_types_are_4_bytes_each(self):
        for t in (mesh.ParamType.SOUND, mesh.ParamType.FIELD_NAME, mesh.ParamType.PROJECTILE):
            self.assertEqual(12, mesh.param_data_length(t, 3))


class TestConvertTflMapActions(unittest.TestCase):
    def _action(self, params_bytes, num_params, action_id=1):
        head = mesh.MapActionHead.build(
            id=action_id, expiration_mode=0, type=b"trig", flags=0,
            trigger_time_lower_bound=0, trigger_time_delta=0,
            num_params=num_params, size=len(params_bytes), offset=0, indent=0,
        ).encode()
        return head + params_bytes

    def test_ambiguous_type_is_shifted_data_is_not(self):
        import struct

        param = struct.pack(">HH4s", 12, 1, b"wayp") + struct.pack(">2L", 100, 200)
        buf = self._action(param, num_params=1)

        new_buf, warnings = mesh.convert_tfl_map_actions(buf, action_count=1)
        self.assertEqual([], warnings)
        self.assertEqual(13, struct.unpack_from(">H", new_buf, 64)[0])
        self.assertEqual(param[2:], new_buf[64 + 2 :])  # count/name/data untouched

    def test_unambiguous_type_is_not_touched(self):
        import struct

        param = struct.pack(">HH4s", 3, 1, b"link") + b"\x00\x00\x00\x2a"
        buf = self._action(param, num_params=1)

        new_buf, warnings = mesh.convert_tfl_map_actions(buf, action_count=1)
        self.assertEqual([], warnings)
        self.assertEqual(buf, new_buf)

    def test_multiple_params_walk_correctly(self):
        """A shifted param followed by an unshifted one -- proves the offset
        bookkeeping (which depends on correct byte-length calculation) does
        not desync partway through."""
        import struct

        param1 = struct.pack(">HH4s", 12, 1, b"wayp") + struct.pack(">2L", 1, 2)
        param2 = struct.pack(">HH4s", 5, 1, b"cnt1") + struct.pack(">L", 42)
        buf = self._action(param1 + param2, num_params=2)

        new_buf, warnings = mesh.convert_tfl_map_actions(buf, action_count=1)
        self.assertEqual([], warnings)
        self.assertEqual(13, struct.unpack_from(">H", new_buf, 64)[0])
        self.assertEqual(5, struct.unpack_from(">H", new_buf, 64 + len(param1))[0])

    def test_unknown_type_warns_and_stops_that_actions_walk(self):
        """An unrecognised type means byte length can no longer be trusted --
        continuing to walk would risk corrupting whatever comes after."""
        import struct

        param1 = struct.pack(">HH4s", 250, 1, b"????") + b"\x00" * 4
        param2 = struct.pack(">HH4s", 3, 1, b"link") + b"\x00" * 4
        buf = self._action(param1 + param2, num_params=2)

        new_buf, warnings = mesh.convert_tfl_map_actions(buf, action_count=1)
        self.assertEqual(1, len(warnings))
        self.assertIn("unrecognised parameter type 250", warnings[0])
        self.assertEqual(buf, new_buf, "left fully untouched once trust is lost")

    def test_multiple_actions(self):
        import struct

        param_a = struct.pack(">HH4s", 12, 1, b"wayp") + struct.pack(">2L", 1, 2)
        param_b = struct.pack(">HH4s", 12, 1, b"cent") + struct.pack(">2L", 3, 4)
        head_a = mesh.MapActionHead.build(
            id=1, expiration_mode=0, type=b"trig", flags=0,
            trigger_time_lower_bound=0, trigger_time_delta=0,
            num_params=1, size=len(param_a), offset=0, indent=0,
        ).encode()
        head_b = mesh.MapActionHead.build(
            id=2, expiration_mode=0, type=b"trig", flags=0,
            trigger_time_lower_bound=0, trigger_time_delta=0,
            num_params=1, size=len(param_b), offset=len(param_a), indent=0,
        ).encode()
        buf = head_a + head_b + param_a + param_b

        new_buf, warnings = mesh.convert_tfl_map_actions(buf, action_count=2)
        self.assertEqual([], warnings)
        action_head_end = 2 * mesh.MAP_ACTION_HEAD_SIZE
        self.assertEqual(13, struct.unpack_from(">H", new_buf, action_head_end)[0])
        self.assertEqual(
            13, struct.unpack_from(">H", new_buf, action_head_end + len(param_a))[0]
        )


class TestRemapMarkerPalette(unittest.TestCase):
    def _palette(self, entries):
        return b"".join(
            mesh.MarkerPaletteEntry.build(
                type=int(marker_type), flags=0, marker_tag=tag,
                team_index=-1, netgame_flags=0,
            ).encode()
            for marker_type, tag in entries
        )

    def test_remaps_a_scenery_reference(self):
        from src.idmap import IdMap

        buf = self._palette([(mesh.MarkerType.SCENERY, b"oldi")])
        id_map = IdMap()
        id_map.add(b"scen", b"oldi", b"newi")

        new_buf, warnings = mesh.remap_marker_palette(buf, 1, id_map)
        self.assertEqual([], warnings)
        entry = mesh.MarkerPaletteEntry.unpack(new_buf, 0)
        self.assertEqual(b"newi", entry.marker_tag)

    def test_unmapped_reference_is_left_alone(self):
        from src.idmap import IdMap

        buf = self._palette([(mesh.MarkerType.SCENERY, b"unkn")])
        new_buf, _ = mesh.remap_marker_palette(buf, 1, IdMap())
        self.assertEqual(buf, new_buf)

    def test_no_id_map_leaves_everything_alone(self):
        buf = self._palette([(mesh.MarkerType.SCENERY, b"oldi")])
        new_buf, _ = mesh.remap_marker_palette(buf, 1, None)
        self.assertEqual(buf, new_buf)

    def test_unset_and_type_without_a_tag_are_skipped(self):
        from src.idmap import IdMap

        buf = self._palette(
            [
                (mesh.MarkerType.SCENERY, b"\xff\xff\xff\xff"),  # unset
                (mesh.MarkerType.OBSERVER, b"oldi"),  # no tag type at all
            ]
        )
        id_map = IdMap()
        id_map.add(b"scen", b"oldi", b"newi")  # would match if type were SCENERY

        new_buf, _ = mesh.remap_marker_palette(buf, 2, id_map)
        self.assertEqual(buf, new_buf, "neither entry should have been touched")

    def test_multiple_entries_each_remapped_independently(self):
        from src.idmap import IdMap

        buf = self._palette(
            [
                (mesh.MarkerType.SCENERY, b"tre1"),
                (mesh.MarkerType.UNIT, b"unt1"),
            ]
        )
        id_map = IdMap()
        id_map.add(b"scen", b"tre1", b"tre2")
        id_map.add(b"unit", b"unt1", b"unt2")

        new_buf, _ = mesh.remap_marker_palette(buf, 2, id_map)
        e0 = mesh.MarkerPaletteEntry.unpack(new_buf, 0)
        e1 = mesh.MarkerPaletteEntry.unpack(new_buf, mesh.MARKER_PALETTE_ENTRY_SIZE)
        self.assertEqual(b"tre2", e0.marker_tag)
        self.assertEqual(b"unt2", e1.marker_tag)


class TestEntrypointSynthesis(unittest.TestCase):
    def _convert(self, tags, id_map=None):
        tfl = reader.read_bytes(fixtures.build_tfl_mono(tags))
        return convert_plugin.convert_container(tfl, id_map=id_map)

    def test_one_entrypoint_per_mesh(self):
        """Measured rule: 166 of 166 real plugins have exactly one entrypoint per
        mesh tag."""
        sb, report = self._convert(fixtures.MESH_TAGS)
        self.assertEqual(1, len(sb.entrypoints))
        self.assertEqual(1, len(report.entrypoints))

        # Non-mesh tags never produce an entrypoint.
        sb, _ = self._convert(fixtures.SAMPLE_TAGS)
        self.assertEqual([], sb.entrypoints)

    def test_id_and_name_come_from_the_mesh_tag(self):
        sb, _ = self._convert(fixtures.MESH_TAGS)
        entry = sb.entrypoints[0]
        self.assertEqual(b"30cb".ljust(16, b"\0"), entry.entry_id)
        self.assertEqual(b"301 crows bridge".ljust(32, b"\0"), entry.entry_name)

    def test_printable_name_comes_from_the_description_string_list(self):
        """And it is the *converted* body, so TFL backslash markup has already
        become Myth II pipe markup."""
        sb, _ = self._convert(fixtures.MESH_TAGS)
        self.assertEqual(
            "The Siege of |bCrow's Bridge|p",
            codec.decode_string(sb.entrypoints[0].entry_long_name),
        )

    def test_falls_back_to_the_tag_name_when_the_stli_is_missing(self):
        """Common in real data: 32 of 703 corpus meshes point at a string list
        that lives in another archive."""
        tags = [t for t in fixtures.MESH_TAGS if t[1] != b"stli"]
        sb, report = self._convert(tags)
        self.assertEqual(
            "301 crows bridge", codec.decode_string(sb.entrypoints[0].entry_long_name)
        )
        self.assertTrue(
            [w for w in report.warnings if "not in this container" in w],
            "a missing description must be reported, not silently swallowed",
        )

    def test_falls_back_when_the_mesh_has_no_description_tag(self):
        tags = [(b"no desc mesh", b"mesh", b"nod1", fixtures.mesh_body())]
        sb, report = self._convert(tags)
        self.assertEqual(
            "no desc mesh", codec.decode_string(sb.entrypoints[0].entry_long_name)
        )
        self.assertTrue([w for w in report.warnings if "no map description" in w])

    def test_short_mesh_body_is_reported_not_fatal(self):
        tags = [(b"stub mesh", b"mesh", b"stub", b"too short")]
        sb, report = self._convert(tags)
        self.assertEqual(1, len(sb.entrypoints))
        self.assertEqual(
            "stub mesh", codec.decode_string(sb.entrypoints[0].entry_long_name)
        )
        self.assertTrue([w for w in report.warnings if "need at least" in w])

    def test_remapped_ids_are_followed(self):
        """If the description stli was renamed, the entrypoint must still find
        it, and the mesh's own new ID must be used."""
        m = idmap.IdMap()
        m.add(b"stli", b"30cc", b"9999")
        m.add(b"mesh", b"30cb", b"8888")
        sb, _ = self._convert(fixtures.MESH_TAGS, id_map=m)

        self.assertEqual(b"8888".ljust(16, b"\0"), sb.entrypoints[0].entry_id)
        self.assertEqual(
            "The Siege of |bCrow's Bridge|p",
            codec.decode_string(sb.entrypoints[0].entry_long_name),
        )

    def test_long_name_is_truncated_to_the_field_width(self):
        long_text = b"x" * 100 + b"\0"
        tags = [
            (b"long mesh", b"mesh", b"lng1", fixtures.mesh_body(description_tag=b"lngd")),
            (b"long desc", b"stli", b"lngd", long_text),
        ]
        sb, report = self._convert(tags)
        self.assertEqual(64, len(sb.entrypoints[0].entry_long_name))
        self.assertTrue([w for w in report.warnings if "truncated" in w])

    def test_container_header_counts_the_entrypoints(self):
        sb, _ = self._convert(fixtures.MESH_TAGS)
        self.assertEqual(1, sb.header.entry_tag_count)

    def test_the_packed_plugin_round_trips_with_its_entrypoints(self):
        from src import writer

        sb, _ = self._convert(fixtures.MESH_TAGS)
        data = writer.pack(sb, preserve_layout=False)
        result = reader.read_bytes(data, "converted")

        self.assertEqual(1, len(result.entrypoints))
        self.assertEqual(sb.entrypoints[0].encode(), result.entrypoints[0].encode())
        self.assertEqual([], reader.find_gaps(result))


class TestMeshBodyConversion(unittest.TestCase):
    """The TFL and Myth II mesh headers are both 1024 bytes, so an unconverted
    TFL body looks valid to Myth II and is silently misread from offset 76 on."""

    def _convert(self, body):
        from src.convert.tags import mesh as mesh_converter

        return mesh_converter.convert(body)

    def test_output_is_a_valid_myth_ii_mesh_header(self):
        body = fixtures.mesh_body(description_tag=b"30cc", flags=0x2A)
        converted, _ = self._convert(body)

        self.assertEqual(len(body), len(converted), "header size is unchanged")
        header = mesh.parse_header(converted, formats.SB)
        self.assertEqual(b"30cc", header.map_description_string_list_tag)
        self.assertEqual(0x2A, header.flags)

    # Offsets and sizes describing the body's own layout are deliberately
    # recomputed: terrain quadruples in cell count, so everything after it
    # moves. Every other shared field must still cross unchanged.
    RECOMPUTED = {
        "mesh_offset", "mesh_size",
        "marker_palette_offset", "marker_palette_size",
        "markers_offset", "markers_size",
        "map_actions_offset", "map_action_buffer_size",
        "media_coverage_region_offset", "media_coverage_region_size",
        "mesh_LOD_data_offset", "mesh_LOD_data_size",
        "data_offset", "data_size",
    }

    def test_shared_fields_survive_the_round_trip(self):
        body = fixtures.mesh_body(description_tag=b"30cc", storyline_tag=b"30tx")
        converted, _ = self._convert(body)

        before = mesh.parse_header(body, formats.TFL)
        after = mesh.parse_header(converted, formats.SB)
        from src.convert.tags import mesh as mesh_converter

        checked = 0
        for field in mesh_converter.SHARED_FIELDS:
            if field in self.RECOMPUTED:
                continue
            checked += 1
            self.assertEqual(
                getattr(before, field), getattr(after, field), f"{field} changed"
            )
        self.assertGreater(checked, 20, "should still be checking most fields")

    def test_myth_ii_only_fields_get_the_measured_defaults(self):
        """Values measured across the 40 meshes of Magma - The Fallen Lords v1.9,
        rather than invented."""
        converted, _ = self._convert(fixtures.mesh_body())
        header = mesh.parse_header(converted, formats.SB)

        self.assertEqual(2048, header.ceiling_height)  # 40/40 in the port
        self.assertEqual(0.5, header.reverb_volume)  # 40/40
        self.assertEqual(0.5, header.reverb_damping)  # 40/40
        self.assertEqual(b"\xff" * 4, header.connector_tag)  # 40/40 unset
        self.assertEqual(0, header.extra_flags)

    def test_tfl_only_fields_are_reported_when_they_carry_something(self):
        import struct

        body = bytearray(fixtures.mesh_body())
        # render_variables_tag sits at offset 76 -- where Myth II has connector_tag.
        body[76 - 4 : 76] = b"rvar"
        _, warnings = self._convert(bytes(body))
        self.assertTrue(
            [w for w in warnings if "render_variables_tag" in w],
            f"expected a dropped-field warning, got {warnings}",
        )

    def test_short_body_is_left_alone_and_reported(self):
        converted, warnings = self._convert(b"too short")
        self.assertEqual(b"too short", converted)
        self.assertTrue([w for w in warnings if "shorter than" in w])

    def test_body_is_rebuilt_with_recomputed_offsets(self):
        """The body is no longer copied through: terrain quadruples in cell
        count, so every block after it has to move and the header has to say
        where they went."""
        import struct

        offsets = {n: s for _, n, s, _ in mesh.TFLMeshHeader._layout if n}
        # A 1x1-submesh mesh: 16x16 TFL cells at 8 bytes.
        cells = 16 * 16
        terrain = bytes(cells * 8)
        body = bytearray(fixtures.mesh_body(trailing=terrain))
        struct.pack_into(">H", body, offsets["submesh_width"], 1)
        struct.pack_into(">H", body, offsets["submesh_height"], 1)
        struct.pack_into(">L", body, offsets["mesh_offset"], 0)
        struct.pack_into(">L", body, offsets["mesh_size"], len(terrain))

        converted, warnings = self._convert(bytes(body))
        self.assertEqual([], warnings)
        after = mesh.parse_header(converted, formats.SB)

        # 32x32 cells at 12 bytes -- four times the cells, six times the bytes.
        self.assertEqual(32 * 32 * 12, after.mesh_size)
        self.assertEqual(6 * len(terrain), after.mesh_size)

        # Level-of-detail data must exist and be exactly half a byte per cell.
        self.assertEqual((32 * 32) // 2, after.mesh_LOD_data_size)

        # The body actually contains everything the header promises.
        trailing = converted[mesh.MESH_HEADER_SIZE :]
        self.assertEqual(after.data_size, len(trailing))
        self.assertLessEqual(
            after.mesh_LOD_data_offset + after.mesh_LOD_data_size, len(trailing)
        )

    def test_terrain_heights_are_blended_into_2x2_blocks(self):
        """One TFL cell becomes the four Myth II cells covering the same
        ground: the first keeps its height, the others sit between it and its
        neighbours, and every other field is copied."""
        import struct

        offsets = {n: s for _, n, s, _ in mesh.TFLMeshHeader._layout if n}
        # 1x1 submesh, every cell distinguishable by its height and normal.
        terrain = bytearray()
        for i in range(16 * 16):
            terrain += struct.pack(">hbbBBH", i * 4, i % 100, 0, 0, 0, 0xFFFF)
        body = bytearray(fixtures.mesh_body(trailing=bytes(terrain)))
        struct.pack_into(">H", body, offsets["submesh_width"], 1)
        struct.pack_into(">H", body, offsets["submesh_height"], 1)
        struct.pack_into(">L", body, offsets["mesh_offset"], 0)
        struct.pack_into(">L", body, offsets["mesh_size"], len(terrain))

        converted, _ = self._convert(bytes(body))
        after = mesh.parse_header(converted, formats.SB)
        out = converted[mesh.MESH_HEADER_SIZE + after.mesh_offset :]

        def height_at(x, y):
            return struct.unpack_from(">h", out, (y * 32 + x) * 12)[0]

        def normal_at(x, y):
            return struct.unpack_from(">b", out, (y * 32 + x) * 12 + 2)[0]

        # Source cell (3, 5) has height (5*16+3)*4 = 332; east 336, south 396,
        # southeast 400. Its 2x2 block is at (6, 10).
        self.assertEqual(332, height_at(6, 10))
        self.assertEqual(334, height_at(7, 10))
        self.assertEqual(364, height_at(6, 11))
        self.assertEqual(366, height_at(7, 11))
        for dx in (0, 1):
            for dy in (0, 1):
                self.assertEqual(83, normal_at(6 + dx, 10 + dy))
        # The last column and row have no neighbour beyond, so they stay level.
        last = (15 * 16 + 15) * 4
        for dx in (0, 1):
            for dy in (0, 1):
                self.assertEqual(last, height_at(30 + dx, 30 + dy))

    def test_media_height_is_written_into_every_cell(self):
        import struct

        offsets = {n: s for _, n, s, _ in mesh.TFLMeshHeader._layout if n}
        terrain = bytes(16 * 16 * 8)
        body = bytearray(fixtures.mesh_body(trailing=terrain))
        struct.pack_into(">H", body, offsets["submesh_width"], 1)
        struct.pack_into(">H", body, offsets["submesh_height"], 1)
        struct.pack_into(">L", body, offsets["mesh_offset"], 0)
        struct.pack_into(">L", body, offsets["mesh_size"], len(terrain))

        from src.convert import plugin as convert_plugin
        from src.convert.tags import mesh as mesh_converter

        context = convert_plugin.ConversionContext(mesh_defaults={"media_height": -512})
        converted, warnings = mesh_converter.convert(bytes(body), context)
        self.assertEqual([], warnings, "media_height is a recognised override")

        after = mesh.parse_header(converted, formats.SB)
        out = converted[mesh.MESH_HEADER_SIZE + after.mesh_offset :]
        for index in (0, 17, 1023):
            media_height = struct.unpack_from(">h", out, index * 12 + 8)[0]
            self.assertEqual(-512, media_height)
            model_index = struct.unpack_from(">H", out, index * 12 + 10)[0]
            self.assertEqual(mesh.NO_MODEL_INDEX, model_index)

    def test_map_action_param_types_are_corrected(self):
        """The actual fix for the EXCEPTION_ACCESS_VIOLATION in byte_swap_data
        (NOTES.md section 14): TFL param type 12 means WORLD_POINT_2D, which
        Myth II numbers 13. Left uncorrected, the engine misreads every
        parameter after the first wrongly-typed one."""
        import struct

        head = mesh.MapActionHead.build(
            id=1, expiration_mode=0, type=b"trig", flags=0,
            trigger_time_lower_bound=0, trigger_time_delta=0,
            num_params=1, size=16, offset=0, indent=0,
        ).encode()
        param = struct.pack(">HH4s", 12, 1, b"wayp") + struct.pack(">2L", 100, 200)
        actions = head + param

        offsets = {n: s for _, n, s, _ in mesh.TFLMeshHeader._layout if n}
        header_bytes = bytearray(fixtures.mesh_body(trailing=actions))
        struct.pack_into(">L", header_bytes, offsets["map_action_count"], 1)
        struct.pack_into(">L", header_bytes, offsets["map_actions_offset"], 0)
        struct.pack_into(">L", header_bytes, offsets["map_action_buffer_size"], len(actions))

        converted, warnings = self._convert(bytes(header_bytes))
        self.assertEqual([], warnings)
        new_type = struct.unpack_from(">H", converted, mesh.MESH_HEADER_SIZE + 64)[0]
        self.assertEqual(13, new_type, "TFL raw 12 must become Myth II's WORLD_POINT_2D (13)")
        # The actual position data is untouched -- only the type code changes.
        self.assertEqual(
            struct.pack(">2L", 100, 200),
            converted[mesh.MESH_HEADER_SIZE + 64 + 8 :][:8],
        )

    def test_marker_palette_tag_is_remapped(self):
        import struct

        from src.idmap import IdMap
        from src.convert.tags import mesh as mesh_converter
        from src.convert import plugin as convert_plugin

        entry = mesh.MarkerPaletteEntry.build(
            type=int(mesh.MarkerType.SCENERY), flags=0,
            marker_tag=b"oldi", team_index=-1, netgame_flags=0,
        ).encode()

        offsets = {n: s for _, n, s, _ in mesh.TFLMeshHeader._layout if n}
        header_bytes = bytearray(fixtures.mesh_body(trailing=entry))
        struct.pack_into(">L", header_bytes, offsets["marker_palette_entries"], 1)
        struct.pack_into(">L", header_bytes, offsets["marker_palette_offset"], 0)
        struct.pack_into(">L", header_bytes, offsets["marker_palette_size"], len(entry))

        id_map = IdMap()
        id_map.add(b"scen", b"oldi", b"newi")
        context = convert_plugin.ConversionContext(id_map=id_map)

        converted, warnings = mesh_converter.convert(bytes(header_bytes), context)
        self.assertEqual([], warnings)
        remapped = mesh.MarkerPaletteEntry.unpack(converted, mesh.MESH_HEADER_SIZE)
        self.assertEqual(b"newi", remapped.marker_tag)

    def test_header_tag_references_are_remapped(self):
        """A decisions-file mapping must reach the mesh header itself, not just
        the unresolved-references report. Found in-engine: `medi.mawa` mapped
        to `ma2w` still failed with "couldn't read header for media definition
        'mawa'", because the header kept the TFL id."""
        import struct

        from src.idmap import IdMap
        from src.convert.tags import mesh as mesh_converter
        from src.convert import plugin as convert_plugin

        offsets = {n: s for _, n, s, _ in mesh.TFLMeshHeader._layout if n}
        body = bytearray(fixtures.mesh_body(trailing=b""))
        struct.pack_into(">4s", body, offsets["media_tag"], b"mawa")

        id_map = IdMap()
        id_map.add(b"medi", b"mawa", b"ma2w")
        context = convert_plugin.ConversionContext(id_map=id_map)

        converted, _ = mesh_converter.convert(bytes(body), context)
        header = mesh.parse_header(converted, formats.SB)
        self.assertEqual(b"ma2w", header.media_tag)

    def test_malformed_trailing_data_is_reported_not_crashed(self):
        """Counts that do not match the available bytes must not raise -- a
        converter that crashes on one bad mesh takes the whole plugin with it."""
        import struct

        offsets = {n: s for _, n, s, _ in mesh.TFLMeshHeader._layout if n}
        header_bytes = bytearray(fixtures.mesh_body(trailing=b""))
        struct.pack_into(">L", header_bytes, offsets["map_action_count"], 7)
        struct.pack_into(">L", header_bytes, offsets["map_action_buffer_size"], 0)

        converted, warnings = self._convert(bytes(header_bytes))
        self.assertTrue(
            [w for w in warnings if "map actions" in w],
            f"expected a map action warning, got {warnings}",
        )
        # Still produced a usable mesh rather than raising.
        self.assertGreaterEqual(len(converted), mesh.MESH_HEADER_SIZE)

    def test_a_block_outside_the_body_is_reported_not_fatal(self):
        """A header claiming a block bigger than the body it lives in must cost
        that block, not the whole level."""
        import struct

        offsets = {n: s for _, n, s, _ in mesh.TFLMeshHeader._layout if n}
        body = bytearray(fixtures.mesh_body(trailing=b"\x00" * 64))
        struct.pack_into(">L", body, offsets["markers_offset"], 0)
        struct.pack_into(">L", body, offsets["markers_size"], 1 << 20)

        converted, warnings = self._convert(bytes(body))
        self.assertTrue([w for w in warnings if "markers" in w and "outside" in w])
        self.assertGreaterEqual(len(converted), mesh.MESH_HEADER_SIZE)

    def test_media_coverage_is_carried_verbatim(self):
        """Where the water is. Dropping it left water uncharted in-engine;
        Magma's port of Crow's Bridge keeps TFL's block, re-traced."""
        import struct

        offsets = {n: s for _, n, s, _ in mesh.TFLMeshHeader._layout if n}
        coverage = b"\x00\x3b\x00\xb6\x06\x00\x00\x3c\x00\xb6\x06\x00"
        body = bytearray(fixtures.mesh_body(trailing=b"\xaa" * 8 + coverage))
        struct.pack_into(">L", body, offsets["media_coverage_region_offset"], 8)
        struct.pack_into(">L", body, offsets["media_coverage_region_size"], len(coverage))

        converted, _ = self._convert(bytes(body))
        after = mesh.parse_header(converted, formats.SB)
        start = mesh.MESH_HEADER_SIZE + after.media_coverage_region_offset
        self.assertEqual(len(coverage), after.media_coverage_region_size)
        self.assertEqual(coverage, converted[start : start + len(coverage)])

    def test_vtfl_flag_is_opt_in(self):
        from src.convert.tags import mesh as mesh_converter

        class Ctx:
            use_vtfl = True

        plain, _ = mesh_converter.convert(fixtures.mesh_body())
        self.assertFalse(
            mesh.parse_header(plain, formats.SB).flags & mesh.MeshFlags.USES_VTFL
        )

        opted, warnings = mesh_converter.convert(fixtures.mesh_body(), Ctx())
        self.assertTrue(
            mesh.parse_header(opted, formats.SB).flags & mesh.MeshFlags.USES_VTFL
        )
        self.assertTrue([w for w in warnings if "USES_VTFL" in w])

    def test_entrypoints_still_work_after_mesh_conversion(self):
        """Entrypoint synthesis reads mesh headers from the *source* tags, since
        the converted ones are now in Myth II layout."""
        tfl = reader.read_bytes(fixtures.build_tfl_mono(fixtures.MESH_TAGS))
        sb, _ = convert_plugin.convert_container(tfl)

        self.assertEqual(1, len(sb.entrypoints))
        self.assertEqual(
            "The Siege of |bCrow's Bridge|p",
            codec.decode_string(sb.entrypoints[0].entry_long_name),
        )
        # And the converted mesh really is Myth II layout now.
        converted_mesh = [t for t in sb.tags if t.tag_type == b"mesh"][0]
        header = mesh.parse_header(converted_mesh.body, formats.SB)
        self.assertEqual(2048, header.ceiling_height)


class TestRealPluginMeshBodies(unittest.TestCase):
    """The gate that actually matters for section 14: every mesh in a real
    93 MB TFL plugin must walk without error. Skips cleanly without a sample,
    same convention as tests/test_roundtrip.py."""

    def _sample_path(self):
        import pathlib

        single = os.environ.get("MYTH_SAMPLE_PLUGIN")
        if single and pathlib.Path(single).is_file():
            return pathlib.Path(single)
        directory = os.environ.get("MYTH_SAMPLE_DIR")
        if directory:
            for entry in sorted(pathlib.Path(directory).iterdir()):
                if entry.is_file() and entry.suffix.lower() == ".gor":
                    return entry
        return None

    def test_every_mesh_in_a_real_plugin_walks_cleanly(self):
        path = self._sample_path()
        if not path:
            self.skipTest(
                "No sample supplied. Set MYTH_SAMPLE_PLUGIN=<file.gor> or "
                "MYTH_SAMPLE_DIR=<dir> to run this gate."
            )

        m = reader.read(path)
        if m.is_sb:
            self.skipTest(f"{path.name} is a Myth II container, not TFL")

        meshes = m.by_type(b"mesh")
        self.assertGreater(len(meshes), 0, "sample has no mesh tags")

        total_actions = total_palette = 0
        for tag in meshes:
            header = mesh.parse_header(tag.body, formats.TFL)
            trailing = tag.body[mesh.MESH_HEADER_SIZE :]

            if header.map_action_count:
                start, size = header.map_actions_offset, header.map_action_buffer_size
                _, warnings = mesh.convert_tfl_map_actions(
                    bytes(trailing[start : start + size]), header.map_action_count
                )
                self.assertEqual(
                    [], warnings, f"mesh.{tag.tag_id}: {warnings}"
                )
                total_actions += header.map_action_count

            if header.marker_palette_entries:
                start = header.marker_palette_offset
                size = header.marker_palette_size
                _, warnings = mesh.remap_marker_palette(
                    bytes(trailing[start : start + size]),
                    header.marker_palette_entries,
                    id_map=None,
                )
                self.assertEqual([], warnings, f"mesh.{tag.tag_id}: {warnings}")
                total_palette += header.marker_palette_entries

        self.assertGreater(total_actions, 0, "sample has no map actions to exercise")
        self.assertGreater(total_palette, 0, "sample has no palette entries to exercise")


if __name__ == "__main__":
    unittest.main()
