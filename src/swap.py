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

import collections
import pathlib
from dataclasses import dataclass, field

from . import codec, formats, mesh, reader, writer
from .convert import headers as convert_headers


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


# --- Restoring stock units -----------------------------------------------------
#
# A big community tagset can redefine the base game's own unit ids. Civil War
# Reloaded 1.8.4 redefines all 165 of Myth II's, and 87 of them now point at a
# different monster: its `wam1` ("warrior") is a Union veteran, `arch` ("archer")
# a Union sharpshooter. Pointing a map at `wam1` with that tagset loaded gives a
# Civil War soldier, not a warrior (checked in-engine on a clean 1.8.5 install).
#
# To give a map the real unit, the swapped plugin carries the original tags. Only
# the tags the tagset *changed* are carried: anything it left alone still shows
# through from the base game. A plugin loaded after the tagset wins over it.

# The base game's tag archives in the order Myth II layers them, later winning;
# the Unity patches stand in for the "1.8.5 gameplay" the engine reports using.
STOCK_ARCHIVES = (
    "tags/small install",
    "tags/medium install",
    "tags/large install",
    "tags/international small install",
    "tags/international large install",
    "plugins/Patch 1.2",
    "plugins/Patch 1.3",
    "plugins/Patch 1.4",
    "plugins/Patch 1.5",
    "plugins/Patch 1.5 Unity",
    "plugins/Patch 1.8 Interface",
    "plugins/Patch 1.8.5 Maps",
    "plugins/Patch 1.8.5 Unity",
)


def stock_archive_paths(myth2_dir):
    """The base game's archives found in a Myth II folder, in layering order."""
    root = pathlib.Path(myth2_dir)
    found = [root / name for name in STOCK_ARCHIVES if (root / name).is_file()]
    if not found:
        raise SwapError(f"no base-game tag archives found in {myth2_dir}")
    return found


def tag_index(paths):
    """``{(tag_type, tag_id): tag}`` over several archives, later ones winning --
    what Myth II sees once they are all loaded."""
    index = {}
    for path in paths:
        for tag in reader.read(path).tags:
            index[tag.key] = tag
    return index


def modified_stock_tags(tagset_index, stock_index):
    """Keys a tagset redefines with a body different from the base game's."""
    return {
        key
        for key, tag in tagset_index.items()
        if key in stock_index and stock_index[key].body != tag.body
    }


def _referenced(body, by_id):
    """Keys in ``by_id`` whose 4-byte id sits at an even offset in ``body``.

    Tag bodies hold references as bare ids with no type, and a full reference
    walker for every tag type does not exist yet, so this errs on the side of
    carrying too much (an extra stock tag, restored) rather than too little (a
    missing tag fails silently in-engine). ``by_id`` holds only the tags the
    tagset changed, which keeps chance matches rare.
    """
    found = set()
    for offset in range(0, len(body) - 3, 2):
        for key in by_id.get(body[offset : offset + 4], ()):
            found.add(key)
    return found


def restore_closure(unit_ids, stock_index, modified):
    """The stock tags to carry so each unit in ``unit_ids`` is the real one
    again: its own tag plus every changed stock tag it leads to.

    Returns ``(keys, unchanged_units)`` -- ``unchanged_units`` being ids whose
    unit tag the tagset left alone, which need nothing carried.
    """
    by_id = collections.defaultdict(list)
    for key in modified:
        by_id[key[1]].append(key)

    wanted, unchanged, todo = set(), [], []
    for unit_id in unit_ids:
        key = (b"unit", unit_id)
        if key not in stock_index:
            raise SwapError(f"{codec.decode_string(unit_id)!r} is not a base-game unit")
        if key in modified:
            todo.append(key)
        else:
            unchanged.append(unit_id)
    while todo:
        key = todo.pop()
        if key in wanted:
            continue
        wanted.add(key)
        for nxt in _referenced(stock_index[key].body, by_id):
            if nxt not in wanted:
                todo.append(nxt)
    return wanted, unchanged


def add_tags(mono, tags):
    """A copy of ``mono`` with ``tags`` appended. A tag whose key the container
    already holds is skipped: the plugin's own always wins. Returns
    ``(new_monolith, added)``."""
    taken = {tag.key for tag in mono.tags}
    identifier = max((tag.header.identifier for tag in mono.tags), default=0)
    added, tags_out = 0, list(mono.tags)
    for tag in tags:
        if tag.key in taken:
            continue
        identifier += 1
        if identifier > convert_headers.INT16_MAX:
            raise SwapError("too many tags to give each a unique identifier")
        header = tag.header.replace(
            identifier=identifier, type=int(formats.ArchiveType.PLUGIN)
        )
        tags_out.append(reader.Tag(header=header, body=tag.body))
        taken.add(tag.key)
        added += 1
    result = reader.Monolith(
        game_version=mono.game_version,
        header=mono.header,
        tags=tags_out,
        entrypoints=mono.entrypoints,
        filename=mono.filename,
        source=b"",
    )
    return result, added


def restore_stock_units(mono, unit_ids, tagset_paths, myth2_dir):
    """Carry the original stock tags for ``unit_ids`` into ``mono``.

    Returns ``(new_monolith, report)`` where ``report`` has ``carried`` (tag
    count added), ``keys`` and ``unchanged`` (units needing nothing).
    """
    stock = tag_index(stock_archive_paths(myth2_dir))
    tagset = tag_index(tagset_paths)
    modified = modified_stock_tags(tagset, stock)
    keys, unchanged = restore_closure(unit_ids, stock, modified)
    ordered = sorted(keys)
    new_mono, added = add_tags(mono, [stock[k] for k in ordered])
    return new_mono, {"carried": added, "keys": ordered, "unchanged": unchanged}
