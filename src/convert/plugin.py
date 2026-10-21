"""Convert a whole TFL container into a Myth II plugin.

Reads a TFL ``.gor``, converts each tag's header and (where a converter exists)
its body, remaps tag IDs, and hands the result to `src.writer` to be packed into
a Myth II container.

What this does **not** do yet is as important as what it does, and the result
reports both:

* **Bodies of unsupported tag types pass through unchanged.** An `arti` body is
  128 bytes in TFL and 168 in Myth II (NOTES.md section 4); passing one through
  produces a correctly-headed tag with wrong contents. Every such tag is listed
  in the report.
* **Container checksums are written as zero.** The algorithm is unknown, and
  measurement showed it does not matter: Myth II 1.8.5 validates neither field
  (NOTES.md section 11).

Entrypoints *are* synthesised, one per mesh tag, so converted levels appear in
the game's menu -- see `entrypoints`.
"""

import struct
from dataclasses import dataclass, field

from .. import (
    codec,
    formats,
    idmap as idmap_module,
    mesh as mesh_module,
    mons as mons_module,
    reader,
    writer,
)
from . import entrypoints, headers, tags as tag_converters
from .tags import obje as obje_converter


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

    def __init__(self, use_vtfl=False, mesh_defaults=None, id_map=None):
        self.use_vtfl = use_vtfl
        self.mesh_defaults = mesh_defaults or {}
        self.id_map = id_map


def unresolved_references(mono, id_map=None):
    """Tags the container's mesh headers, marker palettes, mons tags, and unit
    tags point at but do not contain.

    Returns ``{(tag_type, tag_id): reference_count}``. Covers mesh header
    fields and marker-palette entries (scenery/unit/model/projectile/ambient
    sound/local-projectile-group/animation references -- see
    `src.mesh.MARKER_TYPE_TO_TAG`), plus every `mons` header's direct
    references, its sound-tag list, its attack projectile tags, and a `unit`
    tag's `mons`/`core` references. Still not the full picture: other tag
    types hold references too (mythextract ``tag2local.py`` is the full list),
    and tag references embedded in map-action parameter data are not walked
    yet -- so this undercounts, and says so, rather than pretending to be
    complete.
    """
    present = {(t.tag_type, t.tag_id) for t in mono.tags}
    missing = {}

    def note(tag_type, tag_id):
        resolved = id_map.map_id(tag_type, tag_id) if id_map else tag_id
        if (tag_type, resolved) not in present:
            missing[(tag_type, tag_id)] = missing.get((tag_type, tag_id), 0) + 1

    for tag in mono.by_type(b"mesh"):
        try:
            header = mesh_module.parse_header(tag.body, mono.game_version)
        except ValueError:
            continue

        # Resolve through the ID map, but key the result on the *original* ID.
        # Keying on the mapped one would rename the thing the user is being
        # asked about, so a later "did they decide this?" lookup could never
        # match -- and the reference would look permanently undecided.
        for tag_type, tag_id, _field in mesh_module.referenced_tags(
            header, mono.game_version
        ):
            note(tag_type, tag_id)

        if not header.marker_palette_entries:
            continue
        trailing = tag.body[mesh_module.MESH_HEADER_SIZE :]
        start = header.marker_palette_offset
        end = start + header.marker_palette_size
        try:
            entries = mesh_module.MarkerPaletteEntry.unpack_many(
                trailing[start:end], 0, header.marker_palette_entries
            )
        except (struct.error, ValueError):
            continue
        for entry in entries:
            try:
                marker_type = mesh_module.MarkerType(entry.type)
            except ValueError:
                continue
            tag_type = mesh_module.MARKER_TYPE_TO_TAG.get(marker_type)
            if tag_type is None:
                continue
            if codec.all_on(entry.marker_tag) or codec.all_off(entry.marker_tag):
                continue
            note(tag_type, entry.marker_tag)

    for tag in mono.by_type(b"mons"):
        try:
            header = mons_module.parse_header(tag.body, mono.game_version)
        except ValueError:
            continue

        for tag_type, tag_id, _field in mons_module.referenced_tags(header):
            note(tag_type, tag_id)

        for sound_tag in mons_module.sound_tag_refs(header.sound_tags):
            note(b"soun", sound_tag)

        for projectile_tag in mons_module.attack_projectile_refs(
            header.attacks, mono.game_version, header.number_of_attacks
        ):
            note(b"proj", projectile_tag)

    for tag in mono.by_type(b"unit"):
        try:
            header = mons_module.UnitTag.unpack(tag.body)
        except ValueError:
            continue
        for tag_type, tag_id in ((b"mons", header.mons), (b"core", header.core)):
            if codec.all_on(tag_id) or codec.all_off(tag_id):
                continue
            note(tag_type, tag_id)

    return missing


def convert_container(mono, id_map=None, name=None, description=b"", context=None):
    """Convert a parsed TFL container. Returns ``(sb_monolith, report)``."""
    if not mono.is_tfl:
        raise ConversionError(
            "input is already a Myth II container; nothing to convert"
        )

    id_map = id_map if id_map is not None else idmap_module.default_map()
    context = context if context is not None else ConversionContext()
    # A single source of truth: whatever id_map this call resolved to is what
    # per-tag-type converters see too, regardless of what a caller-supplied
    # context happened to be constructed with.
    context.id_map = id_map
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

    _give_monsters_objects(mono, converted_tags, report)

    if len(converted_tags) > headers.INT16_MAX:
        raise ConversionError(
            f"{len(converted_tags)} tags: cannot assign a unique int16 tag "
            f"identifier to each (max {headers.INT16_MAX})"
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
            f"{len(report.unresolved)} referenced tags are not in this plugin "
            f"({total} references). A TFL plugin is not self-contained; "
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


# TFL fields the mons converter reports as dropped, which _give_monsters_objects
# carries into each monster's own object instead.
_CARRIED_TO_OBJECT = (
    "object_scale_lower_bound",
    "object_scale_delta",
    "maximum_vitality",
    "effect_modifiers",
)


def _give_monsters_objects(mono, converted_tags, report):
    """Give every converted monster an object of its own.

    TFL keeps a monster's scale, vitality and damage-type modifiers on the
    monster and shares one physics-only object between them all; Myth II reads
    those from the object (see `tags.obje`). Each monster gets an object built
    from its TFL header, under the monster's own ID, and its ``object_tag`` is
    pointed at it. Physics come from the object the monster named, when that is
    in this container, and from the stock "basic object" otherwise.
    """
    taken = {t.tag_id for t in converted_tags if t.tag_type == b"obje"}
    tfl_objects = {t.tag_id: t.body for t in mono.tags if t.tag_type == b"obje"}
    object_tag_at = next(
        start for _fmt, name, start, _end in mons_module.SBMonsHeader._layout if name == "object_tag"
    )

    for index, source in enumerate(mono.tags):
        if source.tag_type != b"mons":
            continue
        converted = converted_tags[index]
        try:
            tfl = mons_module.TFLMonsHeader.unpack(source.body)
        except (ValueError, struct.error):
            continue
        if len(converted.body) < object_tag_at + 4:
            continue

        object_id = _free_id(converted.tag_id, taken)
        taken.add(object_id)
        physics = (
            obje_converter.physics_of(tfl_objects[tfl.object_tag])
            if len(tfl_objects.get(tfl.object_tag, b"")) == obje_converter.TFL_SIZE
            else obje_converter.BASIC_OBJECT_PHYSICS
        )
        body = obje_converter.for_monster(tfl, physics)
        name = f"{codec.decode_string(converted.header.name)} object"[:31]
        header = converted.header.replace(
            tag_type=b"obje",
            tag_id=object_id,
            name=codec.encode_string(name, 32),
            identifier=len(converted_tags) + 1,
            tag_data_size=len(body),
        )
        converted_tags.append(reader.Tag(header=header, body=body))

        mons_body = bytearray(converted.body)
        mons_body[object_tag_at : object_tag_at + 4] = object_id
        converted_tags[index] = reader.Tag(header=converted.header, body=bytes(mons_body))

        outcome = report.outcomes[index]
        outcome.warnings = [
            w for w in outcome.warnings
            if not any(f"field {field}=" in w for field in _CARRIED_TO_OBJECT)
        ]
        report.outcomes.append(
            TagOutcome(
                tag_type=b"obje",
                tfl_id=object_id,
                sb_id=object_id,
                name=name,
                status="converted",
                size_before=0,
                size_after=len(body),
                warnings=[
                    f"built for mons.{codec.decode_string(converted.tag_id)} from its "
                    f"TFL scale, vitality and effect modifiers"
                ],
            )
        )


def _free_id(wanted, taken):
    """``wanted``, or a variant of it no tag of the type already uses."""
    if wanted not in taken:
        return wanted
    for ch in b"0123456789#$%&@!":
        candidate = wanted[:3] + bytes([ch])
        if candidate not in taken:
            return candidate
    raise ConversionError(f"no free obje id near {codec.decode_string(wanted)}")


# Myth II silently ignores a plugin whose filename is longer than this. Verified
# in-engine: a 33-character file did not appear in the Campaign list at all, and
# appeared immediately when renamed to 20, with no change to its contents. Same
# width as the container's internal `name` field. See NOTES.md section 11.
MAX_PLUGIN_FILENAME = 32


def convert_file(in_path, out_path, id_map=None, name=None, description=b"", context=None):
    """Convert a TFL container file into a Myth II plugin file.

    Returns ``(report, bytes_written)``. ``name`` -- the name Myth II identifies
    the plugin by -- defaults to the output file's name, as `convert_tagset`'s
    does: defaulting to the *source* file's name let two plugins converted from
    one source hide each other in-engine.
    """
    mono = reader.read(in_path)
    name = name or getattr(out_path, "name", None) or None
    sb_mono, report = convert_container(
        mono, id_map=id_map, name=name, description=description, context=context
    )
    return report, _write_plugin(sb_mono, out_path, report)


def convert_tagset(in_paths, out_path, name=None, id_map=None, context=None):
    """Convert one or more TFL tag archives into a single Myth II tagset.

    A TFL plugin leans on the stock TFL tags the way a Myth II plugin leans on
    the base game; converting those stock tags -- an install's ``TAGS.GOR``
    and ``ARTSOUND.GOR`` -- into a tagset is what lets a converted plugin load
    (NOTES.md section 18). Where several archives carry the same tag, the first
    one given wins, so list them most-authoritative first.

    The result has no entrypoints -- Myth II only offers entrypoint-free plugins
    as tagsets -- and carries ``name`` in its header, which is what Myth II
    identifies a plugin by: two plugins with one internal name hide each other.
    ``name`` defaults to the output file's name.

    Returns ``(report, bytes_written, duplicates)``, where ``duplicates`` counts,
    per later archive, the tags skipped because an earlier one had them.
    """
    if not in_paths:
        raise ConversionError("no input archives given")
    monos = [reader.read(path) for path in in_paths]
    for path, mono in zip(in_paths, monos):
        if not mono.is_tfl:
            raise ConversionError(f"{path} is not a TFL archive")

    seen, merged, duplicates = set(), [], {}
    for path, mono in zip(in_paths, monos):
        for tag in mono.tags:
            key = (tag.tag_type, tag.tag_id)
            if key in seen:
                duplicates[str(path)] = duplicates.get(str(path), 0) + 1
                continue
            seen.add(key)
            merged.append(tag)

    combined = reader.Monolith(
        game_version=monos[0].game_version,
        header=monos[0].header,
        tags=merged,
        entrypoints=[],
        filename=str(in_paths[0]),
        source=b"",
    )
    name = name or getattr(out_path, "name", str(out_path))
    sb_mono, report = convert_container(combined, id_map=id_map, name=name, context=context)

    # Entrypoints would make it a campaign, which cannot load alongside one.
    sb_mono.entrypoints = []
    sb_mono.header = sb_mono.header.replace(entry_tag_count=0)
    report.entrypoints = []
    return report, _write_plugin(sb_mono, out_path, report), duplicates


def _write_plugin(sb_mono, out_path, report):
    """Pack, check it reads back, and write. Returns the bytes written."""
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
    return len(data)


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
                f"referenced {count} time(s)"
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
