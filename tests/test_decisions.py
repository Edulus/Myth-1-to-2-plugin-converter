"""Tests for the human-in-the-loop decisions file."""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import codec, decisions, formats, mesh, reader  # noqa: E402
from src.convert import plugin as convert_plugin  # noqa: E402

from . import fixtures  # noqa: E402


def write(text):
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".toml", delete=False, encoding="utf-8"
    )
    handle.write(text)
    handle.close()
    return pathlib.Path(handle.name)


class TestLoading(unittest.TestCase):
    def test_reads_options_mappings_and_overrides(self):
        path = write(
            """
            [options]
            use_vtfl = true
            plugin_name = "My Plugin"

            [[tag]]
            type = "meli"
            id = "deml"
            map_to = "gras"
            name = "grassland"

            [mesh_defaults]
            ceiling_height = 1024
            """
        )
        chosen = decisions.load(path)

        self.assertTrue(chosen.use_vtfl)
        self.assertEqual("My Plugin", chosen.plugin_name)
        self.assertEqual({"ceiling_height": 1024}, chosen.mesh_defaults)

        mapping = chosen.id_map()
        self.assertEqual(b"gras", mapping.map_id(b"meli", b"deml"))

    def test_blank_map_to_means_undecided_not_mapped(self):
        """An empty entry is a decision not yet made. It must not silently
        become a mapping to nothing."""
        path = write(
            """
            [[tag]]
            type = "meli"
            id = "deml"
            map_to = ""

            [[tag]]
            type = "medi"
            id = "mawa"
            map_to = "wate"
            """
        )
        chosen = decisions.load(path)

        self.assertEqual(1, len(chosen.unresolved()))
        self.assertEqual("deml", chosen.unresolved()[0]["id"])
        self.assertEqual(1, len(chosen.id_map()))
        self.assertEqual(b"deml", chosen.id_map().map_id(b"meli", b"deml"))

    def test_empty_file_is_valid(self):
        chosen = decisions.load(write(""))
        self.assertEqual([], chosen.tag_map)
        self.assertFalse(chosen.use_vtfl)
        self.assertIsNone(chosen.plugin_name)

    def test_rejects_wrong_length_tag_ids(self):
        path = write('[[tag]]\ntype = "meli"\nid = "toolong"\nmap_to = "gras"\n')
        with self.assertRaises(decisions.DecisionsError) as caught:
            decisions.load(path)
        self.assertIn("exactly 4 characters", str(caught.exception))

    def test_rejects_missing_required_keys(self):
        path = write('[[tag]]\ntype = "meli"\n')
        with self.assertRaises(decisions.DecisionsError) as caught:
            decisions.load(path)
        self.assertIn("missing 'id'", str(caught.exception))

    def test_rejects_malformed_toml_with_the_file_named(self):
        path = write("[options\nbroken")
        with self.assertRaises(decisions.DecisionsError) as caught:
            decisions.load(path)
        self.assertIn(str(path), str(caught.exception))


class TestStubGeneration(unittest.TestCase):
    def _stub(self, unresolved=None, candidates=None):
        report = convert_plugin.ConversionReport()
        return decisions.build_stub(
            report, unresolved or {}, candidates, source_name="test.gor"
        )

    def test_stub_is_valid_toml_and_round_trips(self):
        """The generated file has to load back through our own reader --
        otherwise the whole loop is broken."""
        stub = self._stub({(b"meli", b"deml"): 59, (b"medi", b"mawa"): 3})
        path = write(stub)
        chosen = decisions.load(path)

        self.assertEqual(2, len(chosen.tag_map))
        self.assertEqual(2, len(chosen.unresolved()), "entries start undecided")
        self.assertFalse(chosen.use_vtfl, "vtfl is off by default")

    def test_entries_are_ordered_by_how_much_they_matter(self):
        stub = self._stub({(b"meli", b"deml"): 59, (b"medi", b"mawa"): 3})
        self.assertLess(
            stub.index("deml"), stub.index("mawa"), "most-referenced tag comes first"
        )
        self.assertIn("referenced by 59 mesh(es)", stub)

    def test_candidates_are_listed_as_comments(self):
        candidates = {b"meli": [("gras", "grassland", 4), ("carn", "carnage", 7)]}
        stub = self._stub({(b"meli", b"deml"): 59}, candidates)

        self.assertIn("candidates found in your Myth II install", stub)
        self.assertIn("grassland", stub)
        # Comments must not become data.
        chosen = decisions.load(write(stub))
        self.assertEqual(1, len(chosen.tag_map))
        self.assertEqual("", chosen.tag_map[0]["map_to"])

    def test_says_so_when_there_are_no_candidates(self):
        stub = self._stub({(b"xxxx", b"yyyy"): 1}, {})
        self.assertIn("no candidates of this type", stub)

    def test_shaky_defaults_are_flagged_for_review(self):
        """ceiling_height was 40/40 in the reference port; transition_point only
        32/40. A human should be told which is which."""
        stub = self._stub()
        for line in stub.splitlines():
            if line.startswith("# transition_point"):
                self.assertIn("CHECK", line)
            if line.startswith("# ceiling_height"):
                self.assertNotIn("CHECK", line)
                self.assertIn("40/40", line)

    def test_handles_no_unresolved_references(self):
        stub = self._stub({})
        self.assertIn("every referenced tag is present", stub)
        decisions.load(write(stub))  # still valid

    def test_quotes_are_escaped_in_emitted_strings(self):
        """The emitter is hand-rolled, so escaping is worth pinning down."""
        self.assertEqual(r'"a\"b"', decisions._str('a"b'))
        self.assertEqual(r'"a\\b"', decisions._str("a\\b"))
        self.assertEqual(r'"a\nb"', decisions._str("a\nb"))
        self.assertEqual('"a\\u0007b"', decisions._str("a\x07b"))

        # And a name with a quote in it survives a full emit/load round trip.
        stub = decisions.build_stub(
            convert_plugin.ConversionReport(), {}, None, source_name='we"ird.gor'
        )
        self.assertEqual('we"ird', decisions.load(write(stub)).plugin_name)


class TestDecisionsAffectConversion(unittest.TestCase):
    def _convert(self, context=None, id_map=None):
        tfl = reader.read_bytes(fixtures.build_tfl_mono(fixtures.MESH_TAGS))
        return convert_plugin.convert_container(tfl, id_map=id_map, context=context)

    def test_mesh_default_override_is_applied(self):
        context = convert_plugin.ConversionContext(mesh_defaults={"ceiling_height": 999})
        sb, _ = self._convert(context)
        header = mesh.parse_header(
            [t for t in sb.tags if t.tag_type == b"mesh"][0].body, formats.SB
        )
        self.assertEqual(999, header.ceiling_height)

    def test_unknown_override_is_reported_not_silently_dropped(self):
        context = convert_plugin.ConversionContext(mesh_defaults={"not_a_field": 1})
        _, report = self._convert(context)
        self.assertTrue(
            [w for _, w in report.tag_warnings() if "not a synthesised" in w]
        )

    def test_vtfl_option_reaches_the_mesh_converter(self):
        sb, _ = self._convert(convert_plugin.ConversionContext(use_vtfl=True))
        header = mesh.parse_header(
            [t for t in sb.tags if t.tag_type == b"mesh"][0].body, formats.SB
        )
        self.assertTrue(header.flags & mesh.MeshFlags.USES_VTFL)

    def test_unresolved_references_are_detected_and_reported(self):
        """The mesh points at a description string list that is not in the
        container, which is the whole reason the decisions file exists."""
        tags = [t for t in fixtures.MESH_TAGS if t[1] != b"stli"]
        tfl = reader.read_bytes(fixtures.build_tfl_mono(tags))
        _, report = convert_plugin.convert_container(tfl)

        self.assertIn((b"stli", b"30cc"), report.unresolved)
        self.assertTrue([w for w in report.warnings if "not in this plugin" in w])

    def test_a_mapping_can_resolve_a_dangling_reference(self):
        """Map the missing stli onto one that is present, and it stops being
        unresolved."""
        tags = [t for t in fixtures.MESH_TAGS if t[1] != b"stli"]
        tags.append((b"substitute", b"stli", b"9999", b"Substituted name\0"))
        tfl = reader.read_bytes(fixtures.build_tfl_mono(tags))

        _, before = convert_plugin.convert_container(tfl)
        self.assertIn((b"stli", b"30cc"), before.unresolved)

        chosen = decisions.load(
            write('[[tag]]\ntype = "stli"\nid = "30cc"\nmap_to = "9999"\n')
        )
        _, after = convert_plugin.convert_container(tfl, id_map=chosen.id_map())
        self.assertNotIn((b"stli", b"30cc"), after.unresolved)


if __name__ == "__main__":
    unittest.main()
