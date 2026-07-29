"""Synthetic Myth containers, built by hand for tests.

These are assembled with raw ``struct.pack`` calls straight from the layouts
documented in NOTES.md section 3, **deliberately not** using ``src.writer``. If
they were built by the writer, a round-trip test would only prove the writer is
self-consistent. Built independently, it proves reader and writer agree with the
format.

What a synthetic fixture cannot prove is that our *understanding* of the format
matches what Bungie actually shipped -- only a real plugin does that, which is
why `tests/test_roundtrip.py` also looks for one and says so loudly when it is
absent.

No copyrighted game data is used or reproduced here. Tag names and IDs are
invented.
"""

import struct

SB_MONO_HEADER_SIZE = 128
GOR_HEADER_SIZE = 64
TAG_HEADER_SIZE = 64
ENTRY_TAG_HEADER_SIZE = 112

# Non-zero filler for "unused" padding regions. Real Myth tags carry junk in
# these, and a reader that zero-fills them will fail a byte-exact round-trip --
# so the fixtures make sure that failure would be caught.
PAD4 = b"\xde\xad\xbe\xef"
PAD2 = b"\x13\x37"
PAD8 = b"\xca\xfe\xba\xbe\x00\x11\x22\x33"


def _fixed(text, width):
    """NUL-pad a byte string to a fixed width."""
    if len(text) > width:
        raise ValueError(f"{text!r} does not fit in {width} bytes")
    return text.ljust(width, b"\0")


def sb_tag_header(name, tag_type, tag_id, offset, size, version=1, user_data=0):
    """Myth II 64-byte tag header (src/formats.py SBTagHeader)."""
    return struct.pack(
        ">h b b 32s 4s 4s i l L h b b 4s",
        0,  # identifier
        0,  # flags
        0,  # type (ArchiveType.TAG)
        _fixed(name, 32),
        tag_type,
        tag_id,
        offset,
        size,
        user_data,
        version,
        0,  # destination
        -1,  # owner_index
        b"mth2",
    )


def tfl_tag_header(name, tag_type, tag_id, offset, size, version=1, tag_version=0, flags=0):
    """TFL 64-byte tag header (src/formats.py TFLTagHeader)."""
    return struct.pack(
        ">32s 4s 4s L H H i l L 4s",
        _fixed(name, 32),
        tag_type,
        tag_id,
        version,
        tag_version,
        flags,
        offset,
        size,
        0,  # user_data
        b"myth",
    )


def entrypoint(entry_id, name, long_name):
    """Myth II 112-byte entrypoint record (mythextract mono2tag.py:80)."""
    return struct.pack(
        ">16s 32s 64s", _fixed(entry_id, 16), _fixed(name, 32), _fixed(long_name, 64)
    )


def build_sb_mono(
    tags,
    entrypoints=(),
    name=b"test plugin",
    description=b"",
    archive_type=1,  # ArchiveType.PLUGIN
    version=0,
    flags=0,
    checksum=b"\x01\x02\x03\x04",
    header_checksum=b"\x05\x06\x07\x08",
    alias_bodies=False,
    body_gap=0,
):
    """Assemble a Myth II container.

    ``tags`` is a list of ``(name, tag_type, tag_id, body)``. With
    ``alias_bodies``, every directory entry points at the *first* tag's body --
    the deduplication real containers use, which the writer has to preserve.
    ``body_gap`` inserts unaccounted padding before the first body, as real
    containers do (see ``build_tfl_mono``).

    Layout: [128B header][entrypoints][directory][gap][bodies]
    """
    entry_block = b"".join(entrypoints)
    directory_start = SB_MONO_HEADER_SIZE + len(entry_block)
    first_body = directory_start + len(tags) * TAG_HEADER_SIZE + body_gap

    directory = b""
    bodies = b""
    cursor = first_body
    for tag_name, tag_type, tag_id, body in tags:
        if alias_bodies:
            offset, size = first_body, len(tags[0][3])
        else:
            offset, size = cursor, len(body)
            bodies += body
            cursor += len(body)
        directory += sb_tag_header(tag_name, tag_type, tag_id, offset, size)

    if alias_bodies:
        bodies = tags[0][3]

    bodies = bytes(body_gap) + bodies
    total_size = first_body - body_gap + len(bodies)

    header = struct.pack(
        ">h H 32s 64s H H 4s L L 4s",
        archive_type,
        version,
        _fixed(name, 32),
        _fixed(description, 64),
        len(entrypoints),
        len(tags),
        checksum,
        flags,
        total_size,
        header_checksum,
    ) + PAD4 + b"dng2"

    assert len(header) == SB_MONO_HEADER_SIZE, len(header)
    data = header + entry_block + directory + bodies
    assert len(data) == total_size, (len(data), total_size)
    return data


def build_tfl_mono(
    tags, name=b"test.gor", checksum=0x1234ABCD, flags=0, mod_time=0, body_gap=64
):
    """Assemble a TFL ``.gor`` container.

    Layout: [64B header][gap][bodies][directory @ tag_list_offset]

    ``body_gap`` defaults to 64 because that is what the first real plugin
    tested against does: it declares ``header_size = 64`` and then starts its
    first body at 128, with 64 unaccounted zero bytes in between. The reader and
    writer must carry those through rather than assume bodies begin at the end
    of the header.
    """
    bodies = bytes(body_gap)
    cursor = GOR_HEADER_SIZE + body_gap
    directory = b""
    for tag_name, tag_type, tag_id, body in tags:
        directory += tfl_tag_header(tag_name, tag_type, tag_id, cursor, len(body))
        bodies += body
        cursor += len(body)

    tag_list_offset = GOR_HEADER_SIZE + len(bodies)

    header = (
        struct.pack(
            ">H H 32s L L H H H",
            1,  # type
            1,  # version
            _fixed(name, 32),
            checksum,
            tag_list_offset,
            len(tags),
            GOR_HEADER_SIZE,
            flags,
        )
        + PAD2
        + struct.pack(">L", mod_time)
        + PAD8
    )

    assert len(header) == GOR_HEADER_SIZE, len(header)
    return header + bodies + directory


# --- Mesh bodies -------------------------------------------------------------
# A mesh header is 1024 bytes. Rather than lay all ~100 fields out by hand, these
# fixtures write zeros and poke the few fields the entrypoint tests care about at
# hardcoded offsets. The offsets below are stated here independently of
# ``src/mesh.py`` so the two cross-check each other -- ``test_mesh.py`` asserts
# they agree. Both layouts happen to place these three fields identically; where
# TFL and Myth II diverge is further into the struct.
MESH_HEADER_SIZE = 1024
MESH_OFFSET_FLAGS = 76
MESH_OFFSET_MAP_DESCRIPTION_STLI = 140
MESH_OFFSET_PREGAME_STORYLINE = 176

MESH_FLAG_SINGLE_PLAYER_MAP = 1 << 16


def mesh_body(description_tag=b"\xff\xff\xff\xff", storyline_tag=b"\xff\xff\xff\xff",
              flags=0, trailing=b""):
    """A minimal mesh tag body: a 1024-byte header plus optional trailing data."""
    body = bytearray(MESH_HEADER_SIZE)
    body[MESH_OFFSET_FLAGS : MESH_OFFSET_FLAGS + 4] = struct.pack(">L", flags)
    body[MESH_OFFSET_MAP_DESCRIPTION_STLI : MESH_OFFSET_MAP_DESCRIPTION_STLI + 4] = (
        description_tag
    )
    body[MESH_OFFSET_PREGAME_STORYLINE : MESH_OFFSET_PREGAME_STORYLINE + 4] = storyline_tag
    return bytes(body) + trailing


# A TFL container holding one solo mesh, its description string list, and its
# narration text -- the smallest thing that exercises entrypoint synthesis.
MESH_TAGS = [
    (b"301 crows bridge", b"mesh", b"30cb",
     mesh_body(description_tag=b"30cc", storyline_tag=b"30tx",
               flags=MESH_FLAG_SINGLE_PLAYER_MAP)),
    (b"301 description", b"stli", b"30cc", b"The Siege of \\bCrow's Bridge\\p\0Second line\0"),
    (b"301 storyline", b"text", b"30tx", b"They came at dawn.\r\rWe held."),
]


# A small, varied set of tags reused across tests. Bodies are deliberately odd
# lengths, and one is empty, to catch off-by-one offset arithmetic.
SAMPLE_TAGS = [
    (b"test text", b"text", b"tst1", b"Hello from a text tag.\r\rSecond paragraph."),
    (b"test string list", b"stli", b"tst2", b"first\0second\0third\0"),
    (b"empty body", b"scri", b"tst3", b""),
    (b"binary-ish", b"mons", b"tst4", bytes(range(256)) * 3 + b"\x7f"),
    (b"one byte", b"soun", b"tst5", b"\xff"),
]

SAMPLE_ENTRYPOINTS = [
    entrypoint(b"tst1", b"01 test level", b"The First Test Level"),
    entrypoint(b"tst2", b"02 another", b"Another |bTest|p Level"),
]
