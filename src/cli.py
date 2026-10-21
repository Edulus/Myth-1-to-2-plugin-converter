"""Command line entry point.

    python -m src info <container>          list tags and container header
    python -m src roundtrip <container>...  verify read/write is byte-exact
    python -m src diff <a> <b>              compare two containers tag by tag
    python -m src plan --in <gor>           what a conversion would do
    python -m src convert --in <gor> --out <plugin>
    python -m src tagset --in TAGS.GOR --in ARTSOUND.GOR --out <plugin>
    python -m src studio                    the guided local browser app
"""

import argparse
import pathlib
import sys

from . import codec, decisions, plan as plan_module, plugindiff, reader, writer
from .views import html as html_view, text as text_view
from .convert import plugin as convert_plugin


def _load(path):
    try:
        return reader.read(path)
    except reader.FormatError as exc:
        print(f"error: {path}: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)


def cmd_info(args):
    mono = _load(args.container)
    game = "TFL" if mono.is_tfl else "Myth II"

    print(f"{args.container}")
    print(f"  format         {game}")
    for name in mono.header.field_names:
        value = getattr(mono.header, name)
        print(f"  {name:<14} {plugindiff.show_value(value)}")

    gaps = reader.find_gaps(mono)
    if gaps:
        print(f"  layout         {len(gaps)} unaccounted/overlapping regions")
        for gap in gaps[:10]:
            print(f"                 [{gap.start}:{gap.end}] {gap.size}B {gap.label}")
    else:
        print("  layout         fully accounted for")

    if mono.entrypoints:
        print(f"\nEntrypoints ({len(mono.entrypoints)})")
        print("-" * 72)
        for entry in mono.entrypoints:
            print(
                f" {codec.decode_string(entry.entry_id):<6} "
                f"{codec.decode_string(entry.entry_name):<32} "
                f"{codec.decode_string(entry.entry_long_name)}"
            )

    print(f"\nTags ({len(mono.tags)})")
    print("-" * 72)
    if args.types:
        for tag_type, count in sorted(mono.tag_types().items()):
            print(f" {codec.decode_string(tag_type):<6} {count:>5}")
    else:
        for i, tag in enumerate(mono.tags):
            print(
                f" {i:>4} {codec.decode_string(tag.tag_type):<6} "
                f"{codec.decode_string(tag.tag_id):<6} "
                f"{len(tag.body):>9}B  {tag.name}"
            )
    return 0


def _expand(paths):
    """Expand directories into their files. Not recursive -- Myth keeps plugins
    flat in one folder, and the folder also holds readmes and stray junk."""
    expanded = []
    for path in paths:
        path = pathlib.Path(path)
        if path.is_dir():
            expanded += sorted(p for p in path.iterdir() if p.is_file())
        else:
            expanded.append(path)
    return expanded


def cmd_roundtrip(args):
    """The Phase 1 correctness gate, runnable against real game data."""
    ok = failures = skipped = 0
    for path in _expand(args.containers):
        try:
            data = path.read_bytes()
        except OSError as exc:
            print(f"FAIL  {path.name}: {exc}")
            failures += 1
            continue

        # A plugins folder is full of readmes, resource forks and .DS_Store.
        # Those are not failures, they are just not containers.
        try:
            reader.detect_game_version(data)
        except reader.FormatError:
            skipped += 1
            if args.verbose:
                print(f"skip  {path.name} (not a Myth container)")
            continue

        try:
            problems = writer.diagnose_round_trip(data, filename=path.name)
        except (reader.FormatError, writer.PackError) as exc:
            print(f"FAIL  {path.name}: {exc}")
            failures += 1
            continue

        if problems:
            failures += 1
            print(f"FAIL  {path.name} ({len(data):,} bytes)")
            for problem in problems:
                print(f"        {problem}")
        else:
            ok += 1
            if args.verbose:
                print(f"ok    {path.name} ({len(data):,} bytes)")

    print(f"\n{ok}/{ok + failures} byte-exact, {skipped} skipped (not containers)")
    return 1 if failures else 0


def cmd_diff(args):
    left = _load(args.left)
    right = _load(args.right)
    result = plugindiff.diff(left, right)
    for line in plugindiff.format_report(
        result,
        left_name=str(args.left),
        right_name=str(args.right),
        show_same=args.all,
    ):
        print(line)
    return 0 if result.identical else 1


def _candidate_tags(myth2_dir):
    """Tag ids and names by type, gathered from a Myth II install.

    Used to show a human their options when they have to choose a substitute
    for a TFL tag Myth II has no equivalent of.
    """
    candidates = {}
    counts = {}
    root = pathlib.Path(myth2_dir)
    sources = [root / "tags", root / "plugins", root]
    for source in sources:
        if not source.is_dir():
            continue
        for path in sorted(source.iterdir()):
            if not path.is_file():
                continue
            try:
                data = path.read_bytes()
                reader.detect_game_version(data)
                mono = reader.read_bytes(data, path.name)
            except (OSError, reader.FormatError, ValueError):
                continue
            if not mono.is_sb:
                continue
            for tag in mono.tags:
                key = (tag.tag_type, tag.tag_id)
                counts[key] = counts.get(key, 0) + 1
                candidates.setdefault(tag.tag_type, {}).setdefault(
                    tag.tag_id, tag.name
                )
    return {
        tag_type: sorted(
            (
                (codec.decode_string(tag_id), name, counts[(tag_type, tag_id)])
                for tag_id, name in by_id.items()
            ),
            key=lambda row: -row[2],
        )
        for tag_type, by_id in candidates.items()
    }


def cmd_studio(args):
    from .studio import serve

    serve(port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_plan(args):
    """Show what a conversion would do, without doing it.

    The model/view/control split: this builds the plan (model), renders it
    (view), and optionally emits a page that collects decisions (control) whose
    output feeds back in via --decisions.
    """
    chosen = None
    if args.decisions:
        try:
            chosen = decisions.load(args.decisions)
        except (OSError, decisions.DecisionsError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    candidates = {}
    if args.myth2_dir:
        print(f"Scanning {args.myth2_dir} for substitute candidates...", file=sys.stderr)
        candidates = _candidate_tags(args.myth2_dir)

    try:
        plan = plan_module.build(
            args.inp, decisions=chosen, candidates=candidates, name=args.name
        )
    except (reader.FormatError, convert_plugin.ConversionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.html:
        args.html.write_text(
            html_view.render(plan, title=args.title or "Conversion plan"),
            encoding="utf-8",
        )
        print(f"Wrote {args.html}")
    else:
        for line in text_view.render(plan, verbose=args.verbose):
            print(line)

    return 0 if plan.is_ready() else 1


def cmd_convert(args):
    if args.out.exists() and not args.force:
        print(
            f"error: {args.out} already exists (use --force to overwrite)",
            file=sys.stderr,
        )
        return 2

    id_map = None
    context = None
    name = args.name
    if args.decisions:
        try:
            chosen = decisions.load(args.decisions)
        except (OSError, decisions.DecisionsError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        id_map = chosen.id_map()
        context = convert_plugin.ConversionContext(
            use_vtfl=chosen.use_vtfl, mesh_defaults=chosen.mesh_defaults
        )
        name = name or chosen.plugin_name
        print(
            f"Using decisions from {args.decisions}: {len(id_map)} tag mappings, "
            f"{len(chosen.unresolved())} still undecided, "
            f"{len(chosen.mesh_defaults)} mesh overrides, vtfl={chosen.use_vtfl}"
        )

    try:
        report, written = convert_plugin.convert_file(
            args.inp, args.out, id_map=id_map, name=name, context=context
        )
    except (reader.FormatError, writer.PackError, convert_plugin.ConversionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except PermissionError as exc:
        print(
            f"error: cannot write {exc.filename} -- if Myth II is running it holds "
            f"its plugins open; quit it and try again",
            file=sys.stderr,
        )
        return 2

    for line in convert_plugin.format_report(report, str(args.inp), str(args.out)):
        print(line)
    print(f"\nWrote {written:,} bytes.")

    if args.emit_decisions:
        candidates = {}
        if args.myth2_dir:
            print(f"Scanning {args.myth2_dir} for substitute candidates...")
            candidates = _candidate_tags(args.myth2_dir)
        stub = decisions.build_stub(
            report, report.unresolved, candidates, source_name=str(args.inp)
        )
        args.emit_decisions.write_text(stub, encoding="utf-8")
        print(
            f"Wrote decisions template to {args.emit_decisions} "
            f"({len(report.unresolved)} unresolved references to review). "
            f"Edit it, then re-run with --decisions."
        )

    if report.passed_through() or report.unresolved:
        print(
            "This is NOT a playable plugin yet: passed-through tag bodies are still "
            "in TFL format, and it references tags it does not contain."
        )
    return 0


def cmd_tagset(args):
    if args.out.exists() and not args.force:
        print(
            f"error: {args.out} already exists (use --force to overwrite)",
            file=sys.stderr,
        )
        return 2
    try:
        report, written, duplicates = convert_plugin.convert_tagset(
            args.inp, args.out, name=args.name
        )
    except (reader.FormatError, writer.PackError, convert_plugin.ConversionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except PermissionError as exc:
        print(
            f"error: cannot write {exc.filename} -- if Myth II is running it holds "
            f"its plugins open; quit it and try again",
            file=sys.stderr,
        )
        return 2

    sources = ", ".join(str(p) for p in args.inp)
    for line in convert_plugin.format_report(report, sources, str(args.out)):
        print(line)
    for path, count in duplicates.items():
        print(f"Skipped {count} tags in {path} already supplied by an earlier --in.")
    print()
    print(f"Wrote {written:,} bytes: a tagset (no entrypoints). In Myth II, pick it")
    print("under New Game > Tagsets after choosing the campaign it supports.")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="myth-plugin-converter",
        description="Read, verify and compare Myth TFL / Myth II tag containers.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    info = sub.add_parser("info", help="list a container's header and tags")
    info.add_argument("container", type=pathlib.Path)
    info.add_argument(
        "--types", action="store_true", help="summarise by tag type instead of listing"
    )
    info.set_defaults(func=cmd_info)

    rt = sub.add_parser(
        "roundtrip", help="read and rewrite a container, checking it is byte-exact"
    )
    rt.add_argument(
        "containers", nargs="+", type=pathlib.Path, help="files, or a plugins directory"
    )
    rt.add_argument(
        "-v", "--verbose", action="store_true", help="list passes and skips too"
    )
    rt.set_defaults(func=cmd_roundtrip)

    dif = sub.add_parser("diff", help="compare two containers tag by tag")
    dif.add_argument("left", type=pathlib.Path)
    dif.add_argument("right", type=pathlib.Path)
    dif.add_argument("--all", action="store_true", help="include unchanged tags")
    dif.set_defaults(func=cmd_diff)

    con = sub.add_parser("convert", help="convert a TFL container into a Myth II plugin")
    con.add_argument("--in", dest="inp", required=True, type=pathlib.Path)
    con.add_argument("--out", required=True, type=pathlib.Path)
    con.add_argument("--name", help="plugin name to write into the header")
    con.add_argument("--force", action="store_true", help="overwrite an existing output")
    con.add_argument(
        "--decisions", type=pathlib.Path,
        help="apply a decisions file (tag mappings, mesh overrides, options)",
    )
    con.add_argument(
        "--emit-decisions", type=pathlib.Path, metavar="FILE",
        help="write a decisions template listing everything needing a human choice",
    )
    con.add_argument(
        "--myth2-dir", type=pathlib.Path, metavar="DIR",
        help="a Myth II install, scanned to suggest substitutes in --emit-decisions",
    )
    con.set_defaults(func=cmd_convert)

    tag = sub.add_parser(
        "tagset",
        help="convert TFL tag archives (e.g. TAGS.GOR, ARTSOUND.GOR) into one Myth II tagset",
    )
    tag.add_argument(
        "--in", dest="inp", required=True, type=pathlib.Path, action="append",
        help="a TFL archive; repeat for several, most authoritative first",
    )
    tag.add_argument("--out", required=True, type=pathlib.Path)
    tag.add_argument(
        "--name", help="name written into the header (default: the output filename)"
    )
    tag.add_argument("--force", action="store_true", help="overwrite an existing output")
    tag.set_defaults(func=cmd_tagset)

    pln = sub.add_parser(
        "plan", help="show what a conversion would do, without writing anything"
    )
    pln.add_argument("--in", dest="inp", required=True, type=pathlib.Path)
    pln.add_argument("--name", help="plugin name to write into the header")
    pln.add_argument(
        "--decisions", type=pathlib.Path, help="apply a decisions file first"
    )
    pln.add_argument(
        "--myth2-dir", type=pathlib.Path, metavar="DIR",
        help="a Myth II install, scanned to suggest substitutes",
    )
    pln.add_argument(
        "--html", type=pathlib.Path, metavar="FILE",
        help="write an interactive page instead of a text report",
    )
    pln.add_argument("--title", help="title for the page")
    pln.add_argument("-v", "--verbose", action="store_true", help="list everything")
    pln.set_defaults(func=cmd_plan)

    stu = sub.add_parser(
        "studio", help="open the guided browser app (local only)"
    )
    stu.add_argument("--port", type=int, default=0, help="port (default: pick a free one)")
    stu.add_argument(
        "--no-browser", action="store_true", help="do not open a browser automatically"
    )
    stu.set_defaults(func=cmd_studio)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except BrokenPipeError:
        sys.stdout = None
        raise SystemExit(1)
