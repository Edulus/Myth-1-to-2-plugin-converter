"""Compare tags with a reference port, byte offset by byte offset.

Every format fix so far came from the same hand-made method: pair a stock TFL
tag with the tag of the same type and id in a reference (Project Magma's Myth II
port, or Myth II's own stock tags), and read which bytes differ systematically.
This module is that method as a command (``python -m src compare``):

* Tags are paired across the two sides by ``(type, id)``; with ``by_name``,
  tags still unpaired are then paired by ``(type, name)``. Within a side the
  first container that has a key wins.
* Per tag type it counts pairs, same-size pairs, byte-identical pairs and size
  changes, and for the same-size pairs finds the byte offsets that differ in at
  least ``threshold`` of them. Those offsets are merged into ranges, named by
  field where the Myth II layout is declared (`FIELD_LAYOUTS`), and given the
  most common ``ours -> ref`` value transitions.

Like `plugindiff`, it returns a structured `CompareResult` and formats it
separately, so tests can assert on the structure.

Ranges are written ``start-end`` with the end exclusive (``20-36`` is bytes 20
to 35), the convention used in documentation/notes/stock-tags.md section 33.
"""

import collections
import csv
import re
import struct

from . import codec

DEFAULT_THRESHOLD = 0.6
TOP_TRANSITIONS = 3
# Offsets that pass the threshold are merged into one range when at most this
# many bytes separate them, so a run of 16-bit fields whose low bytes change
# (lpgr's 62, 64, ... 76) reads as one range rather than eight.
MERGE_GAP = 1
# Transition values longer than this many bytes are shown truncated.
SHOW_BYTES = 32

_NONZERO_RUN = re.compile(rb"[^\x00]+")


# --- Field names ---------------------------------------------------------------
# Tag type -> a function returning [(start, end, name)] in the Myth II layout.
# Functions, not lists, so a converter module is imported only when its type is
# actually being compared. To name another type, add an entry here.


def struct_fields(struct_def, base=0):
    """``[(start, end, name)]`` for each named field of a `codec.Struct`."""
    fields = []
    offset = base
    for fmt, name in struct_def.fields:
        size = struct.calcsize(f">{fmt}")
        if name is not None:
            fields.append((offset, offset + size, name))
        offset += size
    return fields


def _mons_fields():
    from . import mons

    return struct_fields(mons.SBMonsHeader)


def _geom_fields():
    from .convert.tags import geom

    return struct_fields(geom.SBGeom)


def _mode_fields():
    from .convert.tags import mode

    return struct_fields(mode.Model)


def _amso_fields():
    from .convert.tags import amso

    return [
        (amso.SOUND_TAGS_AT + 4 * slot, amso.SOUND_TAGS_AT + 4 * slot + 4, f"sound_tags[{slot}]")
        for slot in range(amso.SOUND_SLOTS)
    ]


FIELD_LAYOUTS = {
    b"amso": _amso_fields,
    b"geom": _geom_fields,
    b"mode": _mode_fields,
    b"mons": _mons_fields,
}


def field_names(tag_type, start, end, layouts=None):
    """Names of the declared fields overlapping ``[start, end)``, in order."""
    layouts = FIELD_LAYOUTS if layouts is None else layouts
    build = layouts.get(tag_type)
    if build is None:
        return []
    return [name for s, e, name in build() if s < end and start < e]


# --- Result objects --------------------------------------------------------------


class DiffRange:
    """A run of byte offsets that differ in at least the threshold of pairs."""

    def __init__(self, start, end, peak, differing_bytes):
        self.start = start
        self.end = end  # exclusive
        self.peak = peak  # most pairs differing at any one offset in the range
        self.differing_bytes = differing_bytes  # offsets in the range over threshold
        self.fields = []
        self.covering = 0  # same-size pairs long enough to hold the whole range
        self.transitions = []  # [((ours_bytes, ref_bytes), count)], most common first

    @property
    def label(self):
        if self.end - self.start == 1:
            return str(self.start)
        return f"{self.start}-{self.end}"

    def __repr__(self):
        return f"<DiffRange {self.label} peak={self.peak}>"


class TypeStats:
    """Everything measured for one tag type."""

    def __init__(self, tag_type):
        self.tag_type = tag_type
        self.pairs = 0
        self.by_name = 0  # of `pairs`, how many were paired by name
        self.same_size = 0
        self.identical = 0
        self.size_changes = collections.Counter()  # (ours_size, ref_size) -> count
        self.ours_only = 0
        self.ref_only = 0
        self.ranges = []

    @property
    def label(self):
        return codec.decode_string(self.tag_type)


class CompareResult:
    def __init__(self, threshold):
        self.threshold = threshold
        self.types = {}  # raw tag type -> TypeStats, sorted by type

    def get(self, tag_type):
        if isinstance(tag_type, str):
            tag_type = codec.encode_string(tag_type)
        return self.types.get(tag_type)


# --- Pairing ---------------------------------------------------------------------


def _side(monoliths, types):
    """``{(type, id): tag}`` for one side; the first container with a key wins."""
    found = {}
    for mono in monoliths:
        for tag in mono.tags:
            if types is not None and tag.tag_type not in types:
                continue
            found.setdefault(tag.key, tag)
    return found


def pair_tags(ours, ref, types=None, by_name=False):
    """Pair tags across two lists of `reader.Monolith`.

    Returns ``(pairs, ours_only, ref_only)``: ``pairs`` is a list of
    ``(ours_tag, ref_tag, how)`` with ``how`` either ``"id"`` or ``"name"``.
    """
    a = _side(ours, types)
    b = _side(ref, types)
    pairs = [(a[key], b[key], "id") for key in a if key in b]
    ours_left = [tag for key, tag in a.items() if key not in b]
    ref_left = {key: tag for key, tag in b.items() if key not in a}

    if by_name and ours_left and ref_left:
        by_type_name = {}
        for key, tag in ref_left.items():
            by_type_name.setdefault((tag.tag_type, tag.header.name), key)
        unmatched = []
        for tag in ours_left:
            key = by_type_name.pop((tag.tag_type, tag.header.name), None)
            if key is None:
                unmatched.append(tag)
            else:
                pairs.append((tag, ref_left.pop(key), "name"))
        ours_left = unmatched

    return pairs, ours_left, list(ref_left.values())


# --- Measuring -------------------------------------------------------------------


def _xor(a, b):
    n = len(a)
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(n, "big")


def _systematic_ranges(diff_runs, same_size, threshold):
    """Ranges where at least ``threshold`` of ``same_size`` pairs differ.

    ``diff_runs`` is a list of ``(start, end)`` runs of differing bytes, one list
    entry per run per pair. A sweep over run boundaries gives the count at every
    offset without visiting each byte, so a large body costs only its runs.
    """
    if not same_size or not diff_runs:
        return []
    need = threshold * same_size
    events = collections.Counter()
    for start, end in diff_runs:
        events[start] += 1
        events[end] -= 1

    spans = []  # (start, end, count) where count passes the threshold
    count = 0
    points = sorted(events)
    for here, nxt in zip(points, points[1:]):
        count += events[here]
        if count >= need and count > 0:
            spans.append((here, nxt, count))

    ranges = []
    for start, end, count in spans:
        last = ranges[-1] if ranges else None
        if last is not None and start - last.end <= MERGE_GAP:
            last.end = end
            last.peak = max(last.peak, count)
            last.differing_bytes += end - start
        else:
            ranges.append(DiffRange(start, end, count, end - start))
    return ranges


def _transitions(rng, same_pairs):
    counts = collections.Counter()
    for a, b in same_pairs:
        if len(a) >= rng.end:
            counts[(a[rng.start : rng.end], b[rng.start : rng.end])] += 1
    rng.covering = sum(counts.values())
    rng.transitions = counts.most_common(TOP_TRANSITIONS)


def compare(ours, ref, types=None, threshold=DEFAULT_THRESHOLD, by_name=False):
    """Compare lists of `reader.Monolith` (ours against the reference).

    ``types`` is an optional collection of raw 4-byte tag types to limit to.
    """
    types = set(types) if types else None
    pairs, ours_only, ref_only = pair_tags(ours, ref, types, by_name)
    result = CompareResult(threshold)

    def stats(tag_type):
        found = result.types.get(tag_type)
        if found is None:
            found = result.types[tag_type] = TypeStats(tag_type)
        return found

    same_bodies = collections.defaultdict(list)  # type -> same-size [(ours, ref)]
    runs = collections.defaultdict(list)  # type -> [(start, end)]
    for a, b, how in pairs:
        s = stats(a.tag_type)
        s.pairs += 1
        if how == "name":
            s.by_name += 1
        if len(a.body) != len(b.body):
            s.size_changes[(len(a.body), len(b.body))] += 1
            continue
        s.same_size += 1
        same_bodies[a.tag_type].append((a.body, b.body))
        if a.body == b.body:
            s.identical += 1
            continue
        runs[a.tag_type].extend(m.span() for m in _NONZERO_RUN.finditer(_xor(a.body, b.body)))

    for tag in ours_only:
        stats(tag.tag_type).ours_only += 1
    for tag in ref_only:
        stats(tag.tag_type).ref_only += 1

    for tag_type, s in result.types.items():
        s.ranges = _systematic_ranges(runs.get(tag_type, []), s.same_size, threshold)
        for rng in s.ranges:
            rng.fields = field_names(tag_type, rng.start, rng.end)
            _transitions(rng, same_bodies[tag_type])

    result.types = dict(sorted(result.types.items()))
    return result


# --- Formatting ------------------------------------------------------------------


def show_bytes(value):
    """Hex, truncated past `SHOW_BYTES` bytes."""
    if len(value) > SHOW_BYTES:
        return value[:SHOW_BYTES].hex() + f"..(+{len(value) - SHOW_BYTES})"
    return value.hex()


def show_fields(names, limit=3):
    if not names:
        return ""
    if len(names) > limit:
        return ", ".join(names[: limit - 1]) + f", ... {names[-1]} ({len(names)} fields)"
    return ", ".join(names)


def _size_changes(s, limit=1):
    parts = [f"{a}->{b} x{n}" for (a, b), n in s.size_changes.most_common(limit)]
    rest = sum(s.size_changes.values()) - sum(n for _, n in s.size_changes.most_common(limit))
    if rest:
        parts.append(f"+{rest} more")
    return ", ".join(parts) or "-"


def _range_summary(s, limit=4):
    if not s.ranges:
        return "none" if s.same_size > s.identical else "-"
    shown = ", ".join(r.label for r in s.ranges[:limit])
    if len(s.ranges) > limit:
        shown += f" (+{len(s.ranges) - limit} more)"
    return shown


def _detail_lines(s):
    lines = [f"{s.label}  ({s.same_size} same-size pairs, {s.identical} identical)"]
    for rng in s.ranges:
        head = f"  {rng.label:<10} differs in {rng.peak}/{s.same_size}"
        if rng.differing_bytes != rng.end - rng.start:
            head += f" ({rng.differing_bytes} of {rng.end - rng.start} bytes)"
        if rng.fields:
            head += f"  [{show_fields(rng.fields)}]"
        lines.append(head)
        for (a, b), n in rng.transitions:
            lines.append(f"      {show_bytes(a)} -> {show_bytes(b)}  {n}/{rng.covering}")
    return lines


# Show every type's detail when the whole detail section is at most this long.
AUTO_DETAIL_LINES = 60


def format_report(result, ours_names=(), ref_names=(), detail=None):
    """Render a comparison as printable lines.

    ``detail`` is a collection of raw tag types to show range by range; when it
    is None, every type is shown if the detail section is short.
    """
    lines = [f"ours: {name}" for name in ours_names]
    lines += [f"ref:  {name}" for name in ref_names]
    lines.append(
        f"Offsets differing in at least {result.threshold:.0%} of same-size pairs; "
        "ranges are start-end, end exclusive."
    )
    lines.append("")
    lines.append(
        f"{'type':<6}{'pairs':>6}{'same':>6}{'ident':>6}{'ours':>6}{'ref':>6}  "
        f"{'size changes':<28}  systematic ranges"
    )
    lines.append("-" * 96)
    for s in result.types.values():
        pairs = f"{s.pairs}" + ("*" if s.by_name else "")
        lines.append(
            f"{s.label:<6}{pairs:>6}{s.same_size:>6}{s.identical:>6}"
            f"{s.ours_only:>6}{s.ref_only:>6}  {_size_changes(s):<28}  {_range_summary(s)}"
        )
    if not result.types:
        lines.append(" (no tags)")
    if any(s.by_name for s in result.types.values()):
        lines.append("* some pairs matched by name")
    lines.append(
        "same = same-size pairs, ident = byte-identical, ours/ref = tags with no partner"
    )

    with_ranges = [s for s in result.types.values() if s.ranges]
    if detail is None:
        blocks = [_detail_lines(s) for s in with_ranges]
        if sum(len(b) + 1 for b in blocks) > AUTO_DETAIL_LINES:
            blocks = []
            if with_ranges:
                lines.append("")
                lines.append("(use --detail TYPE for the ranges and their values)")
    else:
        blocks = [_detail_lines(s) for s in with_ranges if s.tag_type in detail]
    for block in blocks:
        lines.append("")
        lines.extend(block)
    return lines


CSV_COLUMNS = (
    "type", "start", "end", "fields", "differing_pairs", "same_size_pairs",
    "fraction", "pairs", "identical", "top_ours", "top_ref", "top_count",
    "covering_pairs",
)


def write_csv(result, path):
    """One row per (type, range), with the counts and the top transition."""
    with open(path, "w", newline="", encoding="ascii", errors="replace") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for s in result.types.values():
            for rng in s.ranges:
                (a, b), n = rng.transitions[0] if rng.transitions else ((b"", b""), 0)
                writer.writerow([
                    s.label, rng.start, rng.end, "; ".join(rng.fields), rng.peak,
                    s.same_size, f"{rng.peak / s.same_size:.3f}", s.pairs, s.identical,
                    a.hex(), b.hex(), n, rng.covering,
                ])


def parse_types(text):
    """``"amso,lpgr"`` -> ``{b"amso", b"lpgr"}``."""
    if not text:
        return None
    return {codec.encode_string(t.strip()) for t in text.split(",") if t.strip()}
