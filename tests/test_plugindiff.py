"""Tests for the tag-by-tag container diff."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import plugindiff, reader  # noqa: E402

from . import fixtures  # noqa: E402


def _mono(tags, **kwargs):
    return reader.read_bytes(fixtures.build_sb_mono(tags, **kwargs))


class TestDiff(unittest.TestCase):
    def test_identical_containers_show_no_differences(self):
        left = _mono(fixtures.SAMPLE_TAGS, entrypoints=fixtures.SAMPLE_ENTRYPOINTS)
        right = _mono(fixtures.SAMPLE_TAGS, entrypoints=fixtures.SAMPLE_ENTRYPOINTS)
        result = plugindiff.diff(left, right)
        self.assertTrue(result.identical)
        self.assertEqual([], result.changed_tags())

    def test_detects_changed_body(self):
        modified = list(fixtures.SAMPLE_TAGS)
        modified[0] = (b"test text", b"text", b"tst1", b"Different content entirely.")
        result = plugindiff.diff(_mono(fixtures.SAMPLE_TAGS), _mono(modified))

        self.assertFalse(result.identical)
        changed = result.changed_tags()
        self.assertEqual(1, len(changed))
        self.assertEqual("changed", changed[0].status)
        self.assertEqual("text.tst1", changed[0].label)
        # tag_data_size is a common header field, so the size change surfaces too.
        self.assertIn("tag_data_size", changed[0].header_fields())

    def test_detects_added_and_removed_tags(self):
        fewer = fixtures.SAMPLE_TAGS[:3]
        result = plugindiff.diff(_mono(fixtures.SAMPLE_TAGS), _mono(fewer))
        statuses = {t.label: t.status for t in result.changed_tags()}
        self.assertEqual({"mons.tst4": "removed", "soun.tst5": "removed"}, statuses)

        reverse = plugindiff.diff(_mono(fewer), _mono(fixtures.SAMPLE_TAGS))
        statuses = {t.label: t.status for t in reverse.changed_tags()}
        self.assertEqual({"mons.tst4": "added", "soun.tst5": "added"}, statuses)

    def test_detects_header_only_change(self):
        """Same body, different tag name -- worth flagging during conversion,
        since ID/name remapping is exactly what Phase 2 does."""
        renamed = list(fixtures.SAMPLE_TAGS)
        renamed[0] = (b"renamed tag", b"text", b"tst1", fixtures.SAMPLE_TAGS[0][3])
        result = plugindiff.diff(_mono(fixtures.SAMPLE_TAGS), _mono(renamed))

        changed = result.changed_tags()
        self.assertEqual(1, len(changed))
        self.assertEqual("header-only", changed[0].status)
        self.assertIn("name", changed[0].header_fields())

    def test_detects_container_header_change(self):
        result = plugindiff.diff(
            _mono(fixtures.SAMPLE_TAGS, name=b"one"),
            _mono(fixtures.SAMPLE_TAGS, name=b"two"),
        )
        self.assertIn("name", result.header_fields)
        self.assertFalse(result.identical)

    def test_detects_entrypoint_changes(self):
        one = fixtures.SAMPLE_ENTRYPOINTS[:1]
        result = plugindiff.diff(
            _mono(fixtures.SAMPLE_TAGS, entrypoints=one),
            _mono(fixtures.SAMPLE_TAGS, entrypoints=fixtures.SAMPLE_ENTRYPOINTS),
        )
        self.assertEqual(1, len(result.entrypoints))
        self.assertEqual("added", result.entrypoints[0][0])

    def test_diffs_across_game_versions(self):
        """TFL and SB headers share almost no fields; the diff must still work."""
        tfl = reader.read_bytes(fixtures.build_tfl_mono(fixtures.SAMPLE_TAGS))
        sb = _mono(fixtures.SAMPLE_TAGS)
        result = plugindiff.diff(tfl, sb)

        self.assertIn("game_version", result.header_fields)
        self.assertEqual((1, 2), result.header_fields["game_version"])
        # Same bodies on both sides, so no tag should read as changed.
        self.assertEqual([], [t for t in result.tags if t.status == "changed"])

    def test_format_report_is_printable(self):
        result = plugindiff.diff(_mono(fixtures.SAMPLE_TAGS), _mono(fixtures.SAMPLE_TAGS[:2]))
        lines = plugindiff.format_report(result, "left.plugin", "right.plugin")
        self.assertTrue(all(isinstance(line, str) for line in lines))
        self.assertIn("left.plugin", "\n".join(lines))
        self.assertIn("removed", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
