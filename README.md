# myth-plugin-converter

Converts **Myth: The Fallen Lords (TFL)** plugin files into **Myth II: Soulblighter (SB)**
plugin files.

TFL and Myth II share a common tag architecture -- a monolithic container holding a header,
a tag directory, and concatenated tag bodies -- but differ in the tag header layout, the
container header layout, and in the internal layout of many tag bodies. This tool aims to
read a TFL monolith/plugin, rewrite the tags it contains into Myth II form, and **write out
a working Myth II plugin**.

Built on the research and format work in [jwheare/mythextract](https://github.com/jwheare/mythextract),
which provides the reading and single-tag-header conversion side of the problem. See
[NOTES.md](NOTES.md) for a detailed account of what mythextract gives us and what this
project still has to build.

## Status

**Phase 0 complete** -- research. mythextract solves reading, and already converts a single
tag *header* from TFL to SB form (`myth_headers.tfl2sb`). What it has no code path for at
all is **writing a monolithic container**. Details, verified struct sizes, and open
questions are in [NOTES.md](NOTES.md).

**Phase 1 code complete, gate not yet cleared.** The reader, the packer, a byte-exact
round-trip test and a `plugindiff`-style comparison all exist and pass against synthetic
containers. They have **not** been run against a real Myth II plugin, because there is no
Myth installation on this machine. Until that happens the gate is provisional: synthetic
fixtures prove the reader and writer agree with each other and with the format as
[NOTES.md](NOTES.md) describes it, but only real game data proves that description matches
what Bungie shipped.

To clear the gate, point it at a plugin:

```sh
python -m src roundtrip "/path/to/Myth II/plugins/Some Plugin"
```

Phase 2 does not start until that reports byte-exact.

## Requirements

Python 3.12+. No dependencies -- standard library only, no build step.

## Usage

```sh
python -m src info <container>           # header, entrypoints and tag list
python -m src info --types <container>    # summarise by tag type
python -m src roundtrip <container>...    # verify read/write is byte-exact
python -m src diff <a> <b>                # compare two containers tag by tag
```

`info` and `roundtrip` accept both Myth II containers and TFL `.gor` files. `diff` compares
across game versions too. `convert` arrives in Phase 2.

## Tests

```sh
python -m unittest discover -s . -p "test_*.py"    # no dependencies
python -m pytest                                    # if you have pytest
```

The suite runs clean without game data -- the real-data tests skip. To include them:

```sh
MYTH_SAMPLE_PLUGIN=<file> python -m unittest discover -s . -p "test_*.py"
MYTH_SAMPLE_DIR=<dir>     python -m unittest discover -s . -p "test_*.py"
```

Set `MYTH_REQUIRE_SAMPLE=1` to make a *missing* sample an error rather than a skip, for a
run that is meant to be the real gate.

## Tag type support matrix

Nothing converts yet. Phase 1 reads and rewrites containers without touching tag bodies, so
every type currently passes through byte-for-byte.

| Tag type | Status | Known lossy fields | SB-only fields synthesised |
|---|---|---|---|
| *(all)* | pass-through | -- | -- |

This table gets a row per tag type as Phase 3 lands them, tracking status
(pass-through / converts / not-started), fields we lose, and fields we default because TFL
has no source for them.

## Layout

```
src/codec.py       minimal binary struct codec (lossless; preserves padding)
src/formats.py     container and tag header definitions, ported with citations
src/reader.py      parse a TFL .gor or Myth II container
src/writer.py      pack one back -- the piece mythextract does not have
src/plugindiff.py  tag-by-tag comparison of two containers
src/cli.py         command line entry point
tests/             unittest suite; fixtures.py builds synthetic containers
reference/         git-ignored clone of jwheare/mythextract (prior art, not ours)
NOTES.md           research notes on the reference implementation and the format
```

## Honest limitations

This tool will get a map most of the way, not all of the way. `text`, `stli` and
pass-through types are tractable. `mons`, `arti` and mesh map actions involve real format
changes with fields that have no TFL source and must be defaulted. `mesh` is the hardest.
Expect manual finishing work, and see [NOTES.md](NOTES.md) section 6 for the known unknowns
-- chiefly that nobody has worked out how the Myth II container checksums are computed,
which Phase 1 sidesteps by preserving them but a plugin *builder* cannot.

## Game data

No copyrighted Bungie game data (plugins, `.gor` monoliths, extracted tags, sounds, art)
is ever committed to this repository. `.gitignore` is set up to keep it out. Tests read
from paths supplied at runtime and skip when absent. You supply your own legally obtained
Myth installation when running the tool.
