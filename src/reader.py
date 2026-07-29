"""Read a Myth monolithic tag container (TFL ``.gor`` or Myth II plugin/tagset).

The read path mirrors mythextract ``scripts/mono2tag.py`` and
``scripts/myth_headers.py`` @ c747909:

    header = parse_mono_header(data)          # sniff TFL vs SB, normalise
    entrypoints = get_entrypoints(...)        # SB only
    for tag_header in get_mono_tags(...):     # tag_count records at tag_list_start
        body = data[offset:offset + size]

Container layouts (see NOTES.md section 3):

    SB       [128B header][entrypoints: N x 112][directory: M x 64][bodies ...]
    TFL      [64B header][bodies ...][directory: M x 64 @ tag_list_offset]

A tag's ``tag_data_offset`` inside a container is an **absolute file offset**;
mythextract's ``normalise_tag_header`` rewrites it to 64 only when extracting a
tag to a standalone file, which is not what we are doing here.

Nothing in this module decodes a value lossily -- names and tag IDs stay as raw
bytes -- so a `Monolith` holds everything needed to rebuild the file exactly.
"""

import pathlib
from dataclasses import dataclass, field

from . import codec, formats


class FormatError(ValueError):
    """The data is not a monolith we recognise, or is internally inconsistent."""


@dataclass
class Tag:
    """One tag: its 64-byte directory header plus its body bytes."""

    header: codec.Record
    body: bytes

    @property
    def tag_type(self):
        return self.header.tag_type

    @property
    def tag_id(self):
        return self.header.tag_id

    @property
    def key(self):
        """``(tag_type, tag_id)`` -- how tags are addressed across a load order."""
        return (self.header.tag_type, self.header.tag_id)

    @property
    def name(self):
        """Display-only. Lossy; never re-encode this (see codec.decode_string)."""
        return codec.decode_string(self.header.name)

    @property
    def source_offset(self):
        """Where this tag's body sat in the file it was read from."""
        return self.header.tag_data_offset

    def __repr__(self):
        return (
            f"<Tag {codec.decode_string(self.tag_type)}."
            f"{codec.decode_string(self.tag_id)} {self.name!r} "
            f"{len(self.body)}B>"
        )


@dataclass
class Monolith:
    """A parsed container. Tags are in directory order."""

    game_version: int
    header: codec.Record
    tags: list
    entrypoints: list = field(default_factory=list)
    filename: str = ""
    source: bytes = b""

    @property
    def is_tfl(self):
        return self.game_version == formats.TFL

    @property
    def is_sb(self):
        return self.game_version == formats.SB

    @property
    def name(self):
        """Display-only container name."""
        return codec.decode_string(self.header.name)

    def find(self, tag_type, tag_id):
        """Look up one tag by raw 4-byte type and id. Last match wins, as in
        mythextract's load-order override semantics (scripts/loadtags.py:95-98)."""
        found = None
        for tag in self.tags:
            if tag.header.tag_type == tag_type and tag.header.tag_id == tag_id:
                found = tag
        return found

    def by_type(self, tag_type):
        return [t for t in self.tags if t.header.tag_type == tag_type]

    def tag_types(self):
        """Ordered mapping of raw tag type -> count."""
        counts = {}
        for tag in self.tags:
            counts[tag.header.tag_type] = counts.get(tag.header.tag_type, 0) + 1
        return counts

    def __repr__(self):
        game = "TFL" if self.is_tfl else "SB"
        return (
            f"<Monolith {game} {self.name!r} tags={len(self.tags)} "
            f"entrypoints={len(self.entrypoints)}>"
        )


def detect_game_version(data):
    """Return `formats.TFL` or `formats.SB`, or raise `FormatError`.

    mythextract scripts/myth_headers.py:233-237. The SB check must come first: a
    TFL container is only identified by a weak 4-byte type/version match.
    """
    if len(data) >= formats.SB_MONO_HEADER_SIZE and (
        data[124:128] == formats.SB_MONO_SIGNATURE
    ):
        return formats.SB
    if data[:4] == formats.TFL_MONO_MAGIC:
        return formats.TFL
    raise FormatError(
        "Not a Myth monolith: expected b'dng2' at byte 124 (Myth II) or "
        f"{formats.TFL_MONO_MAGIC!r} at byte 0 (TFL), got "
        f"{data[124:128]!r} and {data[:4]!r}"
    )


def _directory_start(game_version, header):
    """Where the tag directory begins.

    TFL stores it explicitly; SB derives it as header + entrypoint block
    (mythextract scripts/myth_headers.py:251, :263).
    """
    if game_version == formats.TFL:
        return header.tag_list_offset
    return formats.SB_MONO_HEADER_SIZE + header.entry_tag_count * formats.ENTRY_TAG_HEADER_SIZE


def read_bytes(data, filename=""):
    """Parse a container from bytes."""
    data = bytes(data)
    game_version = detect_game_version(data)

    if game_version == formats.TFL:
        header = formats.GORHeader.unpack(data)
        if header.header_size != formats.GOR_HEADER_SIZE:
            raise FormatError(
                f"TFL header_size is {header.header_size}, expected "
                f"{formats.GOR_HEADER_SIZE}"
            )
        entrypoint_count = 0
    else:
        header = formats.SBMonoHeader.unpack(data)
        entrypoint_count = header.entry_tag_count

    entrypoints = formats.EntrypointRecord.unpack_many(
        data, formats.SB_MONO_HEADER_SIZE, entrypoint_count
    )

    tag_count = header.tag_list_count
    directory_start = _directory_start(game_version, header)
    directory_end = directory_start + tag_count * formats.TAG_HEADER_SIZE
    if directory_end > len(data):
        raise FormatError(
            f"Tag directory runs past end of file: {tag_count} tags at "
            f"{directory_start} needs {directory_end} bytes, file is {len(data)}"
        )

    tag_header_struct = formats.TAG_HEADER_BY_VERSION[game_version]
    expected_signature = (
        formats.TFL_TAG_SIGNATURE if game_version == formats.TFL else formats.SB_TAG_SIGNATURE
    )

    tags = []
    for record in tag_header_struct.unpack_many(data, directory_start, tag_count):
        index = len(tags)
        if record.signature != expected_signature:
            raise FormatError(
                f"Tag {index}: signature {record.signature!r}, expected "
                f"{expected_signature!r}. Container and tag versions disagree."
            )
        start = record.tag_data_offset
        end = start + record.tag_data_size
        if record.tag_data_size < 0 or start < 0 or end > len(data):
            raise FormatError(
                f"Tag {index} ({codec.decode_string(record.tag_type)}."
                f"{codec.decode_string(record.tag_id)}) body at [{start}:{end}] "
                f"is outside the file (0..{len(data)})"
            )
        tags.append(Tag(header=record, body=data[start:end]))

    return Monolith(
        game_version=game_version,
        header=header,
        tags=tags,
        entrypoints=entrypoints,
        filename=filename,
        source=data,
    )


def read(path):
    """Parse a container from a file path."""
    path = pathlib.Path(path)
    return read_bytes(path.read_bytes(), filename=path.name)


# --- Layout analysis ---------------------------------------------------------
# The writer lays a container out canonically. If a real file is laid out some
# other way -- padded, reordered, with slack between bodies -- a byte-exact
# round-trip will fail, and this turns that failure into a specific diagnosis
# instead of "8,000,000 bytes differ".


@dataclass
class Region:
    start: int
    end: int
    label: str

    @property
    def size(self):
        return self.end - self.start


def layout(mono):
    """Return the file regions a parsed container accounts for, in file order."""
    regions = []
    if mono.is_tfl:
        regions.append(Region(0, formats.GOR_HEADER_SIZE, "header"))
    else:
        regions.append(Region(0, formats.SB_MONO_HEADER_SIZE, "header"))
        if mono.entrypoints:
            regions.append(
                Region(
                    formats.SB_MONO_HEADER_SIZE,
                    formats.SB_MONO_HEADER_SIZE
                    + len(mono.entrypoints) * formats.ENTRY_TAG_HEADER_SIZE,
                    "entrypoints",
                )
            )

    directory_start = _directory_start(mono.game_version, mono.header)
    regions.append(
        Region(
            directory_start,
            directory_start + len(mono.tags) * formats.TAG_HEADER_SIZE,
            "directory",
        )
    )

    for i, tag in enumerate(mono.tags):
        regions.append(
            Region(
                tag.source_offset,
                tag.source_offset + len(tag.body),
                f"tag[{i}] {codec.decode_string(tag.tag_type)}."
                f"{codec.decode_string(tag.tag_id)}",
            )
        )

    return sorted(regions, key=lambda r: (r.start, r.end))


def find_gaps(mono):
    """Bytes in the source file that no header, directory entry or body covers.

    An empty list means the container is fully accounted for and a canonical
    repack has a chance of being byte-exact. Overlaps are reported with a
    negative size.
    """
    gaps = []
    regions = layout(mono)
    cursor = 0
    for region in regions:
        if region.start != cursor:
            gaps.append(Region(cursor, region.start, f"gap before {region.label}"))
        cursor = max(cursor, region.end)
    if mono.source and cursor != len(mono.source):
        gaps.append(Region(cursor, len(mono.source), "trailing"))
    return gaps
