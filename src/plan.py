"""The conversion plan: what *would* happen, computed without committing to it.

Before this existed, the only way to find out what the converter would do was to
run it and read the log afterwards. The report was a side effect of execution,
which meant there was no model to inspect and nothing to make a decision against
before the fact.

A `Plan` separates the three concerns:

* **Model** -- this module. Computes every outcome, every unresolved reference,
  every synthesised value and how well-evidenced it is. Executes nothing and
  writes nothing.
* **View** -- `src/views/`. Renders a plan as text or as a page. Never decides.
* **Control** -- `src/decisions.py`. A file of choices that feeds back in and
  changes the plan.

So the loop is: build a plan, look at it, adjust the decisions, rebuild the plan,
and only then execute it. `execute()` is a thin wrapper over the writer that
takes a plan that has already been inspected.

Building a plan costs one in-memory conversion. That is cheap next to writing
100 MB to disk, and it means the plan and the eventual output cannot disagree --
they come from the same code path.
"""

from dataclasses import dataclass, field

from . import codec, decisions as decisions_module, reader, writer
from .convert import plugin as convert_plugin
from .convert.tags import mesh as mesh_converter


@dataclass
class UnresolvedRef:
    """A tag the plugin points at but does not contain."""

    tag_type: bytes
    tag_id: bytes
    references: int
    candidates: list = field(default_factory=list)  # (id, name, archive_count)
    decided: bytes = None  # what the decisions file mapped it to, if anything

    @property
    def label(self):
        return f"{codec.decode_string(self.tag_type)}.{codec.decode_string(self.tag_id)}"


@dataclass
class SynthesisedField:
    """A Myth II mesh field with no TFL source, so it has to be invented."""

    name: str
    value: object
    agreed: int = None  # of the reference port's 40 meshes
    overridden: bool = False

    @property
    def confidence(self):
        if self.agreed is None:
            return "unmeasured"
        if self.agreed >= 40:
            return "unanimous"
        return "check"


@dataclass
class Plan:
    """Everything a conversion would do, before it does any of it."""

    source: str = ""
    source_tags: int = 0
    outcomes: list = field(default_factory=list)
    entrypoints: list = field(default_factory=list)
    unresolved: list = field(default_factory=list)
    synthesised: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    options: dict = field(default_factory=dict)
    decisions_path: str = None
    _monolith: object = None

    # --- queries the views and the CLI ask -----------------------------------

    def converted(self):
        return [o for o in self.outcomes if o.status == "converted"]

    def passed_through(self):
        return [o for o in self.outcomes if o.status == "passed-through"]

    def by_tag_type(self):
        """``{tag_type: {"converted": n, "passed-through": n}}``, ordered."""
        summary = {}
        for outcome in self.outcomes:
            row = summary.setdefault(outcome.tag_type, {"converted": 0, "passed-through": 0})
            row[outcome.status] += 1
        return dict(sorted(summary.items()))

    def undecided(self):
        return [u for u in self.unresolved if not u.decided]

    def needs_review(self):
        return [s for s in self.synthesised if s.confidence == "check" and not s.overridden]

    def is_ready(self):
        """True when nothing material is left to a guess."""
        return not self.undecided() and not self.needs_review()

    def output_size(self):
        return len(writer.pack(self._monolith, preserve_layout=False))

    def summary(self):
        return {
            "source tags": self.source_tags,
            "converted": len(self.converted()),
            "passed through": len(self.passed_through()),
            "entrypoints": len(self.entrypoints),
            "unresolved references": len(self.unresolved),
            "still undecided": len(self.undecided()),
            "synthesised fields needing review": len(self.needs_review()),
        }


def build(in_path, decisions=None, candidates=None, name=None):
    """Compute what converting ``in_path`` would do. Writes nothing.

    ``decisions`` is a loaded `decisions.Decisions`; ``candidates`` is the
    ``{tag_type: [(id, name, archives)]}`` map from a Myth II install.
    """
    mono = reader.read(in_path)

    id_map = decisions.id_map() if decisions else None
    context = convert_plugin.ConversionContext(
        use_vtfl=decisions.use_vtfl if decisions else False,
        mesh_defaults=decisions.mesh_defaults if decisions else None,
    )
    sb_mono, report = convert_plugin.convert_container(
        mono,
        id_map=id_map,
        name=name or (decisions.plugin_name if decisions else None),
        context=context,
    )

    candidates = candidates or {}
    unresolved = [
        UnresolvedRef(
            tag_type=tag_type,
            tag_id=tag_id,
            references=count,
            candidates=candidates.get(tag_type, []),
            decided=(id_map.lookup(tag_type, tag_id) or (None,))[0] if id_map else None,
        )
        for (tag_type, tag_id), count in sorted(
            report.unresolved.items(), key=lambda kv: (-kv[1], kv[0])
        )
    ]

    overrides = decisions.mesh_defaults if decisions else {}
    synthesised = [
        SynthesisedField(
            name=field_name,
            value=overrides.get(field_name, value),
            agreed=decisions_module.DEFAULT_CONFIDENCE.get(field_name),
            overridden=field_name in overrides,
        )
        for field_name, value in mesh_converter.SB_ONLY_DEFAULTS.items()
        if isinstance(value, (int, float, bool))
    ]

    return Plan(
        source=str(in_path),
        source_tags=report.source_tags,
        outcomes=report.outcomes,
        entrypoints=report.entrypoints,
        unresolved=unresolved,
        synthesised=synthesised,
        warnings=report.warnings,
        options={
            "use_vtfl": context.use_vtfl,
            "plugin_name": codec.decode_string(sb_mono.header.name),
        },
        decisions_path=decisions.source if decisions else None,
        _monolith=sb_mono,
    )


def execute(plan, out_path):
    """Write the plan's output. The only step that touches the filesystem.

    Returns the number of bytes written.
    """
    data = writer.pack(plan._monolith, preserve_layout=False)

    # The same self-check convert_file does: what we wrote must read back as
    # what we planned.
    verify = reader.read_bytes(data, filename=str(out_path))
    if len(verify.tags) != len(plan._monolith.tags):
        raise convert_plugin.ConversionError(
            f"planned {len(plan._monolith.tags)} tags but the output reads back as "
            f"{len(verify.tags)}"
        )

    with open(out_path, "wb") as handle:
        handle.write(data)
    return len(data)
