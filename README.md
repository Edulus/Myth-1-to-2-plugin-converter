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

**Phase 1 complete. Gate cleared on real TFL data** -- a 93 MB, 427-tag community plugin
(*Sir Mauriac's Tale*, Crow's Bridge Cartographers) reads and rewrites byte-for-byte.

Real data immediately disproved one of our layout assumptions, which is what the gate is
for: that plugin declares `header_size = 64` and then starts its first tag body at **128**,
with 64 unaccounted zero bytes in between. Assuming bodies begin right after the header
dropped those bytes and shifted every offset in the file. Unaccounted bytes are now carried
through verbatim rather than guessed at.

Still outstanding: **the gate has only been cleared on a TFL `.gor`.** The Myth II container
is a different layout (entrypoint block, derived directory position) and has only been
exercised against synthetic fixtures. Point it at a real Myth II plugin before trusting the
SB write path:

```sh
python -m src roundtrip "/path/to/Myth II/plugins/Some Plugin"
```

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
