"""Swap the units a Myth II plugin's maps place for other units.

Built for the Civil War plugins, whose maps place custom rank-and-role units
(``@04-SGT-HeavyInfantry``) that some players would rather see as ordinary
units. A map says which unit sits at each marker through its *marker palette*:
every unit marker names a palette slot, and the slot names a unit tag. Pointing
a slot at a different unit tag changes every marker that uses it and nothing
else.

Map actions need no change. Their "monster identifier" parameters were checked
against the Civil War Reloaded 1.8.4 maps (8,323 of them, none holding a unit
tag id): they are 2-byte marker ids, so they follow the markers.

The replacement units are not copied into the output. They have to be in the
load order, normally the tagset the maps came with.
"""

from dataclasses import dataclass, field

from . import codec, formats, mesh, reader, writer


class SwapError(ValueError):
    pass


@dataclass
class UnitUse:
    """One unit tag a plugin's maps place, and where."""

    tag_id: bytes
    maps: list = field(default_factory=list)

    @property
    def key(self):
        return codec.decode_string(self.tag_id)


class _UnitSwapMap:
    """Just enough of an `idmap.IdMap` for `mesh.remap_marker_palette`: maps
    unit ids through ``swaps`` and leaves every other tag type alone."""

    def __init__(self, swaps):
        self.swaps = swaps

    def map_id(self, tag_type, tag_id):
        if tag_type == b"unit":
            return self.swaps.get(tag_id, tag_id)
        return tag_id


def _palette_span(tag, game_version):
    header = mesh.parse_header(tag.body, game_version)
    start = mesh.body_offset(header.marker_palette_offset)
    size = header.marker_palette_size
    return start, size, size // mesh.MARKER_PALETTE_ENTRY_SIZE


def _require_sb(mono):
    if not mono.is_sb:
        raise SwapError("input is not a Myth II container")


def units_used(mono):
    """The unit tags the plugin's maps place, as ``{tag_id: UnitUse}``, in the
    order first met. Unset palette slots are skipped."""
    _require_sb(mono)
    used = {}
    for tag in mono.by_type(b"mesh"):
        start, _size, count = _palette_span(tag, mono.game_version)
        for index in range(count):
            entry = mesh.MarkerPaletteEntry.unpack(
                tag.body, start + index * mesh.MARKER_PALETTE_ENTRY_SIZE
            )
            if entry.type != mesh.MarkerType.UNIT:
                continue
            if codec.all_on(entry.marker_tag) or codec.all_off(entry.marker_tag):
                continue
            use = used.setdefault(entry.marker_tag, UnitUse(entry.marker_tag))
            if tag.name not in use.maps:
                use.maps.append(tag.name)
    return used


def swap_units(mono, swaps, name=None):
    """A copy of ``mono`` whose maps place ``swaps[old_id]`` wherever they placed
    ``old_id``. ``swaps`` maps 4-byte unit ids to 4-byte unit ids.

    Returns ``(new_monolith, changed)`` where ``changed`` counts the palette
    slots rewritten per map name. ``name`` replaces the plugin's internal name;
    give a swapped plugin its own, because two plugins with one name hide each
    other.
    """
    _require_sb(mono)
    for old, new in swaps.items():
        if len(old) != 4 or len(new) != 4:
            raise SwapError(f"unit ids are 4 bytes: {old!r} -> {new!r}")

    id_map = _UnitSwapMap(swaps)
    changed = {}
    tags = []
    for tag in mono.tags:
        if tag.tag_type != b"mesh":
            tags.append(tag)
            continue
        start, size, count = _palette_span(tag, mono.game_version)
        palette = tag.body[start : start + size]
        new_palette, _warnings = mesh.remap_marker_palette(palette, count, id_map)
        if new_palette == palette:
            tags.append(tag)
            continue
        slots = sum(
            1
            for i in range(count)
            if new_palette[i * mesh.MARKER_PALETTE_ENTRY_SIZE : (i + 1) * mesh.MARKER_PALETTE_ENTRY_SIZE]
            != palette[i * mesh.MARKER_PALETTE_ENTRY_SIZE : (i + 1) * mesh.MARKER_PALETTE_ENTRY_SIZE]
        )
        changed[tag.name] = slots
        body = tag.body[:start] + new_palette + tag.body[start + size :]
        tags.append(reader.Tag(header=tag.header, body=body))

    header = mono.header
    if name is not None:
        header = header.replace(name=codec.encode_string(name, 32))
    swapped = reader.Monolith(
        game_version=formats.SB,
        header=header,
        tags=tags,
        entrypoints=mono.entrypoints,
        filename=mono.filename,
        source=mono.source,
    )
    return swapped, changed


def swap_file(in_path, out_path, swaps, name=None):
    """Read a Myth II plugin, swap units, write the result. Returns
    ``(changed_by_map, bytes_written)``."""
    mono = reader.read(in_path)
    swapped, changed = swap_units(mono, swaps, name=name)
    data = writer.pack(swapped, preserve_layout=True)
    with open(out_path, "wb") as out:
        out.write(data)
    return changed, len(data)
