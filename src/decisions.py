"""The human-in-the-loop decisions file.

Most of this converter has right answers, verified against real data. Three
things do not, and no amount of measurement will settle them:

1. **Which Myth II tag stands in for a TFL tag that has no equivalent.**
   `meli.deml` is referenced by 59 meshes in the test plugin and exists nowhere
   in Myth II. The install ships 25 mesh-lighting tags -- "grassland",
   "carnage", "long desert shadows", "moonshadow". Which one belongs on a given
   level is an aesthetic judgement by someone who knows the level.

2. **Which synthesised values to accept.** `ceiling_height` was 2048 in all 40
   meshes of the reference port, and the Fear manual says it is ignored unless
   the mesh's "Has Ceiling" flag is set, so it is doubly safe. `transition_point`
   was the mode of only 32 of 40, and the manual defines it as the global
   lighting zero point -- a per-map artistic choice about how bright the whole
   map looks. That is a coin-flip dressed as a default. The tool should say
   which is which and let a human override either.

3. **Strategy** -- vTFL compatibility on or off, what to call the plugin.

So the tool writes a file listing every decision it could not make, with its own
guess and the evidence behind it. A human edits it. `convert` reads it back.

A file beats a GUI here: decisions become durable, diffable, reviewable, and
shareable between people converting different plugins -- none of which a
click-through interface gives you.

TOML because `tomllib` is in the standard library and the format takes comments,
which is most of the point. The writer is hand-rolled (there is no stdlib TOML
*writer*) but only has to handle the shapes used below.
"""

import datetime
import textwrap
import tomllib

from . import codec, fieldinfo, idmap as idmap_module

# Confidence below this fraction gets flagged in the emitted file as a value
# worth a human look rather than a safe default.
SHAKY_DEFAULT = 0.95


class DecisionsError(ValueError):
    """The decisions file is malformed."""


class Decisions:
    """Parsed decisions. Everything is optional; absent means "use the default"."""

    def __init__(self, options=None, tag_map=None, mesh_defaults=None, source=None):
        self.options = options or {}
        self.tag_map = tag_map or []  # list of dicts: type, id, map_to, name
        self.mesh_defaults = mesh_defaults or {}
        self.source = source

    @property
    def use_vtfl(self):
        return bool(self.options.get("use_vtfl", False))

    @property
    def plugin_name(self):
        return self.options.get("plugin_name") or None

    def id_map(self):
        """Build an `idmap.IdMap` from the resolved entries."""
        mapping = idmap_module.IdMap()
        for entry in self.tag_map:
            target = (entry.get("map_to") or "").strip()
            if not target:
                continue  # deliberately left undecided
            mapping.add(
                entry["type"], entry["id"], target, entry.get("name") or None
            )
        return mapping

    def unresolved(self):
        """Entries a human has not filled in yet."""
        return [e for e in self.tag_map if not (e.get("map_to") or "").strip()]

    def __repr__(self):
        return (
            f"<Decisions {len(self.tag_map)} mappings "
            f"({len(self.unresolved())} unresolved), "
            f"{len(self.mesh_defaults)} overrides>"
        )


def load(path):
    """Read a decisions file."""
    with open(path, "rb") as handle:
        try:
            data = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise DecisionsError(f"{path}: {exc}") from None

    tag_map = []
    for i, entry in enumerate(data.get("tag", [])):
        for required in ("type", "id"):
            if required not in entry:
                raise DecisionsError(f"{path}: [[tag]] #{i + 1} is missing '{required}'")
        for field in ("type", "id", "map_to"):
            value = entry.get(field, "")
            if value and len(value) != 4:
                raise DecisionsError(
                    f"{path}: [[tag]] {entry['type']}.{entry['id']}: '{field}' must be "
                    f"exactly 4 characters, got {value!r}"
                )
        tag_map.append(entry)

    return Decisions(
        options=data.get("options", {}),
        tag_map=tag_map,
        mesh_defaults=data.get("mesh_defaults", {}),
        source=str(path),
    )


# --- Emitting a stub ---------------------------------------------------------


def build_stub(report, unresolved_refs, candidates=None, source_name=""):
    """Compose the contents of a decisions file for a conversion that just ran.

    ``unresolved_refs`` is ``{(tag_type, tag_id): reference_count}`` for tags the
    plugin points at but does not contain. ``candidates`` optionally maps a tag
    type to a list of ``(tag_id, name, archive_count)`` found in a Myth II
    install, so a human choosing a substitute can see the options.
    """
    from .convert.tags import mesh as mesh_converter

    lines = [
        "# myth-plugin-converter decisions",
        "#",
        "# Every entry here is something the converter could not decide for you.",
        "# Fill in what you want, delete what you do not care about, then re-run:",
        "#",
        "#     python -m src convert --in <plugin> --out <plugin> --decisions <this file>",
        "#",
        f"# Generated from: {source_name}",
        f"# Generated on:   {datetime.date.today().isoformat()}",
        "",
        "[options]",
        "",
        "# Set true to mark converted meshes as vTFL, putting Myth II into TFL",
        "# gameplay emulation. Measured: Magma - The Fallen Lords v1.9 sets this on",
        "# all 40 of its meshes; Magma - The Fallen Lords DX 1.3 (49 meshes) and",
        "# TFL Multipack v2.6 (60) set it on none. It makes the plugin depend on a",
        "# vTFL Unity tagset being loaded.",
        "use_vtfl = false",
        "",
        "# Name written into the plugin header. Keep the FILENAME under 32",
        "# characters too -- Myth II silently ignores longer ones.",
        f'plugin_name = {_str(_derived_name(source_name))}',
        "",
    ]

    lines += _unresolved_section(unresolved_refs, candidates or {})
    lines += _mesh_defaults_section(mesh_converter)
    return "\n".join(lines) + "\n"


def _unresolved_section(unresolved_refs, candidates):
    lines = [
        "",
        "# " + "-" * 74,
        "# Tags this plugin references but does not contain",
        "# " + "-" * 74,
        "#",
        "# A TFL plugin is not self-contained -- it references the stock TFL tag",
        "# library the way a Myth II plugin references the base game. Each entry",
        "# below is a tag some mesh points at that is not in the plugin.",
        "#",
        "# Set map_to to a 4-character Myth II tag id to substitute one, or leave it",
        "# empty to leave the reference as-is. Leaving it empty is fine if you plan",
        "# to supply the real tag from a converted TFL tagset instead.",
        "",
    ]
    if not unresolved_refs:
        lines.append("# (none -- every referenced tag is present in the plugin)")
        lines.append("")
        return lines

    for (tag_type, tag_id), count in sorted(
        unresolved_refs.items(), key=lambda kv: (-kv[1], kv[0])
    ):
        type_text = codec.decode_string(tag_type)
        id_text = codec.decode_string(tag_id)
        lines.append(f"# {type_text}.{id_text} -- referenced {count} time(s)")

        options = candidates.get(tag_type) or []
        if options:
            lines.append(f"#   candidates found in your Myth II install:")
            for cand_id, cand_name, archives in options[:8]:
                lines.append(
                    f"#     {cand_id:<6} {cand_name[:38]!r:<40} (in {archives} archive(s))"
                )
            if len(options) > 8:
                lines.append(f"#     ... and {len(options) - 8} more")
        else:
            lines.append("#   no candidates of this type found in your Myth II install")

        lines.append("[[tag]]")
        lines.append(f"type = {_str(type_text)}")
        lines.append(f"id = {_str(id_text)}")
        lines.append('map_to = ""')
        lines.append("")
    return lines


def _mesh_defaults_section(mesh_converter):
    lines = [
        "",
        "# " + "-" * 74,
        "# Mesh fields Myth II has and TFL does not",
        "# " + "-" * 74,
        "#",
        "# There is nothing in a TFL mesh to translate these from, so they are",
        "# synthesised. The values were measured across the 40 meshes of",
        "# Magma - The Fallen Lords v1.9, the faithful community TFL port.",
        "#",
        "# Uncomment and edit any you want to override. Entries marked CHECK were",
        "# not unanimous in the reference port and are worth a look.",
        "#",
        "# Each entry says what the setting does and, where the stored number is a",
        "# scaled integer, what it actually represents -- 229 is 0.895 of full",
        "# intensity, 2048 is 4 world units. Descriptions come from the official",
        "# Fear manual; the label in brackets is what Fear's own editor calls it.",
        "",
        "[mesh_defaults]",
        "",
    ]
    for field, value in mesh_converter.SYNTHESISED.items():
        if not isinstance(value, (int, float, bool)):
            continue  # byte fields are not usefully editable as text

        info = fieldinfo.get(field)
        if info:
            lines.append(f"# [{info.label}] {info.summary}")
            human = info.describe(value)
            if human != str(value):
                lines.append(f"#   {value} means {human}")
            if info.typical:
                low, high = info.typical
                lines.append(f"#   usual range: {low:g} to {high:g}")
            if info.note:
                for wrapped in textwrap.wrap(info.note, 72):
                    lines.append(f"#   {wrapped}")
            warning = fieldinfo.check(field, value)
            if warning:
                lines.append("#   NOTE: outside the usual range (see above)")

        lines.append(f"# {field} = {_scalar(value)}{_default_note(field)}")
        lines.append("")
    return lines


# How many of the reference port's 40 meshes agreed on each measured default.
# Anything short of unanimous is worth a human's attention rather than silent
# acceptance.
DEFAULT_CONFIDENCE = {
    "ceiling_height": 40,
    "reverb_volume": 40,
    "reverb_decay_time": 40,
    "reverb_damping": 40,
    "connector_count": 40,
    "connectors_size": 40,
    "fog_density": 40,
    "extra_flags": 40,
    "minimum_zoom_factor": 40,
    "editor_data_size": 40,
    "editor_data_offset": 40,
    "min_vtfl_version": 40,
    "max_vtfl_version": 40,
    "dark_fraction": 39,
    "light_fraction": 38,
    "reverb_environment": 38,
    "transition_point": 32,
}


def _default_note(field):
    agreed = DEFAULT_CONFIDENCE.get(field)
    if agreed is None:
        return ""
    if agreed >= 40:
        return f"   # {agreed}/40 meshes agreed"
    flag = "  CHECK" if agreed / 40 < SHAKY_DEFAULT else ""
    return f"   # {agreed}/40 meshes agreed{flag}"


def _derived_name(source_name):
    stem = source_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    for suffix in (".gor", ".plugin"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
    return stem[:32]


# --- Minimal TOML value emitting ---------------------------------------------
# Only the shapes used above. Not a general TOML writer.

_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _str(value):
    out = ['"']
    for char in str(value):
        if char in _ESCAPES:
            out.append(_ESCAPES[char])
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _scalar(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    return str(value)
