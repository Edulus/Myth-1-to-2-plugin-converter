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

## The app

**Windows, no Python yet:** double-click [`launch.bat`](launch.bat). It looks for Python
3.12+ and, if it can't find one, installs it via `winget` (built into current Windows) and
tells you to run it again. Windows may warn that the script is from an unidentified
publisher the first time -- click **More info -> Run anyway**; there is no code signing on
a community tool like this one. The one-time detection logic lives in
[`scripts/launch.ps1`](scripts/launch.ps1).

**Already have Python (any OS):**

```sh
python -m src studio
```

Opens a guided app in your browser for converting a map. Built for someone doing this for
the first time: it explains what tags and plugins are, why a Fallen Lords plugin is not
self-contained, what each decision costs, and how to read the game's log when a level fails
to start. An **Expert** tab drops the hand-holding once you know the ropes.

Unlike `plan --html`, the studio can act -- browse for your files, find your Myth II
install, run the conversion, and write the plugin into your plugins folder.

It binds to `127.0.0.1` only, refuses cross-site requests, and requires a token minted at
startup and passed in the URL it prints. It reads and writes real files on your machine and
is not safe to expose beyond your own computer.

## Usage

```sh
python -m src info <container>            # header, entrypoints and tag list
python -m src info --types <container>     # summarise by tag type
python -m src roundtrip <container|dir>... # verify read/write is byte-exact
python -m src diff <a> <b>                 # compare two containers tag by tag
python -m src plan --in <gor>                     # what a conversion would do
python -m src convert --in <gor> --out <plugin>   # do it
```

### Plan, then convert

`plan` builds the conversion in memory and reports it without writing anything -- so you
can look at the model, decide, and only then commit. It exits non-zero while anything is
still being guessed at, which makes it usable as a gate.

```sh
# A page you can operate: every decision the converter cannot make, with the
# candidates from your own install, and the decisions file forming as you choose.
python -m src plan --in plugin.gor --myth2-dir "/path/to/Myth II" --html plan.html
```

That page is the view and the control surface; its output is `decisions.toml`, which is an
input to the model. Model, view, control:

| | |
|---|---|
| **Model** | `src/plan.py` -- computes every outcome, writes nothing |
| **View** | `src/views/text.py`, `src/views/html.py` -- render a plan, decide nothing |
| **Control** | `src/decisions.py` -- choices that feed back and change the plan |

### The decisions file

Most of this converter has right answers, verified against real data. Some things do not,
and no measurement will settle them -- which Myth II tag stands in for a TFL tag that has
no equivalent, which synthesised values to accept, whether to enable vTFL. Those are
judgement calls for someone who knows the level.

So the tool writes them down instead of guessing silently:

```sh
# Convert, and emit a template listing every decision it could not make.
# --myth2-dir is scanned to suggest substitutes.
python -m src convert --in plugin.gor --out out.plugin     --emit-decisions choices.toml --myth2-dir "/path/to/Myth II"

# Edit choices.toml, then feed it back.
python -m src convert --in plugin.gor --out out.plugin --decisions choices.toml
```

The template is commented TOML carrying the evidence behind each guess -- how many of the
reference port's 40 meshes agreed on a default, which candidate tags exist in your install
and how widely they are used. Entries marked `CHECK` were not unanimous.

Conversion still runs with decisions unmade; it reports them rather than refusing. A file
rather than a GUI because decisions are then durable, diffable, reviewable, and shareable
between people converting different plugins.

`roundtrip` accepts a directory and skips anything in it that is not a Myth container
(readmes, resource forks, `plugin cache`), so you can point it straight at a plugins folder.

`info` and `roundtrip` accept both Myth II containers and TFL `.gor` files. `diff` compares
across game versions too. `convert` and `plan` read TFL `.gor` files only.

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
| `mons` | **converts** | `effect_modifiers` (per-monster damage-vulnerability profile) has no Myth II destination on `mons` -- it moved to `obje`, a cross-tag write out of scope for now; other TFL-only fields dropped (`visual_distance`, `object_scale_*`, `sound_pitch_*`, `maximum_vitality`, `melee_power`) | 17 Myth II-only header fields, defaulted from measurements of `Magma - The Fallen Lords v1.9`; `pathfinding_radius` has no honest single default (per-monster) and `more_hack_flags` is an unresolved tie -- see [NOTES.md](NOTES.md) section 16 |
| `unit` | **converts** | none -- byte-identical layout in both games (128 bytes; only the first 8, two tag references, are declared), only those references may need remapping | -- |
| `proj` | **converts** | TFL's 4 bytes at 76..80 dropped (meaning unknown); TFL flag bit 1 (thrown debris) cleared -- Myth II reads it as *guided* -- see [NOTES.md](NOTES.md) section 18 | zero references written as none |
| `scen` | **converts** | TFL words at 32..44 dropped (no Myth II destination) -- see [NOTES.md](NOTES.md) section 18 | netgame scoring type and flag number (0xFFFF) |
| `meef` | pass-through -- **blocks satchel charges and shade magic in-engine** | 32B vs 36B; Myth II adds a shockwave block with a collection reference | -- |
| `arti` | pass-through | 128B vs 168B | -- |
| `mesh` | **header + terrain + markers + map actions convert** | 6 TFL-only header fields dropped (`render_variables_tag`, `teams_*`, `annotation_*`); tag references inside map-action *parameter data* not yet remapped (marker-palette references are); terrain is upsampled nearest-neighbour (each TFL cell becomes a 2x2 block -- duplicated, never interpolated, so heights stay consistent with their normals); the media coverage region is dropped (empty is valid in 14 of 87 native meshes) | 38 Myth II-only header fields, defaulted from measurements of `Magma - The Fallen Lords v1.9`; per-cell `model_index` (none) and `media_height` (the "Water level" decision); `mesh_LOD_data` **zero-filled** at the new size -- its encoding is not understood |
| `mode` `geom` | pass-through -- **measured, converter not yet written** | `mode`: footprint cells must be split 2x2 (cells halve in size); `geom`: header grows 96B to 128B. Separately, the mesh's per-cell `model_index` (which cells a building covers) is written as "none" -- see [NOTES.md](NOTES.md) section 17 | `geom`: bounding box (derived from vertices); material tail and some surface flag bits unknown |
| `prgr` `lpgr` `core` `soun` `amso` `phys` `part` `medi` | pass-through | unverified whether these differ at all | -- |
| *(all types)* | header converts | TFL `tag_version` and `flags` dropped -- measured safe, see [NOTES.md](NOTES.md) section 9; `version` clamped if it exceeds int16 | `identifier` (unique, sequential), `type` (mirrors container), `flags`, `destination`, `owner_index` |
| *(container)* | header converts | TFL `checksum`, `mod_time` dropped | `checksum` and `header_checksum` **written as zero** -- algorithm unknown; `type`=`PLUGIN`; `version`=0 |

"Pass-through" means the body is copied byte-for-byte and the tag is reported as
unconverted. It is never silently presented as converted.

**Entrypoints are synthesised**, one per mesh tag, so converted levels appear in Myth II's
menu by name -- confirmed in-engine. Starting one still fails, for two separate reasons:

1. The pass-through bodies above (`arti`, `proj`, `prgr`, and the rest) are still in TFL
   format.
2. **A TFL plugin is not self-contained.** It references the stock TFL tag library the way
   a Myth II plugin references the base game. Counting mesh header fields, marker palette
   entries, and now `mons` header/sound/attack references and `unit` references too, the
   test plugin's tags point at 458 tags (4,148 references) they do not contain. Converting a
   plugin in isolation cannot fix that -- the stock tags have to come from a TFL installation
   supplied as a second input, or be mapped onto Myth II equivalents. See
   [NOTES.md](NOTES.md) sections 12-14, 16.

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
- **Only plugins with no entrypoints can be activated as tagsets.** A plugin with
  entrypoints is a *campaign*, and campaigns are single-select -- so two of them cannot load
  together. Stripping entrypoints with `src/writer.py` turns one into a tagset, which is how
  the stock-tag dependency problem below can be worked around.
- **Supplying the stock TFL tags does resolve the dependency problem.** With a converted
  TFL port loaded as a tagset, the missing-tag errors disappear and loading proceeds to the
  next layer -- a crash in the engine's `byte_swap_data` while reading the mesh's data
  blocks, which are still TFL-shaped. See [NOTES.md](NOTES.md) section 13.
- **Markers, marker-palette entries, and map-action headers need no format conversion at
  all** -- verified against a real, working 2011 community tool's source code as well as
  mythextract's own declared struct formats. The one genuine bug found: TFL's map-action
  parameter type numbering is missing a slot Myth II has, so every TFL type code from 12
  up is off by one -- a very plausible cause of the crash above. Fixed and validated
  against all 2,760 map actions / 7,942 parameters in the real test plugin. See
  [NOTES.md](NOTES.md) section 14.

## Layout

```
src/codec.py       minimal binary struct codec (lossless; preserves padding)
src/formats.py     container and tag header definitions, ported with citations
src/mesh.py        mesh headers, markers, marker palette, map actions
src/mons.py        mons/unit headers and attack definitions
src/fieldinfo.py   what mesh fields mean and what a sane value is (Fear manual)
src/reader.py      parse a TFL .gor or Myth II container
src/writer.py      pack one back -- the piece mythextract does not have
src/plan.py        the model: what a conversion would do, computed without doing it
src/decisions.py   the control: choices no measurement can settle
src/views/         the views: text report and shareable HTML page
src/convert/       per-tag-type conversion; tags/ holds the body converters
src/studio/        the guided local browser app
src/plugindiff.py  tag-by-tag comparison of two containers
src/cli.py         command line entry point
tests/             unittest suite; fixtures.py builds synthetic containers
reference/         third-party material we study but do not redistribute --
                   git-ignored except its README, which says how to get each item
NOTES.md           research notes on the reference implementation and the format
```

## Honest limitations

This tool will get a map most of the way, not all of the way. `text`, `stli` and
pass-through types are tractable. `mons`, `unit`, and every structural block of `mesh`
(header, terrain, markers, map actions) now convert; `arti` involves the same kind of real
format change with fields that have no TFL source and must be defaulted, and has not been
started. `mesh` is the hardest, and its terrain is the least certain part: the LOD data is
zero-filled because its encoding is not understood, and nothing since the terrain converter
landed has been tried in-engine.
Expect manual finishing work, and see [NOTES.md](NOTES.md) section 6 for the known unknowns.
The container checksums, once the biggest of those, turned out not to matter: nobody knows
the algorithm, but Myth II 1.8.5 validates neither field, so writing zeros works (see
*Verified in-engine* above).

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
