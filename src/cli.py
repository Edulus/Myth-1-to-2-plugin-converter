"""Command line entry point.

    python -m src info <container>          list tags and container header
    python -m src roundtrip <container>...  verify read/write is byte-exact
    python -m src diff <a> <b>              compare two containers tag by tag

`convert` arrives in Phase 2. Until the round-trip gate passes against real game
data there is nothing here worth converting with.
"""

import argparse
import pathlib
import sys

from . import codec, plugindiff, reader, writer


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


def cmd_roundtrip(args):
    """The Phase 1 correctness gate, runnable against real game data."""
    failures = 0
    for path in args.containers:
        path = pathlib.Path(path)
        try:
            data = path.read_bytes()
        except OSError as exc:
            print(f"FAIL  {path.name}: {exc}")
            failures += 1
            continue
        try:
            problems = writer.diagnose_round_trip(data, filename=path.name)
        except (reader.FormatError, writer.PackError) as exc:
            print(f"FAIL  {path.name}: {exc}")
            failures += 1
            continue

        if problems:
            failures += 1
            print(f"FAIL  {path.name} ({len(data)} bytes)")
            for problem in problems:
                print(f"        {problem}")
        else:
            print(f"ok    {path.name} ({len(data)} bytes)")

    total = len(args.containers)
    print(f"\n{total - failures}/{total} byte-exact")
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
    rt.add_argument("containers", nargs="+", type=pathlib.Path)
    rt.set_defaults(func=cmd_roundtrip)

    dif = sub.add_parser("diff", help="compare two containers tag by tag")
    dif.add_argument("left", type=pathlib.Path)
    dif.add_argument("right", type=pathlib.Path)
    dif.add_argument("--all", action="store_true", help="include unchanged tags")
    dif.set_defaults(func=cmd_diff)

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
