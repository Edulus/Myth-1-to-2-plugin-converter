"""Serialise a `reader.Monolith` back into a Myth monolithic container.

**This is the piece mythextract does not have.** Every write path in
jwheare/mythextract @ c747909 produces either a loose extracted tag, a derived
media file, or an in-place byte splice of an existing container
(``scripts/fixentrypoints.py`` via ``mono2tag.encode_entrypoints``, which reuses
the original directory and bodies verbatim and recomputes no offsets). Nothing
there rebuilds a directory. See NOTES.md section 5.

Layouts produced (NOTES.md section 3):

    SB       [128B header][entrypoints: N x 112][directory: M x 64][bodies ...]
    TFL      [64B header][bodies ...][directory: M x 64 @ tag_list_offset]

Two things this deliberately does **not** do:

* **Checksums are carried through untouched.** The SB header's ``checksum`` and
  ``header_checksum`` are 4 bytes each and nothing in mythextract computes
  either; the algorithm is unknown. Preserving the source values is what makes a
  byte-exact round-trip possible. It also turns out to be sufficient: Myth II
  1.8.5 validates neither field, so a repacked plugin whose checksums no longer
  match its contents loads and plays normally (verified in-engine, NOTES.md
  section 11). Nothing here needs to compute them.

* **Bodies are written verbatim.** Offsets *inside* a tag body are relative to
  the body, not the file (verified in NOTES.md section 3), so moving a tag within
  the container does not require rewriting its interior.
"""

from . import formats, reader


class PackError(ValueError):
    """The structure cannot be serialised into a valid container."""


def _plan_bodies(mono, first_body_offset, preserve_layout):
    """Lay out the body region. Returns ``(offsets_by_tag_index, body_bytes)``.

    With ``preserve_layout``, three properties of the source file are carried
    through, all of which real containers rely on and none of which are visible
    to an extractor:

    * **Order.** Bodies keep their source file order, not directory order.
    * **Aliasing.** Several directory entries may point at one body -- how
      containers deduplicate. Expanding those into copies produces a valid but
      larger, non-byte-exact file.
    * **Gaps.** Bytes between bodies that no structure accounts for. The first
      real plugin tested had 64 zero bytes between its header (which declares
      ``header_size = 64``) and its first body at 128. Rather than guess whether
      that alignment is universal, unaccounted bytes are copied verbatim and
      travel with the body that follows them.

    Without ``preserve_layout``, bodies are packed contiguously in directory
    order and gaps are dropped -- what a freshly built plugin wants.
    """
    tags = mono.tags
    segments = []
    offsets = {}
    cursor = first_body_offset

    if not preserve_layout:
        for i, tag in enumerate(tags):
            offsets[i] = cursor
            segments.append(tag.body)
            cursor += len(tag.body)
        return offsets, b"".join(segments)

    # Stable, so tags sharing an offset keep their directory order -- which
    # matters when a zero-length body precedes a real one at that offset.
    order = sorted(range(len(tags)), key=lambda i: tags[i].source_offset)

    have_source = bool(mono.source)
    if have_source:
        source_start, source_end = reader.data_region(mono)
        source_end = min(source_end, len(mono.source))
    else:
        source_start = source_end = 0
    source_cursor = source_start

    by_source = {}  # (source offset, source length) -> (assigned offset, body)
    for i in order:
        tag = tags[i]
        # Key on length as well as offset. A zero-length body sits at the same
        # offset as whatever follows it without being an alias of it, so keying
        # on offset alone would collapse the two and drop the real body. Use the
        # length recorded in the source directory, not the current body length,
        # so a caller that replaced a body does not change what counts as an
        # alias.
        source_size = tag.header.tag_data_size
        source_key = (tag.source_offset, source_size)
        alias = by_source.get(source_key)
        # Only share an offset when the bodies really are identical -- two tags
        # that aliased in the source may have been converted differently since.
        if tag.body and alias is not None and alias[1] == tag.body:
            offsets[i] = alias[0]
            continue

        if have_source and tag.source_offset > source_cursor:
            gap = mono.source[source_cursor : tag.source_offset]
            segments.append(gap)
            cursor += len(gap)

        offsets[i] = cursor
        by_source.setdefault(source_key, (cursor, tag.body))
        segments.append(tag.body)
        cursor += len(tag.body)
        # Advance by the tag's extent *in the source*, so that shrinking or
        # growing a body does not turn part of the old body into a fake gap.
        source_cursor = max(source_cursor, tag.source_offset + source_size)

    # Any padding between the last body and the directory (TFL) or end of
    # file (SB).
    if have_source and source_end > source_cursor:
        trailing = mono.source[source_cursor:source_end]
        segments.append(trailing)
        cursor += len(trailing)

    return offsets, b"".join(segments)


def pack(mono, preserve_layout=True):
    """Serialise ``mono`` to bytes.

    ``preserve_layout=True`` reproduces the source file's body ordering, which is
    what the Phase 1 round-trip gate requires. Set it False to lay bodies out in
    directory order, which is what a freshly built plugin wants.
    """
    if mono.game_version not in (formats.TFL, formats.SB):
        raise PackError(f"Unknown game version {mono.game_version!r}")

    tag_count = len(mono.tags)
    if tag_count > 0xFFFF:
        raise PackError(f"{tag_count} tags exceeds the uint16 tag_list_count field")

    tag_header_struct = formats.TAG_HEADER_BY_VERSION[mono.game_version]
    directory_size = tag_count * formats.TAG_HEADER_SIZE

    if mono.game_version == formats.SB:
        entry_count = len(mono.entrypoints)
        if entry_count > 0xFFFF:
            raise PackError(
                f"{entry_count} entrypoints exceeds the uint16 entry_tag_count field"
            )
        entry_size = entry_count * formats.ENTRY_TAG_HEADER_SIZE
        directory_start = formats.SB_MONO_HEADER_SIZE + entry_size
        first_body_offset = directory_start + directory_size
    else:
        if mono.entrypoints:
            raise PackError(
                "TFL containers have no entrypoint block "
                f"(got {len(mono.entrypoints)} entrypoints)"
            )
        entry_size = 0
        # TFL puts the directory at the end, after the bodies.
        first_body_offset = formats.GOR_HEADER_SIZE

    offsets, bodies = _plan_bodies(mono, first_body_offset, preserve_layout)
    body_end = first_body_offset + len(bodies)

    if mono.game_version == formats.SB:
        total_size = body_end
    else:
        directory_start = body_end
        total_size = directory_start + directory_size

    # Rebuild the directory with real offsets and sizes.
    directory = bytearray()
    for i, tag in enumerate(mono.tags):
        header = tag.header.replace(
            tag_data_offset=offsets[i],
            tag_data_size=len(tag.body),
        )
        encoded = header.encode()
        if len(encoded) != formats.TAG_HEADER_SIZE:
            raise PackError(
                f"Tag {i} header encoded to {len(encoded)} bytes, expected "
                f"{formats.TAG_HEADER_SIZE}"
            )
        directory += encoded

    # Rebuild the container header. Counts and total size are recomputed;
    # checksums are carried through (see module docstring).
    if mono.game_version == formats.SB:
        header = mono.header.replace(
            entry_tag_count=len(mono.entrypoints),
            tag_list_count=tag_count,
            size=total_size,
        )
    else:
        header = mono.header.replace(
            tag_list_count=tag_count,
            tag_list_offset=directory_start,
            header_size=formats.GOR_HEADER_SIZE,
        )

    entrypoints = b"".join(record.encode() for record in mono.entrypoints)
    if len(entrypoints) != entry_size:
        raise PackError(
            f"Entrypoint block encoded to {len(entrypoints)} bytes, expected {entry_size}"
        )

    if mono.game_version == formats.SB:
        out = header.encode() + entrypoints + bytes(directory) + bodies
    else:
        out = header.encode() + bodies + bytes(directory)

    if len(out) != total_size:
        raise PackError(
            f"Packed {len(out)} bytes but computed a total size of {total_size}"
        )
    return out


def write(mono, path, preserve_layout=True):
    """Pack ``mono`` and write it to ``path``. Returns the bytes written."""
    data = pack(mono, preserve_layout=preserve_layout)
    with open(path, "wb") as out:
        out.write(data)
    return data


def round_trip(data, filename=""):
    """Read ``data`` and pack it straight back. Returns the repacked bytes.

    The Phase 1 correctness gate: for a container we fully understand, this is
    the identity function.
    """
    return pack(reader.read_bytes(data, filename=filename), preserve_layout=True)


def diagnose_round_trip(data, filename=""):
    """Explain why a round-trip is not byte-exact. Returns a list of strings.

    Empty list means the round-trip reproduced the input exactly.
    """
    mono = reader.read_bytes(data, filename=filename)
    repacked = pack(mono, preserve_layout=True)
    if repacked == data:
        return []

    problems = []

    # Unaccounted or overlapping bytes in the source are the usual cause: the
    # canonical repack has no way to reproduce padding or slack it cannot see.
    # (Overlap on its own is normal -- containers alias deduplicated bodies, and
    # a zero-length body shares an offset with whatever follows it -- so this is
    # only reported once we already know the round-trip failed.)
    for gap in reader.find_gaps(mono):
        if gap.size < 0:
            problems.append(
                f"overlap of {-gap.size} bytes at [{gap.end}:{gap.start}] ({gap.label})"
            )
        else:
            problems.append(
                f"{gap.size} unaccounted bytes at [{gap.start}:{gap.end}] ({gap.label})"
            )

    if len(repacked) != len(data):
        problems.append(f"size changed: {len(data)} in, {len(repacked)} out")

    limit = min(len(repacked), len(data))
    differing = [i for i in range(limit) if repacked[i] != data[i]]
    if differing:
        first, last = differing[0], differing[-1]
        problems.append(
            f"{len(differing)} bytes differ, first at {first} "
            f"(in={data[first]:#04x} out={repacked[first]:#04x}), last at {last}"
        )
        problems.append(f"  first difference falls in: {_locate(mono, first)}")

    return problems


def _locate(mono, offset):
    """Name the region a file offset falls in, for diagnostics."""
    for region in reader.layout(mono):
        if region.start <= offset < region.end:
            return f"{region.label} [{region.start}:{region.end}] +{offset - region.start}"
    return f"no known region contains offset {offset}"
