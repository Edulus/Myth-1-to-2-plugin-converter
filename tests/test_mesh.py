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


if __name__ == "__main__":
    unittest.main()
