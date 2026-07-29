"""Synthesise a Myth II entrypoint block from mesh tags.

A TFL ``.gor`` has no entrypoints at all — the concept does not exist in TFL,
whose levels are found by other means. A Myth II plugin needs one 112-byte
entrypoint record per playable map, or the level never reaches the game's menu.
Nothing can be translated here; it all has to be built.

The rule was measured, not guessed. Across 703 entrypoints in 166 real Myth II
plugins:

* every ``entry_id`` resolves to a ``mesh`` tag in the same container (703/703),
* every ``entry_name`` equals that mesh tag's name exactly (703/703),
* and the entrypoint count equals the mesh count in every plugin (166/166).

So: **one entrypoint per mesh, with the ID and name taken from the mesh tag.**

Only the printable ``entry_long_name`` comes from elsewhere — the first string of
the mesh's ``map_description_string_list_tag`` (the same source
mythextract's ``scripts/fixentrypoints.py`` uses to repair stale names).
Validated by deriving it for every entrypoint in the corpus and comparing against
what the plugin ships: **667 exact matches, no mismatches**, the remainder being
meshes whose description string list lives in another archive.
"""

from .. import codec, formats, mesh as mesh_module
from .tags import text as text_converter

ENTRY_ID_WIDTH = 16
ENTRY_NAME_WIDTH = 32
ENTRY_LONG_NAME_WIDTH = 64


def synthesise(source_tags, converted_tags, game_version, id_map=None):
    """Build entrypoint records for every mesh tag.

    Takes both sides deliberately. Mesh *headers* are read from ``source_tags``,
    still in their original layout, because by this point the mesh converter has
    rewritten the converted bodies into Myth II form -- reading those with the
    TFL layout would be wrong. Everything else comes from ``converted_tags``:
    the remapped tag IDs, and `stli` bodies whose markup has already been
    converted.

    The two lists are parallel: one converted tag per source tag, same order.

    Returns ``(entrypoints, warnings)``.
    """
    warnings = []
    entrypoints = []

    stli_by_id = {t.tag_id: t for t in converted_tags if t.tag_type == b"stli"}

    for source, converted in zip(source_tags, converted_tags):
        if converted.tag_type != b"mesh":
            continue

        long_name, note = _printable_name(
            source, converted, game_version, stli_by_id, id_map
        )
        if note:
            warnings.append(note)

        entrypoints.append(
            formats.EntrypointRecord.build(
                entry_id=_fit(converted.tag_id, ENTRY_ID_WIDTH),
                entry_name=_fit(converted.header.name, ENTRY_NAME_WIDTH),
                entry_long_name=_fit(long_name, ENTRY_LONG_NAME_WIDTH),
            )
        )

    return entrypoints, warnings


def _printable_name(source, converted, game_version, stli_by_id, id_map):
    """The level name Myth II shows in its menus. Returns ``(name, warning)``."""
    label = codec.decode_string(converted.tag_id)
    fallback = converted.header.name.split(b"\0", 1)[0]

    try:
        header = mesh_module.parse_header(source.body, game_version)
    except ValueError as exc:
        return fallback, f"mesh.{label}: {exc}; using the tag name as the level name"

    desc_id = header.map_description_string_list_tag
    if codec.all_on(desc_id) or codec.all_off(desc_id):
        return fallback, f"mesh.{label}: no map description string list; using the tag name"

    if id_map is not None:
        desc_id = id_map.map_id(b"stli", desc_id)

    stli = stli_by_id.get(desc_id)
    if stli is None:
        # Common and not an error: stock meshes point at string lists that live
        # in the game's own archives rather than in the plugin.
        return (
            fallback,
            f"mesh.{label}: description string list stli.{codec.decode_string(desc_id)} "
            f"is not in this container; using the tag name as the level name",
        )

    strings = text_converter.to_strings(stli.body)
    if not strings:
        return fallback, f"mesh.{label}: description string list is empty; using the tag name"

    # to_strings decodes for display; re-encode to the on-disk encoding. The body
    # has already been through the TFL->Myth II formatting conversion, so the
    # markup here is already `|`-style.
    name = codec.encode_string(strings[0])
    if len(name) > ENTRY_LONG_NAME_WIDTH:
        return (
            name[:ENTRY_LONG_NAME_WIDTH],
            f"mesh.{label}: level name is {len(name)} bytes, truncated to "
            f"{ENTRY_LONG_NAME_WIDTH}",
        )
    return name, None


def _fit(value, width):
    if isinstance(value, str):
        value = codec.encode_string(value)
    value = bytes(value)
    # Fixed-width fields are NUL-padded; anything already at width is kept whole.
    return value[:width].ljust(width, b"\0")
