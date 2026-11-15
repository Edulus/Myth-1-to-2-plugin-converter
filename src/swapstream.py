"""Swap units, reading and writing in pieces instead of holding whole plugins.

`swap` reads each container whole. The Civil War Reloaded 1.8.4 maps are 518 MB,
its tagset 174 MB, Myth II's own archives another 500, and the swapped plugin is
as big as the maps again: far too much for a browser tab. This module does the
same job touching only what it needs.

* A `LazyContainer` reads a file's header, entrypoints and directory (a few
  hundred kilobytes) and fetches a tag's body from the file only when asked.
* A swapped plugin is the maps plugin with each map's marker palette patched in
  place (same size) and, when original units are restored, a few base-game tags
  added. The tag directory sits *before* the bodies in a Myth II container, so
  adding K tags moves every body by K x 64 bytes and nothing else. The output is
  streamed: header, entrypoints, directory, the source's body region copied in
  chunks with the palette patches laid over it, then the added bodies.

Nothing here decides *what* to swap or restore; that is `swap`'s logic, followed
step for step (the tests compare the two on the same inputs).
"""

import collections
import pathlib

from . import codec, formats, mesh, reader, swap
from .convert import headers as convert_headers

CHUNK = 8 << 20

# Civil War Reloaded names its units by side: ``@`` for the player's, ``+`` for
# the AI's. A label for the page, not something the engine knows.
SIDES = {"@": "Yours (names starting @)", "+": "Enemy (names starting +)"}


def side_of(name):
    if name[:2] in ("@ ", "+ ") or name[:1] not in SIDES:
        return "other"
    return name[0]


class LazyContainer:
    """A Myth II container opened for reading. The directory is in memory;
    bodies are read from the file when asked for."""

    def __init__(self, path):
        self.path = pathlib.Path(path)
        self._file = open(self.path, "rb")
        try:
            self._parse()
        except Exception:
            self._file.close()
            raise

    def _parse(self):
        f = self._file
        head = f.read(formats.SB_MONO_HEADER_SIZE)
        try:
            version = reader.detect_game_version(head)
        except reader.FormatError as exc:
            raise swap.SwapError(f"{self.path.name} is not a Myth plugin") from exc
        if version != formats.SB:
            raise swap.SwapError(
                f"{self.path.name} is a Fallen Lords file. Swapping units is for "
                "Myth II plugins such as the Civil War maps."
            )
        self.header = formats.SBMonoHeader.unpack(head)
        entry_size = self.header.entry_tag_count * formats.ENTRY_TAG_HEADER_SIZE
        self.entrypoint_bytes = f.read(entry_size)
        self.entrypoints = formats.EntrypointRecord.unpack_many(
            self.entrypoint_bytes, 0, self.header.entry_tag_count
        )
        count = self.header.tag_list_count
        directory = f.read(count * formats.TAG_HEADER_SIZE)
        if len(directory) != count * formats.TAG_HEADER_SIZE:
            raise swap.SwapError(f"{self.path.name}: the tag directory runs past the end of the file")
        self.records = formats.SBTagHeader.unpack_many(directory, 0, count)
        self.directory_start = formats.SB_MONO_HEADER_SIZE + entry_size
        f.seek(0, 2)
        self.size = f.tell()
        for i, rec in enumerate(self.records):
            end = rec.tag_data_offset + rec.tag_data_size
            if rec.tag_data_size < 0 or rec.tag_data_offset < 0 or end > self.size:
                raise swap.SwapError(f"{self.path.name}: tag {i} lies outside the file")
        self.index = {(r.tag_type, r.tag_id): i for i, r in enumerate(self.records)}

    @property
    def data_start(self):
        """Where the bodies begin: straight after the directory."""
        return self.directory_start + len(self.records) * formats.TAG_HEADER_SIZE

    def body(self, i):
        rec = self.records[i]
        self._file.seek(rec.tag_data_offset)
        data = self._file.read(rec.tag_data_size)
        if len(data) != rec.tag_data_size:
            raise swap.SwapError(f"{self.path.name}: could not read tag {i}")
        return data

    def tag(self, i):
        return reader.Tag(header=self.records[i], body=self.body(i))

    def read_range(self, start, end):
        self._file.seek(start)
        return self._file.read(end - start)

    def close(self):
        self._file.close()


class Layered:
    """Several containers as Myth II sees them once loaded in order: for a tag
    in more than one, the last wins. Directories only; bodies on demand."""

    def __init__(self, paths):
        self.containers = []
        try:
            for path in paths:
                self.containers.append(LazyContainer(path))
        except Exception:
            self.close()
            raise
        self.where = {}
        for container in self.containers:
            for key, i in container.index.items():
                self.where[key] = (container, i)

    def __contains__(self, key):
        return key in self.where

    def header(self, key):
        container, i = self.where[key]
        return container.records[i]

    def body(self, key):
        container, i = self.where[key]
        return container.body(i)

    def name(self, key):
        return codec.decode_string(self.header(key).name)

    def close(self):
        for container in self.containers:
            container.close()


def units_used(maps):
    """`swap.units_used` for a `LazyContainer`: ``{tag_id: UnitUse}`` in the
    order first met."""
    used = {}
    for i, rec in enumerate(maps.records):
        if rec.tag_type != b"mesh":
            continue
        tag = maps.tag(i)
        start, _size, count = swap._palette_span(tag, formats.SB)
        for index in range(count):
            entry = mesh.MarkerPaletteEntry.unpack(
                tag.body, start + index * mesh.MARKER_PALETTE_ENTRY_SIZE
            )
            if entry.type != mesh.MarkerType.UNIT:
                continue
            if codec.all_on(entry.marker_tag) or codec.all_off(entry.marker_tag):
                continue
            use = used.setdefault(entry.marker_tag, swap.UnitUse(entry.marker_tag))
            if tag.name not in use.maps:
                use.maps.append(tag.name)
    return used


def palette_patches(maps, swaps):
    """The in-place edits that make the maps place ``swaps[old]`` where they
    placed ``old``: ``(patches, changed)``, patches being ``(file offset, new
    palette bytes)`` and ``changed`` the palette slots rewritten per map name."""
    for old, new in swaps.items():
        if len(old) != 4 or len(new) != 4:
            raise swap.SwapError(f"unit ids are 4 bytes: {old!r} -> {new!r}")
    id_map = swap._UnitSwapMap(swaps)
    entry = mesh.MARKER_PALETTE_ENTRY_SIZE
    patches, changed = [], {}
    for i, rec in enumerate(maps.records):
        if rec.tag_type != b"mesh":
            continue
        tag = maps.tag(i)
        start, size, count = swap._palette_span(tag, formats.SB)
        palette = tag.body[start : start + size]
        new_palette, _warnings = mesh.remap_marker_palette(palette, count, id_map)
        if new_palette == palette:
            continue
        if len(new_palette) != len(palette):
            raise swap.SwapError(f"map {tag.name!r}: the palette changed size")
        changed[tag.name] = sum(
            1
            for s in range(count)
            if new_palette[s * entry : (s + 1) * entry] != palette[s * entry : (s + 1) * entry]
        )
        patches.append((rec.tag_data_offset + start, new_palette))
    return patches, changed


class Restorer:
    """`swap.restore_stock_units`, reading bodies only as needed.

    ``tagset`` and ``stock`` are `Layered`. A key counts as *modified* when the
    tagset redefines it with a body different from the base game's; each
    answer is worked out once, from the two bodies, the first time it is asked.
    """

    def __init__(self, tagset, stock):
        self.tagset, self.stock = tagset, stock
        self._modified = {}
        self._by_id = collections.defaultdict(list)
        for key in tagset.where:
            if key in stock.where:
                self._by_id[key[1]].append(key)

    def modified(self, key):
        if key not in self._modified:
            if key not in self.tagset or key not in self.stock:
                self._modified[key] = False
            else:
                a, b = self.tagset.header(key), self.stock.header(key)
                self._modified[key] = (
                    a.tag_data_size != b.tag_data_size
                    or self.tagset.body(key) != self.stock.body(key)
                )
        return self._modified[key]

    def _referenced(self, body):
        """`swap._referenced`, over the keys the tagset really changed."""
        found = set()
        for offset in range(0, len(body) - 3, 2):
            for key in self._by_id.get(body[offset : offset + 4], ()):
                if self.modified(key):
                    found.add(key)
        return found

    def closure(self, unit_ids):
        """`swap.restore_closure`: ``(keys, unchanged_units)``."""
        wanted, unchanged, todo = set(), [], []
        for unit_id in unit_ids:
            key = (b"unit", unit_id)
            if key not in self.stock:
                raise swap.SwapError(f"{codec.decode_string(unit_id)!r} is not a base-game unit")
            if self.modified(key):
                todo.append(key)
            else:
                unchanged.append(unit_id)
        while todo:
            key = todo.pop()
            if key in wanted:
                continue
            wanted.add(key)
            for nxt in self._referenced(self.stock.body(key)):
                if nxt not in wanted:
                    todo.append(nxt)
        return wanted, unchanged


def _stream_region(container, start, end, patches, emit):
    """Copy ``container``'s bytes ``[start, end)`` to ``emit`` in chunks, with
    each ``(offset, bytes)`` patch laid over them."""
    patches = sorted(patches)
    first = 0  # patches before this index end before the current chunk
    pos = start
    while pos < end:
        stop = min(pos + CHUNK, end)
        chunk = bytearray(container.read_range(pos, stop))
        if len(chunk) != stop - pos:
            raise swap.SwapError("the maps plugin ended unexpectedly")
        while first < len(patches) and patches[first][0] + len(patches[first][1]) <= pos:
            first += 1
        for offset, data in patches[first:]:
            if offset >= stop:
                break
            lo, hi = max(offset, pos), min(offset + len(data), stop)
            chunk[lo - pos : hi - pos] = data[lo - offset : hi - offset]
        emit(bytes(chunk))
        pos = stop


def write_swapped(maps, emit, patches=(), carry=(), name=None):
    """Write the maps plugin with ``patches`` applied and ``carry`` added.

    ``carry`` is a list of ``(directory record, body size, read_body)`` for
    tags to add; a tag whose key the plugin already holds is skipped (the
    plugin's own always wins, as in `swap.add_tags`). ``emit`` is called with
    successive chunks of the output. Returns ``(bytes_written, tags_added)``.
    """
    taken = set(maps.index)
    added = []
    identifier = max((r.identifier for r in maps.records), default=0)
    for record, size, read_body in carry:
        key = (record.tag_type, record.tag_id)
        if key in taken:
            continue
        identifier += 1
        if identifier > convert_headers.INT16_MAX:
            raise swap.SwapError("too many tags to give each a unique identifier")
        taken.add(key)
        added.append((record.replace(identifier=identifier, type=int(formats.ArchiveType.PLUGIN)), size, read_body))

    delta = len(added) * formats.TAG_HEADER_SIZE
    data_start, data_end = maps.data_start, maps.size
    cursor = data_start + delta + (data_end - data_start)
    directory = bytearray()
    for rec in maps.records:
        directory += rec.replace(tag_data_offset=rec.tag_data_offset + delta).encode()
    for record, size, _read in added:
        directory += record.replace(tag_data_offset=cursor, tag_data_size=size).encode()
        cursor += size
    total = cursor

    header = maps.header.replace(
        entry_tag_count=len(maps.entrypoints),
        tag_list_count=len(maps.records) + len(added),
        size=total,
    )
    if name is not None:
        header = header.replace(name=codec.encode_string(name, 32))

    written = 0

    def out(data):
        nonlocal written
        written += len(data)
        emit(data)

    out(header.encode())
    out(maps.entrypoint_bytes)
    out(bytes(directory))
    _stream_region(maps, data_start, data_end, patches, out)
    for _record, size, read_body in added:
        body = read_body()
        if len(body) != size:
            raise swap.SwapError("a carried tag changed size while it was being read")
        out(body)
    if written != total:
        raise swap.SwapError(f"wrote {written} bytes but computed a total size of {total}")
    return written, len(added)
