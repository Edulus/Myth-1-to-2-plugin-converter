"""The studio's "swap units" page: choose which units a Myth II plugin's maps place.

A thin layer over `src.swap`. It holds one session -- the maps plugin, the tagset
its units live in, and the Myth II folder -- and offers two actions: describe the
units the maps place, and write a plugin with the chosen swaps applied.
"""

import pathlib

from .. import codec, reader, swap, writer

# Civil War Reloaded names its units by side: ``@`` for the player's, ``+`` for
# the AI's. A label for the page, not something the engine knows.
SIDES = {"@": "Yours (names starting @)", "+": "Enemy (names starting +)"}

MAX_PLUGIN_FILENAME = 32


def _side(name):
    if name[:2] in ("@ ", "+ ") or name[:1] not in SIDES:
        return "other"
    return name[0]


class SwapSession:
    def __init__(self):
        self.maps_path = None
        self.tagset_paths = []
        self.myth2_dir = None
        self._mono = None
        self._unit_names = {}
        self._stock = {}
        self._modified = set()

    # -- describing ---------------------------------------------------------

    def open(self, maps_path, tagset_paths, myth2_dir):
        maps_path = pathlib.Path(maps_path).expanduser()
        tagset_paths = [pathlib.Path(p).expanduser() for p in tagset_paths if str(p).strip()]
        if not tagset_paths:
            raise ValueError("Give the tagset the maps use, so units can be named.")
        mono = reader.read(maps_path)
        if not mono.is_sb:
            raise ValueError(
                f"{maps_path.name} is a Fallen Lords file. Swapping units is for "
                f"Myth II plugins such as the Civil War maps."
            )
        myth2_dir = pathlib.Path(myth2_dir).expanduser()
        stock = swap.tag_index(swap.stock_archive_paths(myth2_dir))
        tagset = swap.tag_index(tagset_paths)

        self.maps_path, self.tagset_paths, self.myth2_dir = maps_path, tagset_paths, myth2_dir
        self._mono = mono
        self._stock = stock
        self._modified = swap.modified_stock_tags(tagset, stock)
        self._unit_names = {
            key[1]: tag.name for key, tag in tagset.items() if key[0] == b"unit"
        }

        used = swap.units_used(mono)
        units = []
        for tag_id, use in used.items():
            name = self._unit_names.get(tag_id) or (
                stock[(b"unit", tag_id)].name if (b"unit", tag_id) in stock else ""
            )
            units.append({
                "id": codec.decode_string(tag_id),
                "name": name,
                "side": _side(name),
                "maps": len(use.maps),
            })
        units.sort(key=lambda u: (-u["maps"], u["id"]))
        return {
            "name": maps_path.name,
            "maps": len(mono.by_type(b"mesh")),
            "units": units,
            "choices": self._choices(),
            "sides": SIDES,
        }

    def _choices(self):
        """Every unit that can stand in: the real base-game units first (restored
        if the tagset redefined them), then the tagset's own."""
        stock_units, tagset_units = [], []
        for key, tag in self._stock.items():
            if key[0] != b"unit":
                continue
            stock_units.append({
                "id": codec.decode_string(key[1]),
                "name": tag.name,
                "restored": key in self._modified,
            })
        for tag_id, name in self._unit_names.items():
            if (b"unit", tag_id) in self._stock:
                continue
            tagset_units.append({"id": codec.decode_string(tag_id), "name": name, "restored": False})
        by_name = lambda u: u["name"].lower()
        return {"stock": sorted(stock_units, key=by_name), "tagset": sorted(tagset_units, key=by_name)}

    # -- writing ------------------------------------------------------------

    def build(self, swaps, out_path, name=None):
        if self._mono is None:
            raise ValueError("Open a maps plugin first.")
        wanted = {}
        for old, new in swaps.items():
            if new and new != old:
                wanted[self._unit_id(old)] = self._unit_id(new)
        if not wanted:
            raise ValueError("Choose at least one unit to replace.")

        out_path = pathlib.Path(out_path).expanduser()
        if out_path == self.maps_path:
            raise ValueError("Write to a new file; the original maps plugin is left alone.")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        swapped, changed = swap.swap_units(self._mono, wanted, name=name or out_path.name)
        stock_ids = [new for new in set(wanted.values()) if (b"unit", new) in self._stock]
        swapped, restored = swap.restore_stock_units(
            swapped, stock_ids, self.tagset_paths, self.myth2_dir
        )
        data = writer.pack(swapped, preserve_layout=not restored["carried"])
        out_path.write_bytes(data)
        return {
            "path": str(out_path),
            "bytes": len(data),
            "swapped": len(wanted),
            "slots": sum(changed.values()),
            "maps": len(changed),
            "restored": restored["carried"],
            "filenameTooLong": len(out_path.name) > MAX_PLUGIN_FILENAME,
            "filenameLength": len(out_path.name),
        }

    @staticmethod
    def _unit_id(text):
        raw = str(text).encode("mac-roman", errors="replace")
        if len(raw) != 4:
            raise ValueError(f"{text!r} is not a 4-character unit id")
        return raw
