"""Convert a whole TFL container into a Myth II plugin.

Reads a TFL ``.gor``, converts each tag's header and (where a converter exists)
its body, remaps tag IDs, and hands the result to `src.writer` to be packed into
a Myth II container.

What this does **not** do yet is as important as what it does, and the result
reports both:

* **Bodies of unsupported tag types pass through unchanged.** A `mons` body is
  512 bytes in TFL and 1024 in Myth II (NOTES.md section 4); passing one through
  produces a correctly-headed tag with wrong contents. Every such tag is listed
  in the report.
* **Container checksums are written as zero.** The algorithm is unknown, and
  measurement showed it does not matter: Myth II 1.8.5 validates neither field
  (NOTES.md section 11).

Entrypoints *are* synthesised, one per mesh tag, so converted levels appear in
the game's menu -- see `entrypoints`.
"""

from dataclasses import dataclass, field

from .. import codec, formats, idmap as idmap_module, mesh as mesh_module, reader, writer
from . import entrypoints, headers, tags as tag_converters


class ConversionError(ValueError):
    """The input cannot be converted."""


@dataclass
class TagOutcome:
    tag_type: bytes
    tfl_id: bytes
    sb_id: bytes
    name: str
    status: str  # "converted" | "passed-through"
    size_before: int
    size_after: int
    warnings: list = field(default_factory=list)

    @property
    def label(self):
        return f"{codec.decode_string(self.tag_type)}.{codec.decode_string(self.tfl_id)}"

    @property
    def renamed(self):
        return self.tfl_id != self.sb_id


@dataclass
class ConversionReport:
    outcomes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    entrypoints: list = field(default_factory=list)
    unresolved: dict = field(default_factory=dict)
    source_tags: int = 0

    def converted(self):
        return [o for o in self.outcomes if o.status == "converted"]

    def passed_through(self):
        return [o for o in self.outcomes if o.status == "passed-through"]

    def unsupported_types(self):
        """Tag types that were passed through, with counts. The honest summary
        of how far from playable the output is."""
        counts = {}
        for outcome in self.passed_through():
            counts[outcome.tag_type] = counts.get(outcome.tag_type, 0) + 1
        return dict(sorted(counts.items()))

    def renamed(self):
        return [o for o in self.outcomes if o.renamed]

    def tag_warnings(self):
        return [(o, w) for o in self.outcomes for w in o.warnings]


class ConversionContext:
    """Settings the per-tag-type converters may consult."""

    def __init__(self, use_vtfl=False, mesh_defaults=None):
        self.use_vtfl = use_vtfl
        self.mesh_defaults = mesh_defaults or {}


def unresolved_references(mono, id_map=None):
    """Tags the container's mesh headers point at but do not contain.

    Returns ``{(tag_type, tag_id): mesh_count}``. Mesh headers only for now --
    other tag types hold references too (mythextract ``tag2local.py`` is the
    full list) but their bodies are not parsed yet, so this undercounts and
    says so rather than pretending to be complete.
    """
    present = {(t.tag_type, t.tag_id) for t in mono.tags}
    missing = {}
    for tag in mono.by_type(b"mesh"):
        try:
            header = mesh_module.parse_header(tag.body, mono.game_version)
        except ValueError:
            continue
        for tag_type, tag_id, _field in mesh_module.referenced_tags(
            header, mono.game_version
        ):
            # Resolve through the ID map, but key the result on the *original*
            # ID. Keying on the mapped one would rename the thing the user is
            # being asked about, so a later "did they decide this?" lookup could
            # never match -- and the reference would look permanently undecided.
            resolved = id_map.map_id(tag_type, tag_id) if id_map else tag_id
            if (tag_type, resolved) not in present:
                missing[(tag_type, tag_id)] = missing.get((tag_type, tag_id), 0) + 1
    return missing


def convert_container(mono, id_map=None, name=None, description=b"", context=None):
    """Convert a parsed TFL container. Returns ``(sb_monolith, report)``."""
    if not mono.is_tfl:
        raise ConversionError(
            "input is already a Myth II container; nothing to convert"
        )

    id_map = id_map if id_map is not None else idmap_module.default_map()
    context = context if context is not None else ConversionContext()
    report = ConversionReport(source_tags=len(mono.tags))

    if len(mono.tags) > headers.INT16_MAX:
        raise ConversionError(
            f"{len(mono.tags)} tags: cannot assign a unique int16 tag identifier "
            f"to each (max {headers.INT16_MAX})"
        )

    converted_tags = []
    for index, tag in enumerate(mono.tags):
        converter = tag_converters.converter_for(tag.tag_type)

        if converter is not None:
            body, body_warnings = converter.convert(tag.body, context)
            status = "converted"
        else:
            body, body_warnings = tag.body, []
            status = "passed-through"

        mapped = id_map.lookup(tag.tag_type, tag.tag_id)
        sb_id, mapped_name = mapped if mapped else (tag.tag_id, None)

        header, header_warnings = headers.convert_tag_header(
            tag.header,
            len(body),
            tag_id=sb_id,
            name=mapped_name,
            # Unique within the container, and mirroring the container's own
            # archive type -- both matching what real plugins do (see
            # convert/headers.py SB_DEFAULTS).
            identifier=index + 1,
            archive_type=formats.ArchiveType.PLUGIN,
        )
        converted_tags.append(reader.Tag(header=header, body=body))

        report.outcomes.append(
            TagOutcome(
                tag_type=tag.tag_type,
                tfl_id=tag.tag_id,
                sb_id=sb_id,
                name=tag.name,
                status=status,
                size_before=len(tag.body),
                size_after=len(body),
                warnings=body_warnings + header_warnings,
            )
        )

    # Entrypoints have to be built from the mesh tags -- TFL has no equivalent.
    # Done after tag conversion so IDs are already remapped and stli bodies
    # already carry Myth II formatting codes.
    entry_records, entry_warnings = entrypoints.synthesise(
        mono.tags, converted_tags, mono.game_version, id_map=id_map
    )
    report.entrypoints = entry_records
    report.warnings.extend(entry_warnings)

    mono_header, mono_warnings = headers.convert_mono_header(
        mono, tag_count=len(converted_tags), entry_count=len(entry_records),
        name=name, description=description,
    )
    report.warnings.extend(mono_warnings)

    report.unresolved = unresolved_references(mono, id_map=id_map)
    if report.unresolved:
        total = sum(report.unresolved.values())
        report.warnings.append(
            f"{len(report.unresolved)} tags referenced by mesh headers are not in "
            f"this plugin ({total} references). A TFL plugin is not self-contained; "
            f"supply them from a converted TFL tagset, or map them with a decisions "
            f"file (--emit-decisions)"
        )

    unsupported = report.unsupported_types()
    if unsupported:
        listed = ", ".join(
            f"{codec.decode_string(t)}x{n}" for t, n in unsupported.items()
        )
        report.warnings.append(
            f"{len(report.passed_through())} tags of {len(unsupported)} types were "
            f"passed through with unconverted bodies: {listed}"
        )

    sb_mono = reader.Monolith(
        game_version=formats.SB,
        header=mono_header,
        tags=converted_tags,
        entrypoints=entry_records,
        filename=mono.filename,
        source=b"",  # built, not read: there is no source layout to preserve
    )
    return sb_mono, report


# Myth II silently ignores a plugin whose filename is longer than this. Verified
# in-engine: a 33-character file did not appear in the Campaign list at all, and
# appeared immediately when renamed to 20, with no change to its contents. Same
# width as the container's internal `name` field. See NOTES.md section 11.
MAX_PLUGIN_FILENAME = 32


def convert_file(in_path, out_path, id_map=None, name=None, description=b"", context=None):
    """Convert a TFL container file into a Myth II plugin file.

    Returns ``(report, bytes_written)``.
    """
    mono = reader.read(in_path)
    sb_mono, report = convert_container(
        mono, id_map=id_map, name=name, description=description, context=context
    )

    filename = getattr(out_path, "name", str(out_path))
    if len(filename) > MAX_PLUGIN_FILENAME:
        report.warnings.append(
            f"output filename is {len(filename)} characters; Myth II silently "
            f"ignores plugins with filenames over {MAX_PLUGIN_FILENAME}. Rename it "
            f"or the game will not list it at all."
        )
    # A built container has no source layout, so bodies are packed canonically.
    data = writer.pack(sb_mono, preserve_layout=False)

    # Cheap self-check: whatever we just wrote must read back as the same tags.
    verify = reader.read_bytes(data, filename=str(out_path))
    if len(verify.tags) != len(sb_mono.tags):
        raise ConversionError(
            f"wrote {len(sb_mono.tags)} tags but the result reads back as "
            f"{len(verify.tags)}"
        )
    for expected, actual in zip(sb_mono.tags, verify.tags):
        if expected.body != actual.body:
            raise ConversionError(
                f"body of {codec.decode_string(expected.tag_type)}."
                f"{codec.decode_string(expected.tag_id)} did not survive packing"
            )

    with open(out_path, "wb") as out:
        out.write(data)
    return report, len(data)


def format_report(report, in_name="", out_name=""):
    """Render a conversion report as printable lines."""
    lines = []
    if in_name or out_name:
        lines.append(f"in  {in_name}")
        lines.append(f"out {out_name}")
        lines.append("")

    converted = report.converted()
    passed = report.passed_through()
    lines.append(
        f"{report.source_tags} tags: {len(converted)} converted, "
        f"{len(passed)} passed through unchanged"
    )
    lines.append(f"{len(report.entrypoints)} entrypoints synthesised from mesh tags")

    if report.entrypoints:
        lines.append("")
        lines.append("Levels the game will list")
        lines.append("-" * 72)
        for record in report.entrypoints:
            lines.append(
                f" {codec.decode_string(record.entry_id):<6} "
                f"{codec.decode_string(record.entry_long_name)}"
            )

    if converted:
        lines.append("")
        lines.append("Converted")
        lines.append("-" * 72)
        for outcome in converted:
            delta = outcome.size_after - outcome.size_before
            change = f"{delta:+d}B" if delta else "same size"
            rename = (
                f" -> {codec.decode_string(outcome.sb_id)}" if outcome.renamed else ""
            )
            lines.append(
                f" {outcome.label:<12}{rename:<8} {outcome.size_after:>8}B "
                f"{change:<10} {outcome.name}"
            )

    if report.unresolved:
        lines.append("")
        lines.append("Referenced but NOT PRESENT (needs a tagset, or a decisions file)")
        lines.append("-" * 72)
        for (tag_type, tag_id), count in sorted(
            report.unresolved.items(), key=lambda kv: (-kv[1], kv[0])
        )[:20]:
            lines.append(
                f" {codec.decode_string(tag_type)}.{codec.decode_string(tag_id):<6} "
                f"referenced by {count} mesh(es)"
            )
        if len(report.unresolved) > 20:
            lines.append(f" ... and {len(report.unresolved) - 20} more")

    unsupported = report.unsupported_types()
    if unsupported:
        lines.append("")
        lines.append("Passed through with UNCONVERTED bodies")
        lines.append("-" * 72)
        for tag_type, count in unsupported.items():
            lines.append(f" {codec.decode_string(tag_type):<6} {count:>5}")

    tag_warnings = report.tag_warnings()
    if tag_warnings:
        lines.append("")
        lines.append("Per-tag warnings")
        lines.append("-" * 72)
        for outcome, warning in tag_warnings:
            lines.append(f" {outcome.label:<12} {warning}")

    if report.warnings:
        lines.append("")
        lines.append("Warnings")
        lines.append("-" * 72)
        for warning in report.warnings:
            lines.append(f" ! {warning}")

    return lines
