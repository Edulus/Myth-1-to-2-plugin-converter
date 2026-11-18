# myth-plugin-converter

Converts **Myth: The Fallen Lords (TFL)** plugin files into **Myth II: Soulblighter (SB)**
plugin files.

TFL and Myth II share a common tag architecture -- a monolithic container holding a header,
a tag directory, and concatenated tag bodies -- but differ in the tag header layout, the
container header layout, and in the internal layout of many tag bodies. This tool aims to
read a TFL monolith/plugin, rewrite the tags it contains into Myth II form, and **write out
a working Myth II plugin**.

Built on the research and format work in [jwheare/mythextract](https://github.com/jwheare/mythextract),
which provides the reading and single-tag-header conversion side of the problem. The
[documentation](documentation/README.md) folder holds what the converter does to each tag
type, the research notes behind every rule, and how the site and releases work.

## Status

**Public beta, converter 0.18 (17 November 2026).** Two levels from *Sir
Mauriac's Tale* -- **Tandem** and **In the Name of Glory** -- load, play and
reach the end-game screen in Myth II 1.8.5, converted entirely by the tool.
Testers have confirmed water, riverbanks, buildings, hosted multiplayer games
(units, scenery, flags and balls), the ground after explosions, and units that
stand still when they stop. Forest Giants, Trow and healers were fixed in 0.17
and 0.18 and are not yet checked in the game. Other levels are untested.

The converter handles terrain, markers, map actions, monsters/units and their
objects, projectiles, artifacts, scenery, weather, mesh effects, lighting,
ambient sounds, sprite collections, text and building models (`mode`/`geom`).
Lighting uses standard values for every map, and a few tag types (including
water definitions and projectile groups) are still copied unchanged.
[documentation/conversion-rules.md](documentation/conversion-rules.md) has the
rule for every tag type and what has been checked in the game.

**Convert in your browser:** the project website has a *Convert a plugin* page.
Drop a TFL plugin on it and it converts inside the browser tab, with nothing
uploaded, and gives back a Myth II plugin with the stock tags it needs built in.
It runs this converter unchanged under [Pyodide](https://pyodide.org)
(`src/web.py` is its entry point, `web/convert/` holds the page's scripts, and
`scripts/keep_site.py` builds it). Checked in Chrome on Windows with *Sir
Mauriac's Tale*: about 5 seconds to convert, roughly 1.1 GB of browser memory,
and the result played *Tandem* on a clean Myth II 1.8.5 install.

Unless visitors untick a box (ticked by default), the plugin's name, level count
and converter version go on a public "Maps converted so far" list on that page;
[documentation/site-and-releases.md](documentation/site-and-releases.md) says how
to remove an entry.

**Also in this beta:** a ready-made, already-converted *Sir Mauriac's Tale*
(a GitHub release, linked from the project website) that needs nothing else
installed, and a companion tool that swaps the units in the Civil War plugins'
maps for regular ones -- see [Swapping units](#swapping-units-civil-war-maps).

The container reader/writer also passed the historical byte-exact round-trip
gate on 282 real archives. This checks container preservation, not gameplay:

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

## Get started

Download this repository with **Code -> Download ZIP** and extract it, or:

```sh
git clone https://github.com/Edulus/Myth-1-to-2-plugin-converter.git
cd Myth-1-to-2-plugin-converter
```

You need Python 3.12+, Myth II 1.8.5, your own TFL game's `tags` folder
(`TAGS.GOR` and `ARTSOUND.GOR`), and an extracted TFL plugin (`.gor`). No game
data is included. No Python packages or build step are needed. There is no
packaged release of the converter itself.

On Windows, `launch.bat` finds Python or attempts to install it with winget,
then opens the studio. Follow its prompt to run it again after installation;
if winget is unavailable it opens the Python download page. The studio cannot
build the stock tagset, so use the terminal commands below first. On other
systems, install Python 3.12+ yourself.

**Quit Myth II first.** Open a terminal in the extracted repository folder
(the one containing `src` and `launch.bat`). In Windows File Explorer, open that
folder, type `powershell` into the address bar and press Enter. Replace the
example paths below with your own, keeping the quotes. If needed, replace
`python` with `python3` or, on Windows, `py -3.12`.

```sh
python -m src tagset --in "TFL/tags/TAGS.GOR" --in "TFL/tags/ARTSOUND.GOR" --out "Myth II/plugins/ZZ TFL stock"
python -m src convert --in "Sir Mauriac's Tale.gor" --out "Myth II/plugins/ZZ Mauriac"
```

Build the stock tagset once; convert each plugin separately. **No decisions
file is required for this baseline workflow.** Output files have no extension.
If the install folder is not writable, write to a folder you can access and
copy the results into Myth II's `plugins` folder while the game is closed.

Start Myth II: **New Game -> converted campaign -> Tagsets -> activate
ZZ TFL stock -> choose a level -> OK**. Select the tagset after the campaign:
changing campaigns can clear it. Only one campaign can load at a time; the
stock tagset has no selectable levels, so it can accompany the campaign.

- Restart Myth II after adding files, and quit it before replacing files.
- Output filenames must be at most 32 characters. Their internal names default
  to the output filenames; use distinct names to avoid hidden duplicates.
- Activate the stock tagset only for converted TFL levels: it overrides
  same-ID tags from Myth II while active.
- Conversion warnings matter. A readable output does not guarantee gameplay.

To report a problem, include the plugin and level, Myth II version, expected
and observed behaviour, and the end of `myth_log.txt`. For crashes, include
relevant lines from the newest `myth_crashlog- <date>.txt` too. Remove private
paths and share observations rather than game files. The
[project website](https://edulus.github.io/Myth-1-to-2-plugin-converter/)
has comment boxes that require no account.

## The app

**Windows:** double-click [`launch.bat`](launch.bat). See the setup instructions
above; its Python detection logic lives in [`scripts/launch.ps1`](scripts/launch.ps1).

**Already have Python (any OS):**

```sh
python -m src studio
```

Opens a guided app in your browser for converting an individual plugin. It does
**not** build the stock tagset; use `tagset` above first. Its missing-reference
suggestions do not validate the complete stock-tagset dependency chain. Built for someone doing this for
the first time: it explains what tags and plugins are, why a Fallen Lords plugin is not
self-contained, what each decision costs, and how to read the game's log when a level fails
to start. An **Expert** tab drops the hand-holding once you know the ropes.

Unlike `plan --html`, the studio can act -- browse for your files, find your Myth II
install, run the conversion, and write the plugin into your plugins folder.

It binds to `127.0.0.1` only, refuses cross-site requests, and requires a token minted at
startup and passed in the URL it prints. It reads and writes real files on your machine and
is not safe to expose beyond your own computer.

## Swapping units (Civil War maps)

A companion tool for the Civil War plugins (tested with *Civil War Reloaded
1.8.4* and the older *Fields of Battle* pack on the 1.7 tagset). Their maps place custom rank-and-role soldiers; this swaps them for
regular units you choose, such as warriors or ghols, and writes a new plugin.
The original is never changed.

You need the plugin that holds the **maps**, the **tagset** its units live in
(both from the Civil War download, which this project does not supply), and
your **Myth II folder**.

**In your browser, with nothing to install:** the [Swap Civil War units](https://edulus.github.io/Myth-1-to-2-plugin-converter/swap/index.html) page does the same job. Choose the maps, the tagset and your Myth II folder; the page reads them in place (nothing is uploaded), you pick the replacements, and it writes the new plugin for you to save. It was built because Obelix asked for it.

In the local app (`python -m src studio`), click **Swap units (Civil War)** at the top.
Give it those three paths, press *Read the maps*, then pick a replacement for each
unit -- or set the whole "yours" and "enemy" side at once -- and press *Write the
new plugin*. It lands in your `plugins` folder.

From the command line:

```sh
# What do the maps place?
python -m src swap --in <maps> --tags <tagset> --list

# Swap units. OLD and NEW are the 4-character ids shown by --list.
python -m src swap --in <maps> --tags <tagset> --myth2-dir "<Myth II>" \
    --out "<Myth II>/plugins/ZZ Swapped units" --swap @0sh=wam1 --swap +ash=ghol
```

**Why `--myth2-dir`.** The Civil War tagset redefines every one of Myth II's own
unit ids: in it, `wam1` ("warrior") is a Union veteran. So pointing a map at a
stock id is not enough. With `--myth2-dir` the tool reads the original unit tags
from your own install and carries them into the new plugin (only those the tagset
changed -- a few hundred bytes each).

**To play it:** in Myth II choose the new campaign *first*, then activate the
tagset under **Tagsets**. The new plugin has to load after the tagset.

**How far it is verified:** on a clean Myth II 1.8.5 install, real warriors and
ghols appeared on *Fort Sumter* (Civil War Reloaded 1.8.4) and on *Little Flat
Top* (the Fields of Battle pack, with the 1.7 tagset). Other maps, other
replacement units and other Civil War packs are untested. Use the tagset that
matches your maps: the 1.7 tagset for the 1.7 map packs, the 1.8.4 one for 1.8.4. The "yours" and "enemy"
shortcuts rely on that tagset naming its units with a leading `@` or `+`. Maps
unlock in order in the campaign list, so only the first levels are playable at
first. See [documentation/notes/unit-swapper.md](documentation/notes/unit-swapper.md) for the details.

## Usage

```sh
python -m src info <container>            # header, entrypoints and tag list
python -m src info --types <container>     # summarise by tag type
python -m src roundtrip <container|dir>... # verify read/write is byte-exact
python -m src diff <a> <b>                 # compare two containers tag by tag
python -m src plan --in <gor>                     # what a conversion would do
python -m src convert --in <gor> --out <plugin>   # do it
python -m src swap --in <maps> --tags <tagset> --list   # units a Myth II plugin's maps place
```

### Supplying the stock TFL tags

A TFL plugin is not self-contained: it uses the stock TFL tags the way a Myth II
plugin uses the base game. Convert them once, from your own TFL install's `tags`
folder, into a Myth II tagset:

```sh
python -m src tagset --in "TFL/tags/TAGS.GOR" --in "TFL/tags/ARTSOUND.GOR"     --out "/path/to/Myth II/plugins/ZZ TFL stock"
```

Where archives share a tag the first `--in` wins. The result has no entrypoints
-- Myth II only offers entrypoint-free plugins as tagsets -- and carries its own
internal name (Myth II identifies plugins by it, and two with the same name hide
one another). In Myth II: New Game, choose the converted campaign, then
**Tagsets**, and activate it. Choosing a campaign clears the tagset selection, so
check the log line `Starting mesh ... with 2 plugins` if a level reports missing
tags.

Or skip the tagset: `convert --stock "TFL/tags/TAGS.GOR" --stock "TFL/tags/ARTSOUND.GOR"`
builds the stock tags into the plugin itself, so it needs nothing else installed.
Only the stock tags the plugin uses go in (*Sir Mauriac's Tale*: 293 MB instead of
419 MB, verified in-engine); add `--all-stock` to carry every one.

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

## What is converted

[documentation/conversion-rules.md](documentation/conversion-rules.md) lists, for
every tag type, whether it converts, what is lost or changed, and which Myth II
fields the converter fills in, each with the measurement behind it. It also
lists what has been checked in the game. In short:

- Converted: maps (header, terrain, markers, map actions), monsters and units
  with an object of their own each, projectiles, scenery, artifacts, particle
  systems, mesh effects, lighting, ambient sounds, sprite collections, building
  models, text.
- Copied unchanged ("pass-through", always reported as such): `prgr`, `core`,
  `soun`, `phys` (measured: no systematic difference from Myth II's copies), and
  `lpgr`, `medi`, `ligh`, `wind`, `d256`.
- Container checksums are written as zero: Myth II 1.8.5 validates neither.
- Entrypoints are synthesised, one per map, so converted levels appear in the
  campaign menu.

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
src/studio/        the guided local browser app (swapping.py: the Swap units page)
src/swap.py        swap the units a Myth II plugin's maps place; restore stock units
src/plugindiff.py  tag-by-tag comparison of two containers
src/cli.py         command line entry point
tests/             unittest suite; fixtures.py builds synthetic containers
reference/         third-party material we study but do not redistribute --
                   git-ignored except its README, which says how to get each item
documentation/     conversion rules, research notes, the site and releases, plans
```

## Honest limitations

Only two single-player levels have been tested through to the end-game screen.
Lighting uses standard values, and terrain heights are blended between the
original points (no hand detail as in Magma's ports). References inside
map-action parameter data are not yet remapped. Water definitions, projectile
groups and a few other types are copied unchanged. Expect manual finishing work
and verify each level in game; a passing file round-trip is not a gameplay test.
See [documentation/conversion-rules.md](documentation/conversion-rules.md).

## Game data

The converter's code, tests and fixtures contain no game data, and `.gitignore`
keeps game files out. There are two deliberate exceptions, both so that players
need nothing else installed:

- The project website's in-browser converter serves the *Myth: The Fallen Lords*
  stock tags (`TAGS.GOR` and `ARTSOUND.GOR`, split into pieces) from
  `docs/convert/stock/`, and bundles the ones a plugin uses into its output.
- The ready-made *Sir Mauriac's Tale* release carries those stock tags inside
  the plugin.

Neither Civil War download is supplied. The website also shows credited artwork
and a testing screenshot. Tests read from paths supplied at runtime and skip
when absent. When running the tool yourself, you supply your own legally
obtained Myth installation.

## License and credits

MIT -- see [LICENSE](LICENSE).

This project would not exist without [jwheare/mythextract](https://github.com/jwheare/mythextract)
(MIT, © 2025 James Wheare), which is the source of the format research this builds on.
[NOTICE](NOTICE) records the attribution and the trademark position;
[documentation/notes/prior-art.md](documentation/notes/prior-art.md) documents what was
taken from it, file by file, with citations at each use site in the source.

Myth: The Fallen Lords and Myth II: Soulblighter are trademarks of their respective rights
holders. This is an unofficial, non-commercial interoperability tool, not affiliated with
or endorsed by any rights holder.

The swap tool was checked against *Civil War Reloaded 1.8.4* by PoinT of
ARMY Munitions Factory, which builds on work by IronDuke (Project Magma),
Cydonian, Thoran and others credited in its own readme. It is a third-party
plugin; nothing from it is included here.
