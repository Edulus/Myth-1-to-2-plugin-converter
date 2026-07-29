"""Phase 1 correctness gate: read a container, write it back, byte-for-byte.

If we cannot reproduce a known-good plugin exactly, we cannot trust any
conversion built on top of the reader and writer. Nothing in Phase 2 proceeds
until this passes.

Two tiers of test here:

* **Synthetic** -- always runs. Containers built by hand in ``tests/fixtures.py``
  from the documented layout, independently of ``src.writer``. Proves reader and
  writer agree with each other *and* with the spec as we understand it.

* **Real sample** -- skips cleanly when absent, so the suite runs in CI without
  game data. Point it at a plugin with:

      MYTH_SAMPLE_PLUGIN=/path/to/plugin      one file
      MYTH_SAMPLE_DIR=/path/to/plugins        every file in a directory

  Only the real sample can prove our understanding matches what Bungie shipped.
  Until one has been run, this gate is *provisional* -- see test_sample_present.

Written against stdlib ``unittest`` so it runs with no dependencies
(``python -m unittest discover -s tests``); pytest collects it too.
"""

import os
import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import codec, formats, reader, writer  # noqa: E402

from . import fixtures  # noqa: E402


class TestSyntheticRoundTrip(unittest.TestCase):
    """Read/write identity on containers we built ourselves."""

    def assert_round_trips(self, data, label):
        problems = writer.diagnose_round_trip(data, filename=label)
        self.assertEqual(
            [], problems, f"{label} did not round-trip:\n  " + "\n  ".join(problems)
        )
        self.assertEqual(data, writer.round_trip(data, filename=label))

    def test_sb_plugin_round_trips(self):
        data = fixtures.build_sb_mono(
            fixtures.SAMPLE_TAGS, entrypoints=fixtures.SAMPLE_ENTRYPOINTS
        )
        self.assert_round_trips(data, "synthetic-sb-plugin")

    def test_sb_tagset_without_entrypoints_round_trips(self):
        data = fixtures.build_sb_mono(fixtures.SAMPLE_TAGS)
        self.assert_round_trips(data, "synthetic-sb-tagset")

    def test_sb_with_no_tags_round_trips(self):
        data = fixtures.build_sb_mono([])
        self.assert_round_trips(data, "synthetic-sb-empty")

    def test_tfl_mono_round_trips(self):
        data = fixtures.build_tfl_mono(fixtures.SAMPLE_TAGS)
        self.assert_round_trips(data, "synthetic-tfl")

    def test_aliased_bodies_are_preserved(self):
        """Real containers deduplicate identical bodies by pointing several
        directory entries at one offset. Repacking must not silently expand
        them into separate copies."""
        data = fixtures.build_sb_mono(fixtures.SAMPLE_TAGS, alias_bodies=True)
        self.assert_round_trips(data, "synthetic-sb-aliased")

        mono = reader.read_bytes(data)
        offsets = {t.source_offset for t in mono.tags}
        self.assertEqual(1, len(offsets), "fixture should alias every body")

    def test_non_zero_padding_survives(self):
        """'Unused' bytes in real tags are not zero. Zero-filling them on encode
        would break byte-exactness, so prove they are carried through."""
        data = fixtures.build_sb_mono(fixtures.SAMPLE_TAGS)
        self.assertEqual(fixtures.PAD4, data[120:124], "fixture lost its padding")
        self.assertEqual(fixtures.PAD4, writer.round_trip(data)[120:124])

        tfl = fixtures.build_tfl_mono(fixtures.SAMPLE_TAGS)
        self.assertEqual(fixtures.PAD2, tfl[50:52], "fixture lost its padding")
        self.assertEqual(fixtures.PAD2, writer.round_trip(tfl)[50:52])


class TestReaderParsing(unittest.TestCase):
    def setUp(self):
        self.data = fixtures.build_sb_mono(
            fixtures.SAMPLE_TAGS, entrypoints=fixtures.SAMPLE_ENTRYPOINTS
        )
        self.mono = reader.read_bytes(self.data, filename="synthetic")

    def test_detects_game_version(self):
        self.assertEqual(formats.SB, self.mono.game_version)
        self.assertTrue(self.mono.is_sb)
        tfl = reader.read_bytes(fixtures.build_tfl_mono(fixtures.SAMPLE_TAGS))
        self.assertEqual(formats.TFL, tfl.game_version)
        self.assertTrue(tfl.is_tfl)

    def test_reads_every_tag_with_correct_body(self):
        self.assertEqual(len(fixtures.SAMPLE_TAGS), len(self.mono.tags))
        for (name, tag_type, tag_id, body), tag in zip(
            fixtures.SAMPLE_TAGS, self.mono.tags
        ):
            self.assertEqual(tag_type, tag.tag_type)
            self.assertEqual(tag_id, tag.tag_id)
            self.assertEqual(body, tag.body)
            self.assertEqual(codec.decode_string(name), tag.name)

    def test_reads_entrypoints(self):
        self.assertEqual(2, len(self.mono.entrypoints))
        self.assertEqual(
            "The First Test Level",
            codec.decode_string(self.mono.entrypoints[0].entry_long_name),
        )

    def test_find_and_by_type(self):
        self.assertIsNotNone(self.mono.find(b"text", b"tst1"))
        self.assertIsNone(self.mono.find(b"text", b"nope"))
        self.assertEqual(1, len(self.mono.by_type(b"mons")))
        self.assertEqual({b"text", b"stli", b"scri", b"mons", b"soun"},
                         set(self.mono.tag_types()))

    def test_no_gaps_in_a_well_formed_container(self):
        self.assertEqual([], reader.find_gaps(self.mono))

    def test_rejects_non_myth_data(self):
        with self.assertRaises(reader.FormatError):
            reader.read_bytes(b"not a myth file" * 20)

    def test_rejects_truncated_body(self):
        """A directory entry pointing past EOF must fail loudly, not silently
        return a short body."""
        data = bytearray(self.data)
        directory_start = formats.SB_MONO_HEADER_SIZE + 2 * formats.ENTRY_TAG_HEADER_SIZE
        # tag_data_size sits at +48 within an SB tag header.
        struct.pack_into(">l", data, directory_start + 48, 1 << 30)
        with self.assertRaises(reader.FormatError) as caught:
            reader.read_bytes(bytes(data))
        self.assertIn("outside the file", str(caught.exception))

    def test_rejects_mixed_signature(self):
        """An SB container holding a TFL-signed tag header is corrupt."""
        data = bytearray(self.data)
        directory_start = formats.SB_MONO_HEADER_SIZE + 2 * formats.ENTRY_TAG_HEADER_SIZE
        data[directory_start + 60 : directory_start + 64] = b"myth"
        with self.assertRaises(reader.FormatError) as caught:
            reader.read_bytes(bytes(data))
        self.assertIn("signature", str(caught.exception))


class TestWriterRebuildsOffsets(unittest.TestCase):
    def test_directory_offsets_are_recomputed_not_copied(self):
        """The point of the writer: shrink a body and every later offset moves."""
        tags = list(fixtures.SAMPLE_TAGS)
        mono = reader.read_bytes(fixtures.build_sb_mono(tags))

        mono.tags[0].body = b"shorter"
        repacked = reader.read_bytes(writer.pack(mono, preserve_layout=True))

        self.assertEqual(b"shorter", repacked.tags[0].body)
        self.assertEqual(7, repacked.tags[0].header.tag_data_size)
        for original, rebuilt in zip(mono.tags[1:], repacked.tags[1:]):
            self.assertEqual(original.body, rebuilt.body)
        self.assertEqual([], reader.find_gaps(repacked))

    def test_size_field_is_recomputed(self):
        mono = reader.read_bytes(fixtures.build_sb_mono(fixtures.SAMPLE_TAGS))
        mono.tags[0].body += b"padding to grow the file"
        packed = writer.pack(mono)
        self.assertEqual(len(packed), reader.read_bytes(packed).header.size)

    def test_checksums_are_carried_through_untouched(self):
        """We cannot compute them (NOTES.md section 6), so we must not invent them."""
        data = fixtures.build_sb_mono(
            fixtures.SAMPLE_TAGS, checksum=b"\xaa\xbb\xcc\xdd",
            header_checksum=b"\x11\x22\x33\x44",
        )
        repacked = reader.read_bytes(writer.round_trip(data))
        self.assertEqual(b"\xaa\xbb\xcc\xdd", repacked.header.checksum)
        self.assertEqual(b"\x11\x22\x33\x44", repacked.header.header_checksum)

    def test_canonical_layout_also_produces_a_readable_container(self):
        """preserve_layout=False is what a freshly built plugin will use."""
        mono = reader.read_bytes(
            fixtures.build_sb_mono(
                fixtures.SAMPLE_TAGS, entrypoints=fixtures.SAMPLE_ENTRYPOINTS
            )
        )
        canonical = reader.read_bytes(writer.pack(mono, preserve_layout=False))
        self.assertEqual([], reader.find_gaps(canonical))
        self.assertEqual(
            [t.body for t in mono.tags], [t.body for t in canonical.tags]
        )

    def test_tfl_containers_reject_entrypoints(self):
        mono = reader.read_bytes(fixtures.build_tfl_mono(fixtures.SAMPLE_TAGS))
        mono.entrypoints = list(fixtures.SAMPLE_ENTRYPOINTS)
        with self.assertRaises(writer.PackError):
            writer.pack(mono)


def _sample_paths():
    """Real plugins to test against, from the environment. Empty if none given."""
    paths = []
    single = os.environ.get("MYTH_SAMPLE_PLUGIN")
    if single:
        paths.append(pathlib.Path(single))
    directory = os.environ.get("MYTH_SAMPLE_DIR")
    if directory:
        for entry in sorted(pathlib.Path(directory).iterdir()):
            if entry.is_file() and not entry.name.startswith("."):
                paths.append(entry)
    return [p for p in paths if p.is_file()]


class TestRealSampleRoundTrip(unittest.TestCase):
    """The gate that actually matters. Skips when no game data is supplied.

    Never commit the sample. These read from paths given at runtime only.
    """

    def test_sample_round_trips(self):
        paths = _sample_paths()
        if not paths:
            self.skipTest(
                "No sample supplied. Set MYTH_SAMPLE_PLUGIN=<file> or "
                "MYTH_SAMPLE_DIR=<dir> to run the real-data gate."
            )
        for path in paths:
            with self.subTest(plugin=path.name):
                data = path.read_bytes()
                try:
                    mono = reader.read_bytes(data, filename=path.name)
                except reader.FormatError as exc:
                    self.skipTest(f"{path.name} is not a monolith: {exc}")
                problems = writer.diagnose_round_trip(data, filename=path.name)
                self.assertEqual(
                    [],
                    problems,
                    f"{path.name} ({mono!r}) did not round-trip:\n  "
                    + "\n  ".join(problems),
                )

    def test_sample_present(self):
        """Fails only when explicitly asked to require real data.

        Set MYTH_REQUIRE_SAMPLE=1 in a run that is meant to be the real gate, so
        a missing sample is an error rather than a silent skip.
        """
        if os.environ.get("MYTH_REQUIRE_SAMPLE") != "1":
            self.skipTest("MYTH_REQUIRE_SAMPLE is not set")
        self.assertTrue(
            _sample_paths(),
            "MYTH_REQUIRE_SAMPLE=1 but no sample found via "
            "MYTH_SAMPLE_PLUGIN / MYTH_SAMPLE_DIR",
        )


if __name__ == "__main__":
    unittest.main()
