"""Convert a TFL tag header into a Myth II tag header.

Ported from mythextract ``myth_headers.tfl2sb`` @ c747909, with its
``normalise_tag_header`` folded in. The field mapping is unchanged; what is added
is honesty about the parts that do not survive.

`tfl2sb` is lossy in three ways, none of which it reports:

* TFL's ``version`` is a uint32, Myth II's is an int16. mythextract assigns it
  straight across, which silently wraps above 32767.
* TFL's ``tag_version`` has no Myth II destination and is dropped.
* TFL's ``flags`` has no Myth II destination and is dropped.

This module performs the same conversion but returns a warning for each lossy
field it actually encounters, so a conversion run can report what it lost rather
than discovering it in-game.
"""

from .. import codec, formats

# mythextract myth_headers.py:162-180 (tfl2sb) and :368-376 (normalise_tag_header)
# zero `identifier`, `type` and `destination` and set `owner_index` to -1. That is
# right for its purpose -- writing a *standalone extracted tag file* -- but two of
# those values are wrong for a tag sitting inside a container. Surveying 35,683 tag
# headers across 211 real Myth II plugins:
#
#   identifier   never 0 in practice (1 occurrence in 35,683). Unique per tag,
#                near-sequential, clustered in a narrow negative int16 range --
#                the signature of an authoring-tool handle counter. So we assign
#                unique sequential values rather than a constant.
#   type         mirrors the *container's* archive type in 194 of 211 plugins;
#                tags inside a PLUGIN are type=PLUGIN, not type=TAG.
#   flags        0 in 35,656 of 35,683. Zeroing it matches practice, which also
#                means dropping TFL's flags costs nothing here.
#   owner_index  -1 in 35,657 of 35,683.
#   destination  varies (0, -1, 3, 2, 1); 0 is the most common by far.
#
# Whether the engine actually reads `identifier` at load time is unknown -- see
# NOTES.md section 6. Matching observed practice is the conservative choice.
SB_DEFAULTS = {
    "flags": 0,
    "destination": 0,
    "owner_index": -1,
}

INT16_MIN, INT16_MAX = -(1 << 15), (1 << 15) - 1


def convert_tag_header(
    tfl_header,
    body_length,
    tag_id=None,
    name=None,
    identifier=1,
    archive_type=formats.ArchiveType.PLUGIN,
):
    """Convert one TFL tag header to Myth II form.

    ``body_length`` sets ``tag_data_size`` from the converted body, since body
    conversion can change the length. ``tag_id`` and ``name`` override the
    originals, which is how ID remapping is applied. ``identifier`` should be
    unique within the container and ``archive_type`` should match it.

    ``tag_data_offset`` is left at zero; the writer assigns real offsets when it
    lays the container out.

    Returns ``(sb_header_record, warnings)``.
    """
    warnings = []

    if not INT16_MIN <= identifier <= INT16_MAX:
        raise ValueError(f"identifier {identifier} does not fit an int16 field")

    version = tfl_header.version
    if not INT16_MIN <= version <= INT16_MAX:
        warnings.append(
            f"version {version} does not fit Myth II's int16 field; clamped to "
            f"{INT16_MAX}"
        )
        version = INT16_MAX

    # These two TFL fields have no Myth II equivalent. Only worth reporting when
    # they actually carry something.
    if tfl_header.tag_version:
        warnings.append(
            f"dropped TFL tag_version={tfl_header.tag_version} (no Myth II field)"
        )
    if tfl_header.flags:
        warnings.append(f"dropped TFL flags={tfl_header.flags} (no Myth II field)")

    header = formats.SBTagHeader.build(
        identifier=identifier,
        type=int(archive_type),
        name=_fit(name if name is not None else tfl_header.name, 32),
        tag_type=tfl_header.tag_type,
        tag_id=tag_id if tag_id is not None else tfl_header.tag_id,
        tag_data_offset=0,
        tag_data_size=body_length,
        user_data=tfl_header.user_data,
        version=version,
        signature=formats.SB_TAG_SIGNATURE,
        **SB_DEFAULTS,
    )
    return header, warnings


def _fit(value, width):
    """NUL-pad or validate a fixed-width byte field."""
    if isinstance(value, str):
        return codec.encode_string(value, width)
    value = bytes(value)
    if len(value) > width:
        raise ValueError(f"{value!r} does not fit in {width} bytes")
    return value.ljust(width, b"\0")


def convert_mono_header(tfl_mono, tag_count, entry_count, name=None, description=b""):
    """Build a Myth II container header for a plugin converted from TFL.

    The two containers share almost nothing (NOTES.md section 3), so most of this
    is synthesised rather than translated:

    * ``type`` becomes ``PLUGIN``. A TFL ``.gor`` is a foundation archive
      (mythextract treats it as ``ArchiveType.FOUNDATION``); what we are building
      is a plugin.
    * ``version`` becomes 0. In a Myth II plugin this field is a `PluginFlag`
      bitfield (load-order and vTFL hints), not a version, so carrying TFL's
      ``version = 1`` across would set ``TAGSETS_LAST`` by accident.
    * ``checksum`` and ``header_checksum`` are zeroed. Nobody has worked out how
      Myth II computes them (NOTES.md section 6) and TFL's single uint32 checksum
      is a different field of a different width. Zero is at least visibly wrong
      rather than plausibly wrong.
    * ``size`` is filled in by the writer, which is the only thing that knows the
      final layout.

    Returns ``(sb_mono_header_record, warnings)``.
    """
    warnings = [
        "container checksum and header_checksum written as zero -- the algorithm "
        "is unknown (NOTES.md section 6)"
    ]
    if entry_count == 0:
        warnings.append(
            "no entrypoints: the plugin will load but expose no playable levels "
            "until mesh conversion can synthesise them"
        )

    header = formats.SBMonoHeader.build(
        type=int(formats.ArchiveType.PLUGIN),
        version=0,
        name=_fit(name if name is not None else tfl_mono.header.name, 32),
        description=_fit(description, 64),
        entry_tag_count=entry_count,
        tag_list_count=tag_count,
        checksum=b"\0\0\0\0",
        flags=0,
        size=0,  # the writer recomputes this
        header_checksum=b"\0\0\0\0",
        signature=formats.SB_MONO_SIGNATURE,
    )
    return header, warnings
