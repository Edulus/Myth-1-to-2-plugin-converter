"""Tests for the TFL -> Myth II conversion layer."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import codec, formats, idmap, reader, writer  # noqa: E402
from src.convert import headers, plugin as convert_plugin  # noqa: E402
from src.convert.tags import text as text_converter  # noqa: E402

from . import fixtures  # noqa: E402


class TestTextConversion(unittest.TestCase):
    def test_formatting_escape_is_translated(self):
        """TFL introduces format codes with a backslash, Myth II with a pipe."""
        body, warnings = text_converter.convert(rb"Plain \bbold\p and \iitalic\p.")
        self.assertEqual(rb"Plain |bbold|p and |iitalic|p.".replace(b"\\", b"|"), body)
        self.assertEqual(b"Plain |bbold|p and |iitalic|p.", body)
        self.assertEqual([], warnings)

    def test_empty_body_is_untouched(self):
        self.assertEqual((b"", []), text_converter.convert(b""))

    def test_plain_text_is_unchanged(self):
        body = b"No formatting here at all.\r\rSecond paragraph."
        self.assertEqual((body, []), text_converter.convert(body))

    def test_warns_about_backslashes_that_are_not_format_codes(self):
        """A literal backslash is indistinguishable from an escape, so it gets
        converted too. That is lossy and the caller should hear about it."""
        body, warnings = text_converter.convert(rb"C:\temp and \bbold\p")
        self.assertEqual(b"C:|temp and |bbold|p", body)
        self.assertEqual(1, len(warnings))
        self.assertIn("1 of 3 backslashes", warnings[0])

    def test_a_literal_backslash_can_be_indistinguishable_from_markup(self):
        r"""The heuristic has a real limit worth pinning down: `C:\path` ends in
        a backslash followed by 'p', which is exactly the 'plain' format code.
        No warning is possible, and the text is silently altered."""
        body, warnings = text_converter.convert(rb"C:\path")
        self.assertEqual(b"C:|path", body)
        self.assertEqual([], warnings, "indistinguishable from |p markup")

    def test_stli_splitting_for_display(self):
        strings = text_converter.to_strings(b"first\0second\0\0third\r\n")
        self.assertEqual(["first", "second", "third"], strings)

    def test_registry_covers_text_and_stli(self):
        from src.convert import tags

        self.assertEqual(
            [b".256", b"arti", b"geom", b"meef", b"meli", b"mesh", b"mode", b"mons", b"obje", b"part", b"proj", b"scen", b"stli", b"text", b"unit"], tags.supported_types()
        )
        self.assertIs(text_converter, tags.converter_for(b"text"))
        self.assertIs(text_converter, tags.converter_for(b"stli"))
        self.assertIsNone(tags.converter_for(b"scri"))


class TestHeaderConversion(unittest.TestCase):
    def _tfl_header(self, **overrides):
        raw = fixtures.tfl_tag_header(
            b"a tag", b"text", b"tst1", 128, 41, **overrides
        )
        return formats.TFLTagHeader.unpack(raw)

    def test_fields_carry_across(self):
        sb, warnings = headers.convert_tag_header(self._tfl_header(), body_length=37)

        self.assertEqual(b"text", sb.tag_type)
        self.assertEqual(b"tst1", sb.tag_id)
        self.assertEqual(b"a tag".ljust(32, b"\0"), sb.name)
        self.assertEqual(37, sb.tag_data_size, "size comes from the converted body")
        self.assertEqual(formats.SB_TAG_SIGNATURE, sb.signature)
        self.assertEqual([], warnings)
        self.assertEqual(formats.TAG_HEADER_SIZE, len(sb.encode()))

    def test_dropped_tfl_fields_are_reported(self):
        """tfl2sb silently discards tag_version and flags. Real TFL data has
        non-zero values in both, so silence would hide real loss."""
        _, warnings = headers.convert_tag_header(
            self._tfl_header(tag_version=3, flags=5), body_length=1
        )
        self.assertEqual(2, len(warnings))
        self.assertIn("tag_version=3", warnings[0])
        self.assertIn("flags=5", warnings[1])

    def test_version_too_large_for_int16_is_clamped_and_reported(self):
        """TFL's version is uint32 and Myth II's is int16; mythextract assigns
        straight across, which wraps silently."""
        sb, warnings = headers.convert_tag_header(
            self._tfl_header(version=70000), body_length=1
        )
        self.assertEqual(headers.INT16_MAX, sb.version)
        self.assertEqual(1, len(warnings))
        self.assertIn("does not fit", warnings[0])

    def test_id_and_name_can_be_overridden_for_remapping(self):
        sb, _ = headers.convert_tag_header(
            self._tfl_header(), body_length=1, tag_id=b"30cb", name=b"301 crows bridge"
        )
        self.assertEqual(b"30cb", sb.tag_id)
        self.assertEqual(b"301 crows bridge".ljust(32, b"\0"), sb.name)

    def test_rejects_identifier_outside_int16(self):
        with self.assertRaises(ValueError):
            headers.convert_tag_header(self._tfl_header(), 1, identifier=40000)


class TestIdMap(unittest.TestCase):
    def test_lookup_and_passthrough(self):
        m = idmap.IdMap()
        m.add(b"text", b"aaaa", b"30cb", "301 crows bridge")

        self.assertEqual(b"30cb", m.lookup(b"text", b"aaaa")[0])
        self.assertEqual(b"30cb", m.map_id(b"text", b"aaaa"))
        # Unmapped IDs pass through -- custom content keeps its own IDs.
        self.assertEqual(b"bbbb", m.map_id(b"text", b"bbbb"))
        self.assertIsNone(m.lookup(b"stli", b"aaaa"), "type is part of the key")

    def test_accepts_str_or_bytes(self):
        m = idmap.IdMap()
        m.add("text", "aaaa", "30cb")
        self.assertEqual(b"30cb", m.map_id(b"text", b"aaaa"))
        self.assertIn(("text", "aaaa"), m)

    def test_rejects_wrong_length_ids(self):
        m = idmap.IdMap()
        with self.assertRaises(ValueError):
            m.add(b"text", b"toolong", b"30cb")

    def test_rejects_conflicting_mapping(self):
        m = idmap.IdMap()
        m.add(b"text", b"aaaa", b"30cb")
        m.add(b"text", b"aaaa", b"30cb")  # identical is fine
        with self.assertRaises(ValueError):
            m.add(b"text", b"aaaa", b"30cc")

    def test_stock_level_table_is_intact(self):
        """Seeded verbatim from mythextract's TFLTagMap -- 25 levels, two of
        which deliberately have no caption tag."""
        self.assertEqual(25, len(idmap.STOCK_TFL_LEVEL_TEXT))
        self.assertEqual(3, len(idmap.stock_level_text_targets("01")))
        self.assertEqual(
            2, len(idmap.stock_level_text_targets("15")), "level 15 has no captions"
        )
        types = [t for t, _, _ in idmap.stock_level_text_targets("01")]
        self.assertEqual([b"text", b"stli", b"stli"], types)


# Every converted monster gains an object of its own (convert/plugin.py).
MONSTERS = sum(1 for t in fixtures.SAMPLE_TAGS if t[1] == b"mons")


class TestContainerConversion(unittest.TestCase):
    def setUp(self):
        self.tfl = reader.read_bytes(fixtures.build_tfl_mono(fixtures.SAMPLE_TAGS))

    def test_produces_a_readable_myth_ii_container(self):
        sb, report = convert_plugin.convert_container(self.tfl)
        data = writer.pack(sb, preserve_layout=False)

        result = reader.read_bytes(data, "converted")
        self.assertTrue(result.is_sb)
        self.assertEqual(len(fixtures.SAMPLE_TAGS) + MONSTERS, len(result.tags), "plus an object per monster")
        self.assertEqual(
            int(formats.ArchiveType.PLUGIN),
            result.header.type,
            "a converted TFL .gor becomes a plugin, not a foundation archive",
        )
        self.assertEqual([], reader.find_gaps(result))

    def test_text_and_stli_are_converted_and_the_rest_passes_through(self):
        _, report = convert_plugin.convert_container(self.tfl)

        converted = {o.tag_type for o in report.converted()}
        self.assertEqual({b"text", b"stli", b"mons", b"obje"}, converted)
        self.assertEqual(
            {b"scri": 1, b"soun": 1}, report.unsupported_types()
        )

    def test_passed_through_bodies_are_byte_identical(self):
        """We do not pretend to convert what we cannot. An unconverted body must
        come out exactly as it went in."""
        sb, _ = convert_plugin.convert_container(self.tfl)
        for original, converted in zip(self.tfl.tags, sb.tags):
            if original.tag_type not in (b"text", b"stli", b"mesh", b"mons"):
                self.assertEqual(original.body, converted.body, original.tag_type)

    def test_formatting_is_actually_translated_end_to_end(self):
        tags = [(b"story", b"text", b"txt1", rb"The \bFallen\p Lords")]
        tfl = reader.read_bytes(fixtures.build_tfl_mono(tags))
        sb, _ = convert_plugin.convert_container(tfl)
        self.assertEqual(b"The |bFallen|p Lords", sb.tags[0].body)

    def test_tag_identifiers_are_unique(self):
        """Real plugins never reuse a tag identifier; all-zero is unattested."""
        sb, _ = convert_plugin.convert_container(self.tfl)
        identifiers = [t.header.identifier for t in sb.tags]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertNotIn(0, identifiers)

    def test_reports_the_honest_warnings(self):
        _, report = convert_plugin.convert_container(self.tfl)
        joined = "\n".join(report.warnings)
        self.assertIn("checksum", joined)
        self.assertIn("no entrypoints", joined)
        self.assertIn("passed through", joined)

    def test_id_remapping_is_applied_to_the_directory(self):
        m = idmap.IdMap()
        m.add(b"text", b"tst1", b"30cb", "301 crows bridge")
        sb, report = convert_plugin.convert_container(self.tfl, id_map=m)

        self.assertEqual(b"30cb", sb.tags[0].tag_id)
        self.assertEqual(b"301 crows bridge".ljust(32, b"\0"), sb.tags[0].header.name)
        self.assertEqual(1, len(report.renamed()))

    def test_refuses_to_convert_a_myth_ii_container(self):
        sb = reader.read_bytes(fixtures.build_sb_mono(fixtures.SAMPLE_TAGS))
        with self.assertRaises(convert_plugin.ConversionError):
            convert_plugin.convert_container(sb)

    def test_report_formats_without_error(self):
        _, report = convert_plugin.convert_container(self.tfl)
        lines = convert_plugin.format_report(report, "in.gor", "out.plugin")
        joined = "\n".join(lines)
        self.assertIn("UNCONVERTED", joined)
        self.assertTrue(all(isinstance(line, str) for line in lines))


class TestConvertFile(unittest.TestCase):
    def test_round_trips_through_disk(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            src = tmp / "in.gor"
            out = tmp / "out.plugin"
            src.write_bytes(fixtures.build_tfl_mono(fixtures.SAMPLE_TAGS))

            report, written = convert_plugin.convert_file(src, out, name="Converted")

            self.assertEqual(written, out.stat().st_size)
            result = reader.read(out)
            self.assertTrue(result.is_sb)
            self.assertEqual("Converted", codec.decode_string(result.header.name))
            self.assertEqual(len(fixtures.SAMPLE_TAGS) + MONSTERS, len(result.tags))
            self.assertEqual(len(fixtures.SAMPLE_TAGS) + MONSTERS, len(report.outcomes))

    def test_the_internal_name_defaults_to_the_output_filename(self):
        """Myth II identifies plugins by this name; defaulting to the source's
        let two plugins converted from one .gor hide each other in-engine."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            src = tmp / "cbc.TFL.mauriac.gor"
            out = tmp / "ZZ Mauriac"
            src.write_bytes(fixtures.build_tfl_mono(fixtures.SAMPLE_TAGS))
            convert_plugin.convert_file(src, out)
            self.assertEqual("ZZ Mauriac", codec.decode_string(reader.read(out).header.name))

    def test_warns_when_output_filename_is_too_long_for_myth_ii(self):
        """Myth II silently ignores plugins with filenames over 32 characters --
        verified in-engine. Nothing reports it, so we have to."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            src = tmp / "in.gor"
            src.write_bytes(fixtures.build_tfl_mono(fixtures.SAMPLE_TAGS))

            short = tmp / ("s" * 32)
            report, _ = convert_plugin.convert_file(src, short)
            self.assertFalse([w for w in report.warnings if "filename" in w])

            long = tmp / ("x" * 33)
            report, _ = convert_plugin.convert_file(src, long)
            warned = [w for w in report.warnings if "filename" in w]
            self.assertEqual(1, len(warned))
            self.assertIn("33 characters", warned[0])


if __name__ == "__main__":
    unittest.main()
