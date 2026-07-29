"""Tests for mesh header parsing and entrypoint synthesis."""

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

    def test_shared_fields_survive_the_round_trip(self):
        body = fixtures.mesh_body(description_tag=b"30cc", storyline_tag=b"30tx")
        converted, _ = self._convert(body)

        before = mesh.parse_header(body, formats.TFL)
        after = mesh.parse_header(converted, formats.SB)
        from src.convert.tags import mesh as mesh_converter

        for field in mesh_converter.SHARED_FIELDS:
            self.assertEqual(
                getattr(before, field), getattr(after, field), f"{field} changed"
            )

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

    def test_trailing_body_data_is_preserved_verbatim(self):
        """Only the header is converted. Terrain, markers and map actions are
        copied untouched -- and said to be."""
        trailing = bytes(range(256)) * 4
        body = fixtures.mesh_body(trailing=trailing)
        converted, _ = self._convert(body)
        self.assertEqual(trailing, converted[mesh.MESH_HEADER_SIZE :])

    def test_map_actions_and_markers_are_flagged_as_unconverted(self):
        import struct

        body = bytearray(fixtures.mesh_body())
        offsets = {n: s for _, n, s, _ in mesh.TFLMeshHeader._layout if n}
        struct.pack_into(">L", body, offsets["map_action_count"], 7)
        struct.pack_into(">L", body, offsets["marker_count"], 12)

        _, warnings = self._convert(bytes(body))
        self.assertTrue([w for w in warnings if "7 map actions" in w])
        self.assertTrue([w for w in warnings if "12 markers" in w])

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


if __name__ == "__main__":
    unittest.main()
