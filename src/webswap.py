"""The website's in-browser unit swapper calls this, under Pyodide.

The page (web/swap/) mounts the visitor's own files -- the Civil War maps, its
tagset, and their Myth II folder -- into Pyodide's filesystem without copying
them, asks `scan` what the maps place and which units can stand in, then calls
`build` with the chosen swaps. `build` hands the new plugin back in chunks
(`emit`), so the 500 MB result is never held whole. Nothing leaves the
visitor's computer. This module only shapes the answers for the page; the
swapping itself is `swapstream`, which follows `swap`.
"""

import re

from . import codec, swap, swapstream

# Characters Windows and macOS refuse in a filename.
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MAX_PLUGIN_FILENAME = 32
DEFAULT_NAME = "ZZ Swapped units"


class Problem(Exception):
    """Something the visitor needs to hear about, in plain words."""


def output_name(wanted):
    """The new plugin's filename, which is also its in-game name: what the
    visitor typed without characters a filename can't hold, at most 32 long
    (Myth II does not list a plugin whose filename is longer)."""
    stem = " ".join(_UNSAFE.sub("", wanted or "").split()) or DEFAULT_NAME
    return stem[:MAX_PLUGIN_FILENAME].rstrip()


def _unit_id(text):
    raw = str(text).encode("mac-roman", errors="replace")
    if len(raw) != 4:
        raise Problem(f"{text!r} is not a 4-character unit id.")
    return raw


class _Open:
    """The three inputs, opened lazily, closed together."""

    def __init__(self, maps_path, tagset_paths, myth2_dir):
        if not tagset_paths:
            raise Problem("Choose the tagset the maps use, so their units can be named.")
        self.maps = self.tagset = self.stock = None
        try:
            self.maps = swapstream.LazyContainer(maps_path)
            self.tagset = swapstream.Layered(tagset_paths)
            try:
                stock_paths = swap.stock_archive_paths(myth2_dir)
            except swap.SwapError as exc:
                raise Problem(
                    "Couldn't find Myth II's own game files in that folder. Choose "
                    "your Myth II folder, the one that holds the tags and plugins folders."
                ) from exc
            self.stock = swapstream.Layered(stock_paths)
        except swap.SwapError as exc:
            self.close()
            raise Problem(str(exc)) from exc
        except Exception:
            self.close()
            raise

    def close(self):
        for part in (self.maps, self.tagset, self.stock):
            if part is not None:
                part.close()


def scan(maps_path, tagset_paths, myth2_dir):
    """What the maps place, and every unit that can stand in for one.

    Returns a dict for the page: ``name``, ``maps`` (how many), ``units``
    (``id``, ``name``, ``side``, ``maps``), ``choices`` (``stock`` and
    ``tagset``, each a list of ``id``, ``name``, ``restored``) and ``sides``.
    """
    opened = _Open(maps_path, tagset_paths, myth2_dir)
    try:
        restorer = swapstream.Restorer(opened.tagset, opened.stock)
        tagset, stock = opened.tagset, opened.stock
        unit_names = {
            key[1]: tagset.name(key) for key in tagset.where if key[0] == b"unit"
        }
        used = swapstream.units_used(opened.maps)
        units = []
        for tag_id, use in used.items():
            name = unit_names.get(tag_id) or (
                stock.name((b"unit", tag_id)) if (b"unit", tag_id) in stock else ""
            )
            units.append({
                "id": codec.decode_string(tag_id),
                "name": name,
                "side": swapstream.side_of(name),
                "maps": len(use.maps),
            })
        units.sort(key=lambda u: (-u["maps"], u["id"]))

        stock_units, tagset_units = [], []
        for key in stock.where:
            if key[0] == b"unit":
                stock_units.append({
                    "id": codec.decode_string(key[1]),
                    "name": stock.name(key),
                    "restored": restorer.modified(key),
                })
        for tag_id, name in unit_names.items():
            if (b"unit", tag_id) not in stock:
                tagset_units.append({"id": codec.decode_string(tag_id), "name": name, "restored": False})
        by_name = lambda u: u["name"].lower()
        return {
            "name": opened.maps.path.name,
            "maps": sum(1 for r in opened.maps.records if r.tag_type == b"mesh"),
            "units": units,
            "choices": {"stock": sorted(stock_units, key=by_name), "tagset": sorted(tagset_units, key=by_name)},
            "sides": swapstream.SIDES,
        }
    finally:
        opened.close()


def build(maps_path, tagset_paths, myth2_dir, swaps, out_name, emit):
    """Write the maps with ``swaps`` (``{old id text: new id text}``) applied,
    handing the plugin to ``emit`` in chunks. Returns a dict for the page:
    ``filename``, ``bytes``, ``swapped``, ``slots``, ``maps``, ``restored``."""
    wanted = {}
    for old, new in swaps.items():
        if new and new != old:
            wanted[_unit_id(old)] = _unit_id(new)
    if not wanted:
        raise Problem("Choose at least one unit to replace.")
    filename = output_name(out_name)

    opened = _Open(maps_path, tagset_paths, myth2_dir)
    try:
        patches, changed = swapstream.palette_patches(opened.maps, wanted)
        stock_ids = sorted(new for new in set(wanted.values()) if (b"unit", new) in opened.stock)
        try:
            keys, _unchanged = swapstream.Restorer(opened.tagset, opened.stock).closure(stock_ids)
        except swap.SwapError as exc:
            raise Problem(str(exc)) from exc
        stock = opened.stock
        carry = [
            (stock.header(k), stock.header(k).tag_data_size, lambda k=k: stock.body(k))
            for k in sorted(keys)
        ]
        written, added = swapstream.write_swapped(opened.maps, emit, patches, carry, filename)
        return {
            "filename": filename,
            "bytes": written,
            "swapped": len(wanted),
            "slots": sum(changed.values()),
            "maps": len(changed),
            "restored": added,
        }
    except swap.SwapError as exc:
        raise Problem(str(exc)) from exc
    finally:
        opened.close()
