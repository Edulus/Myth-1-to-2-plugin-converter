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

**Phase 1 complete. Gate cleared on both game versions against real data.**

| Corpus | Files | Bytes | Result |
|---|---:|---:|---|
| Myth II plugins | 276 | 9.90 GB | 276/276 byte-exact |
| Myth II core tag archives | 5 | 512 MB | 5/5 byte-exact |
| TFL plugin (*Sir Mauriac's Tale*) | 1 | 93 MB | byte-exact |

That covers every archive type the format defines in the wild -- `PLUGIN`, `PATCH`,
`ADDON`, `INTERFACE`, `METASERVER` and the `FOUNDATION` install archives -- up to a
624 MB / 923-tag plugin and a 2,649-tag one.

Real data was worth the trouble immediately: it disproved a layout assumption that
synthetic fixtures could never have caught. The TFL plugin declares `header_size = 64` and
then starts its first tag body at **128**, with 64 unaccounted zero bytes in between.
Assuming bodies begin right after the header dropped those bytes and shifted every offset
in the file. Unaccounted bytes are now carried through verbatim rather than guessed at.

Reproduce with:

```sh
python -m src roundtrip "/path/to/Myth II/plugins"
python -m src roundtrip "/path/to/Myth II/tags"
```

## Requirements

Python 3.12+. No dependencies -- standard library only, no build step.

## Usage

```sh
python -m src info <container>            # header, entrypoints and tag list
python -m src info --types <container>     # summarise by tag type
python -m src roundtrip <container|dir>... # verify read/write is byte-exact
python -m src diff <a> <b>                 # compare two containers tag by tag
```

`roundtrip` accepts a directory and skips anything in it that is not a Myth container
(readmes, resource forks, `plugin cache`), so you can point it straight at a plugins folder.

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

| Tag type | Status | Known lossy fields | Myth II fields synthesised |
|---|---|---|---|
| `text` | **converts** | a literal `\` becomes `\|`; when followed by `i`/`b`/`p` it is indistinguishable from markup and no warning is possible | -- |
| `stli` | **converts** | as `text` | -- |
| `.256` `d256` | pass-through | body unconverted | -- |
| `mons` | pass-through | **body unconverted** -- 512B in TFL vs 1024B in Myth II, so this is wrong, not merely lossy | -- |
| `unit` `arti` | pass-through | `arti` is 128B vs 168B | -- |
| `mesh` | pass-through | same size, different field meanings | -- |
| `proj` `prgr` `lpgr` `core` `soun` `amso` `phys` `scen` `part` `medi` | pass-through | unverified whether these differ at all | -- |
| *(all types)* | header converts | TFL `tag_version` and `flags` dropped -- measured safe, see [NOTES.md](NOTES.md) section 9; `version` clamped if it exceeds int16 | `identifier` (unique, sequential), `type` (mirrors container), `flags`, `destination`, `owner_index` |
| *(container)* | header converts | TFL `checksum`, `mod_time` dropped | `checksum` and `header_checksum` **written as zero** -- algorithm unknown; `type`=`PLUGIN`; `version`=0 |

"Pass-through" means the body is copied byte-for-byte and the tag is reported as
unconverted. It is never silently presented as converted.

**The output is not a playable plugin yet.** Two things stand between here and playable:
the pass-through bodies above, and entrypoint synthesis -- a TFL `.gor` has no entrypoints,
and a Myth II plugin needs one per playable mesh or the level never reaches the menu. That
needs the mesh converter.

The container side, however, is confirmed working: a plugin built by `src/writer.py` with
**both checksums zeroed** loads and plays in Myth II 1.8.5. See below.

## Verified in-engine

Tested against **Myth II 1.8.5 build 471b**, using a real 102-tag plugin as the subject
([NOTES.md](NOTES.md) section 11):

- **Neither container checksum is validated.** A plugin we built, with `checksum` and
  `header_checksum` both zero, loads and plays. This removes what was the project's biggest
  risk -- the algorithm never needs reversing.
- **Padding between the tag directory and the first body is optional.** Dropping it changes
  nothing, matching the corpus where 51 of 186 entrypoint-bearing plugins have none.
- **Myth II silently ignores a plugin whose filename exceeds 32 characters.** Nothing
  reports this; the plugin simply never appears. `convert` warns about it.

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

## License and credits

MIT -- see [LICENSE](LICENSE).

This project would not exist without [jwheare/mythextract](https://github.com/jwheare/mythextract)
(MIT, © 2025 James Wheare), which is the source of the format research this builds on.
[NOTICE](NOTICE) records the attribution and the trademark position;
[NOTES.md](NOTES.md) documents what was taken from it, file by file, with citations at
each use site in the source.

Myth: The Fallen Lords and Myth II: Soulblighter are trademarks of their respective rights
holders. This is an unofficial, non-commercial interoperability tool, not affiliated with
or endorsed by any rights holder.
