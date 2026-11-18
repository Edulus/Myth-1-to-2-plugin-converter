"""Real-data regression check (improvement plan item B2).

Converts *Sir Mauriac's Tale* with every stock TFL tag built in, in memory,
and compares the result with a manifest kept in the repository
(``tests/regression/manifest.json``): a short hash of every converted tag's
body, and, per tag type, how many of our stock tags are byte-identical to
Project Magma's port. No game data is committed, only hashes and counts.

    python scripts/regression.py --tfl-tags "<TFL>/TAGS" --magma "<Magma - The Fallen Lords v1.9>"
    python scripts/regression.py ... --update     # accept the changes

A change that is meant shows up here as a list of which tag types changed and
how many tags; commit the updated manifest with it, so the diff shows its
reach. A change that is not meant shows up here before it reaches players.

Inputs: the source plugin from the git-ignored ``local/release/`` (see
documentation/site-and-releases.md), your TFL tags folder (``--tfl-tags`` or
``TFL_TAGS_DIR``), and optionally Magma's port (``--magma`` or
``MAGMA_TFL_PORT``) for the similarity counts. ``tests/test_regression.py``
runs the check when those environment variables are set.
"""

import argparse
import collections
import hashlib
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import __version__, compare, reader  # noqa: E402
from src.convert import plugin  # noqa: E402

SOURCE = ROOT / "local" / "release" / "cbc.TFL.mauriac.gor"
MANIFEST = ROOT / "tests" / "regression" / "manifest.json"


def tag_key(tag):
    """``type/id`` with both shown as text when printable, hex otherwise."""
    def show(b):
        text = b.decode("latin-1")
        return text if text.isprintable() and "/" not in text else "0x" + b.hex()
    return f"{show(tag.tag_type)}/{show(tag.tag_id)}"


def body_hashes(tags):
    """``{key: hash}``; a repeated key gets ``#2``, ``#3``... in directory order."""
    out, seen = {}, collections.Counter()
    for tag in tags:
        key = tag_key(tag)
        seen[key] += 1
        if seen[key] > 1:
            key = f"{key}#{seen[key]}"
        out[key] = hashlib.sha256(tag.body).hexdigest()[:16]
    return out


def convert(tfl_tags):
    stock = [tfl_tags / "TAGS.GOR", tfl_tags / "ARTSOUND.GOR"]
    for p in [SOURCE] + stock:
        if not p.is_file():
            raise SystemExit(f"not found: {p}")
    mono = reader.read(SOURCE)
    mono, _ = plugin.bundle_stock(mono, stock, only_used=False)
    sb_mono, _report = plugin.convert_container(mono, name="ZZ Mauriac TFL2SB")
    return sb_mono


def magma_identical(sb_mono, magma_path):
    result = compare.compare([sb_mono], [reader.read(magma_path)])
    return {t.decode("latin-1"): s.identical for t, s in sorted(result.types.items())}


def diff(old, new):
    """Changes between two manifests, as lines; empty if none."""
    lines = []
    old_tags, new_tags = old.get("tags", {}), new["tags"]
    by_type = collections.defaultdict(lambda: collections.Counter())
    for key in old_tags.keys() | new_tags.keys():
        kind = key.split("/", 1)[0]
        if key not in new_tags:
            by_type[kind]["removed"] += 1
        elif key not in old_tags:
            by_type[kind]["added"] += 1
        elif old_tags[key] != new_tags[key]:
            by_type[kind]["changed"] += 1
    for kind in sorted(by_type):
        counts = ", ".join(f"{n} {what}" for what, n in sorted(by_type[kind].items()))
        lines.append(f"  {kind}: {counts}")
    old_sim, new_sim = old.get("magma_identical", {}), new.get("magma_identical")
    if new_sim is not None:
        for kind in sorted(old_sim.keys() | new_sim.keys()):
            a, b = old_sim.get(kind, 0), new_sim.get(kind, 0)
            if a != b:
                lines.append(f"  identical to Magma, {kind}: {a} -> {b}" + ("   <-- fewer" if b < a else ""))
    return lines


def build(tfl_tags, magma=None):
    sb_mono = convert(tfl_tags)
    manifest = {
        "about": "Sir Mauriac's Tale converted with every stock TFL tag; see scripts/regression.py",
        "converter": __version__,
        "tags": body_hashes(sb_mono.tags),
    }
    if magma:
        manifest["magma_identical"] = magma_identical(sb_mono, magma)
    return manifest


def check(tfl_tags, magma=None, update=False):
    """Returns the list of change lines (empty: no change). With ``update``,
    writes the new manifest."""
    new = build(tfl_tags, magma)
    old = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    if magma is None and "magma_identical" in old:
        new["magma_identical"] = old["magma_identical"]  # not measured this time; keep
    lines = diff(old, new)
    if update:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(new, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tfl-tags", type=pathlib.Path, default=os.environ.get("TFL_TAGS_DIR"))
    ap.add_argument("--magma", type=pathlib.Path, default=os.environ.get("MAGMA_TFL_PORT"))
    ap.add_argument("--update", action="store_true", help="write the new manifest")
    args = ap.parse_args(argv)
    if not args.tfl_tags:
        ap.error("--tfl-tags (or TFL_TAGS_DIR) is required")
    lines = check(args.tfl_tags, args.magma, args.update)
    if not lines:
        print("No change from the manifest.")
        return 0
    print("Changed from the manifest:" if not args.update else "Manifest updated. Changes:")
    print("\n".join(lines))
    return 0 if args.update else 1


if __name__ == "__main__":
    sys.exit(main())
