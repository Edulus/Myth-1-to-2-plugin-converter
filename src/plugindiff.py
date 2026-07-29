"""Compare two Myth containers tag by tag.

Modelled on mythextract ``scripts/plugindiff.py`` @ c747909, which diffs container
headers, entrypoints and tag bodies and prints them in `<`/`>` style. Two
differences, both because this one has to serve conversion work rather than
inspection:

* It returns a structured `DiffResult` and keeps formatting separate, so tests
  and the converter can assert on a diff instead of scraping stdout.
* It compares across game versions. TFL and SB tag headers have different fields
  entirely, so header comparison is limited to what both actually have.

The main use is Phase 2 onward: diff a converted plugin against a known-good
community port of the same content to see what we got wrong.
"""

import hashlib

from . import codec

# Fields present in both TFL and SB tag headers, so a cross-version diff has
# something meaningful to compare (src/formats.py TFLTagHeader / SBTagHeader).
COMMON_TAG_FIELDS = ("name", "tag_type", "tag_id", "tag_data_size", "user_data", "version")


def _digest(data):
    return hashlib.sha256(data).hexdigest()[:12]


def _label(tag):
    return f"{codec.decode_string(tag.tag_type)}.{codec.decode_string(tag.tag_id)}"


class TagDiff:
    """How one tag differs between two containers."""

    def __init__(self, key, left=None, right=None):
        self.key = key
        self.left = left
        self.right = right

    @property
    def status(self):
        if self.left is None:
            return "added"
        if self.right is None:
            return "removed"
        if self.left.body != self.right.body:
            return "changed"
        if self.header_fields():
            return "header-only"
        return "same"

    def header_fields(self):
        """Common header fields whose values differ. Empty if none do."""
        if self.left is None or self.right is None:
            return {}
        changed = {}
        for name in COMMON_TAG_FIELDS:
            a = getattr(self.left.header, name)
            b = getattr(self.right.header, name)
            if a != b:
                changed[name] = (a, b)
        return changed

    @property
    def label(self):
        return _label(self.left if self.left is not None else self.right)


class DiffResult:
    def __init__(self):
        self.header_fields = {}  # field -> (left, right)
        self.entrypoints = []  # (status, entry_id, left_name, right_name)
        self.tags = []  # TagDiff, in a stable order

    @property
    def identical(self):
        return (
            not self.header_fields
            and not self.entrypoints
            and all(t.status == "same" for t in self.tags)
        )

    def changed_tags(self):
        return [t for t in self.tags if t.status != "same"]

    def counts(self):
        counts = {}
        for tag in self.tags:
            counts[tag.status] = counts.get(tag.status, 0) + 1
        return counts


def _diff_headers(left, right):
    """Compare container headers. Only fields both formats have."""
    changed = {}
    if left.game_version != right.game_version:
        changed["game_version"] = (left.game_version, right.game_version)

    shared = set(left.header.field_names) & set(right.header.field_names)
    for name in sorted(shared):
        a = getattr(left.header, name)
        b = getattr(right.header, name)
        if a != b:
            changed[name] = (a, b)
    return changed


def _diff_entrypoints(left, right):
    def index(mono):
        return {e.entry_id: e for e in mono.entrypoints}

    a, b = index(left), index(right)
    result = []
    for entry_id in sorted(set(a) | set(b)):
        in_a, in_b = a.get(entry_id), b.get(entry_id)
        key = codec.decode_string(entry_id)
        if in_a is None:
            result.append(("added", key, None, codec.decode_string(in_b.entry_long_name)))
        elif in_b is None:
            result.append(("removed", key, codec.decode_string(in_a.entry_long_name), None))
        elif in_a.encode() != in_b.encode():
            result.append(
                (
                    "changed",
                    key,
                    codec.decode_string(in_a.entry_long_name),
                    codec.decode_string(in_b.entry_long_name),
                )
            )
    return result


def diff(left, right):
    """Diff two `reader.Monolith` objects. Tags are matched on (type, id)."""
    result = DiffResult()
    result.header_fields = _diff_headers(left, right)
    result.entrypoints = _diff_entrypoints(left, right)

    left_tags = {t.key: t for t in left.tags}
    right_tags = {t.key: t for t in right.tags}

    # Left's order first, then anything only on the right, so a report reads in
    # the order of the container you started from.
    ordered = [t.key for t in left.tags]
    ordered += [k for k in (t.key for t in right.tags) if k not in left_tags]

    seen = set()
    for key in ordered:
        if key in seen:
            continue
        seen.add(key)
        result.tags.append(TagDiff(key, left_tags.get(key), right_tags.get(key)))

    return result


def format_report(result, left_name="<", right_name=">", show_same=False):
    """Render a diff as a list of printable lines."""
    lines = [f"< {left_name}", f"> {right_name}"]

    if result.header_fields:
        lines.append("")
        lines.append("Container header")
        lines.append("-" * 72)
        for name, (a, b) in result.header_fields.items():
            lines.append(f" {name:<20} < {show_value(a):<22} > {show_value(b)}")

    if result.entrypoints:
        lines.append("")
        lines.append("Entrypoints")
        lines.append("-" * 72)
        for status, entry_id, a, b in result.entrypoints:
            lines.append(f" {status:<8} {entry_id:<6} < {str(a):<22} > {b}")

    interesting = result.tags if show_same else result.changed_tags()
    lines.append("")
    lines.append(f"Tags ({_summarise(result.counts())})")
    lines.append("-" * 72)
    for tag in interesting:
        if tag.status == "removed":
            lines.append(f" removed  {tag.label:<12} {_digest(tag.left.body)} {tag.left.name}")
        elif tag.status == "added":
            lines.append(f" added    {tag.label:<12} {_digest(tag.right.body)} {tag.right.name}")
        else:
            lines.append(
                f" {tag.status:<8} {tag.label:<12} "
                f"< {_digest(tag.left.body)} {len(tag.left.body):>8}B  "
                f"> {_digest(tag.right.body)} {len(tag.right.body):>8}B"
            )
            for name, (a, b) in tag.header_fields().items():
                lines.append(f"          {name:<20} < {show_value(a):<22} > {show_value(b)}")

    if not interesting:
        lines.append(" (no differences)")
    return lines


def _summarise(counts):
    if not counts:
        return "none"
    return ", ".join(f"{count} {status}" for status, count in sorted(counts.items()))


def show_value(value):
    if isinstance(value, bytes):
        if codec.all_on(value):
            return f"[FF x {len(value)}]"
        if codec.all_off(value):
            return f"[00 x {len(value)}]"
        try:
            text = codec.decode_string(value)
        except Exception:  # pragma: no cover - decode_string replaces on error
            text = ""
        if text and text.isprintable():
            return repr(text)
        return f"0x{value.hex()}"
    return repr(value)
