"""Container and tag-header structure definitions for Myth TFL and Myth II.

Every structure here is ported from jwheare/mythextract ``scripts/myth_headers.py``
@ c747909, cross-checked against the annotated hex dumps in its ``docs/``
directory. Field names are kept identical to mythextract's so the two can be read
side by side.

Sizes are asserted at import time against the constants mythextract declares.
"""

import enum

from . import codec

# --- Sizes (mythextract scripts/myth_headers.py:8-11) ------------------------
GOR_HEADER_SIZE = 64
SB_MONO_HEADER_SIZE = 128
TAG_HEADER_SIZE = 64
ENTRY_TAG_HEADER_SIZE = 112

# --- Magic (mythextract scripts/myth_headers.py:233-234, :291-301) -----------
SB_MONO_SIGNATURE = b"dng2"  # at bytes 124:128 of an SB container
TFL_MONO_MAGIC = b"\x00\x01\x00\x01"  # type=1, version=1 at bytes 0:4 of a .gor
TFL_TAG_SIGNATURE = b"myth"  # at bytes 60:64 of a TFL tag header
SB_TAG_SIGNATURE = b"mth2"  # at bytes 60:64 of an SB tag header

TFL = 1
SB = 2


class ArchiveType(enum.IntEnum):
    """mythextract scripts/myth_headers.py:13-21 (``ArchiveType``)."""

    TAG = 0
    PLUGIN = 1
    PATCH = 2
    FOUNDATION = 3
    CACHE = 4
    INTERFACE = 5
    ADDON = 6
    METASERVER = 7


class PluginFlag(enum.IntFlag):
    """The SB mono header's ``version`` field reinterpreted as flags.

    mythextract scripts/loadtags.py:27-31 (``PluginFlag``). Only meaningful when
    ``type == ArchiveType.PLUGIN``.
    """

    TAGSETS_LAST = 1  # load in reverse order (mesh plugins then tagsets)
    VTFL = 2  # compatibility with vTFL
    URL_PLUGIN = 4  # depends on the plugin named in the description field
    MESH_LAST = 8  # force meshes in this plugin to load last


# --- Myth II monolith header, 128 bytes --------------------------------------
# mythextract scripts/myth_headers.py:71-84 (``SBMonoHeaderFmt``), with the
# annotated layout at :33-70. `description` doubles as a dependency plugin name
# when PluginFlag.URL_PLUGIN is set (scripts/loadtags.py:235-236).
SBMonoHeader = codec.Struct(
    "SBMonoHeader",
    [
        ("h", "type"),  # ArchiveType
        ("H", "version"),  # PluginFlag bits when type == PLUGIN
        ("32s", "name"),
        ("64s", "description"),
        ("H", "entry_tag_count"),  # offset 100
        ("H", "tag_list_count"),  # offset 102
        ("4s", "checksum"),  # algorithm unknown -- see NOTES.md section 6
        ("L", "flags"),
        ("L", "size"),  # total file size in bytes
        ("4s", "header_checksum"),  # algorithm unknown
        ("4x", None),
        ("4s", "signature"),  # b'dng2', offset 124
    ],
)

# --- TFL monolith (.gor) header, 64 bytes ------------------------------------
# mythextract scripts/myth_headers.py:98-110 (``GORHeaderFmt``), annotated at :87-97.
GORHeader = codec.Struct(
    "GORHeader",
    [
        ("H", "type"),
        ("H", "version"),
        ("32s", "name"),
        ("L", "checksum"),
        ("L", "tag_list_offset"),  # explicit, unlike SB where it is derived
        ("H", "tag_list_count"),
        ("H", "header_size"),  # 64
        ("H", "flags"),
        ("2x", None),
        ("L", "mod_time"),
        ("8x", None),
    ],
)

# --- SB entrypoint record, 112 bytes -----------------------------------------
# mythextract scripts/mono2tag.py:80 and :94-99 pack/unpack these as a bare
# '>16s 32s 64s'. Given a name here so it round-trips like everything else.
EntrypointRecord = codec.Struct(
    "EntrypointRecord",
    [
        ("16s", "entry_id"),  # the mesh tag id, NUL-padded
        ("32s", "entry_name"),
        ("64s", "entry_long_name"),  # printable level name
    ],
)

# --- TFL tag header, 64 bytes ------------------------------------------------
# mythextract scripts/myth_headers.py:131-142 (``TFLHeaderFmt``). A real example
# in hex is at the top of mythextract docs/256TagCollectionFormat.txt.
TFLTagHeader = codec.Struct(
    "TFLTagHeader",
    [
        ("32s", "name"),
        ("4s", "tag_type"),
        ("4s", "tag_id"),
        ("L", "version"),
        ("H", "tag_version"),  # dropped by tfl2sb -- see NOTES.md section 2
        ("H", "flags"),  # dropped by tfl2sb
        ("i", "tag_data_offset"),  # absolute file offset inside a monolith
        ("l", "tag_data_size"),  # body length, excluding this 64-byte header
        ("L", "user_data"),
        ("4s", "signature"),  # b'myth'
    ],
)

# --- SB tag header, 64 bytes -------------------------------------------------
# mythextract scripts/myth_headers.py:145-160 (``SBHeaderFmt``). Note this is a
# different field *order* from TFL, not just different fields: SB moves the
# 4-byte identifier/flags/type block to the front and version to the back.
SBTagHeader = codec.Struct(
    "SBTagHeader",
    [
        ("h", "identifier"),
        ("b", "flags"),
        ("b", "type"),  # ArchiveType
        ("32s", "name"),
        ("4s", "tag_type"),
        ("4s", "tag_id"),
        ("i", "tag_data_offset"),
        ("l", "tag_data_size"),
        ("L", "user_data"),
        ("h", "version"),  # int16 here, uint32 in TFL
        ("b", "destination"),
        ("b", "owner_index"),
        ("4s", "signature"),  # b'mth2'
    ],
)

TAG_HEADER_BY_VERSION = {TFL: TFLTagHeader, SB: SBTagHeader}

# Guard against a typo in any of the definitions above silently changing a size.
assert SBMonoHeader.size == SB_MONO_HEADER_SIZE, SBMonoHeader.size
assert GORHeader.size == GOR_HEADER_SIZE, GORHeader.size
assert EntrypointRecord.size == ENTRY_TAG_HEADER_SIZE, EntrypointRecord.size
assert TFLTagHeader.size == TAG_HEADER_SIZE, TFLTagHeader.size
assert SBTagHeader.size == TAG_HEADER_SIZE, SBTagHeader.size
