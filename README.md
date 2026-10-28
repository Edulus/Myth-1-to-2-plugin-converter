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

**Public beta.** Two levels from *Sir Mauriac's Tale* -- **Tandem** and
**In the Name of Glory** -- load, play and reach the end-game screen in Myth II
1.8.5, converted entirely by the tool. Other levels and multiplayer remain
unverified. See [NOTES.md](NOTES.md) sections 17-18.

The converter handles terrain, markers, map actions, monsters/units and their
objects, projectiles, artifacts, scenery, weather, mesh effects, lighting,
sprite collections, text and building models (`mode`/`geom`). Lighting uses
standard values for every map, terrain heights are blended onto Myth II's finer
grid, and some tag bodies (including sounds and projectile groups) pass through
unchanged. The support matrix below records those limits.

**Convert in your browser:** the project website has a *Convert a plugin* page.
Drop a TFL plugin on it and it converts inside the browser tab, with nothing
uploaded, and gives back a Myth II plugin with the stock tags it needs built in.
It runs this converter unchanged under [Pyodide](https://pyodide.org)
(`src/web.py` is its entry point, `web/convert/` holds the page's scripts, and
`scripts/keep_site.py` builds it). Checked in Chrome on Windows with *Sir
Mauriac's Tale*: about 5 seconds to convert, roughly 1.1 GB of browser memory,
and the result played *Tandem* on a clean Myth II 1.8.5 install.

Unless visitors untick a box (ticked by default), the plugin's name, level count
and converter version go on a public "Maps converted so far" list on that page. The list lives
in the comments service (`comments-worker/`, Cloudflare KV key `conversions`).
To remove an entry, from `comments-worker/`:

```powershell
npx wrangler kv key get conversions --binding VOTES --remote > conversions.json
# edit conversions.json: delete the unwanted entry
npx wrangler kv key put conversions --binding VOTES --remote --path conversions.json
```

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
packaged GitHub release yet.

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

In the app (`python -m src studio`), click **Swap units (Civil War)** at the top.
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
first. See [NOTES.md](NOTES.md) for the details.

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

## Tag type support matrix

| Tag type | Status | Known lossy fields | Myth II fields synthesised |
|---|---|---|---|
| `text` | **converts** | a literal `\` becomes `\|`; when followed by `i`/`b`/`p` it is indistinguishable from markup and no warning is possible | -- |
| `stli` | **converts** | as `text` | -- |
| `.256` | **converts** | none -- records shared; Myth II's data block gains 32 bytes (every internal offset moves) and TFL's saved runtime pointers are zeroed; 48 of 79 unedited Magma collections reproduce byte-for-byte -- see [NOTES.md](NOTES.md) section 18 | -- |
| `d256` | pass-through | body unconverted | -- |
| `mons` | **converts** | TFL-only fields dropped (`visual_distance`, `sound_pitch_*`, `melee_power`); scale, vitality and `effect_modifiers` move to the monster's own `obje` (below) | 17 Myth II-only header fields, defaulted from measurements of `Magma - The Fallen Lords v1.9`; `pathfinding_radius` has no honest single default (per-monster) and `more_hack_flags` is an unresolved tie -- see [NOTES.md](NOTES.md) section 16 |
| `unit` | **converts** | none -- byte-identical layout in both games (128 bytes; only the first 8, two tag references, are declared), only those references may need remapping | -- |
| `proj` | **converts** | TFL's 4 bytes at 76..80 dropped (meaning unknown); TFL flag bit 1 (thrown debris) cleared -- Myth II reads it as *guided* -- see [NOTES.md](NOTES.md) section 18 | zero references written as none |
| `scen` | **converts** | TFL words at 32..44 dropped (no Myth II destination) -- see [NOTES.md](NOTES.md) section 18 | netgame scoring type and flag number (0xFFFF) |
| `meef` | **converts** | TFL's word at 16 and constant at 10 not carried; no shockwave (TFL has none) -- see [NOTES.md](NOTES.md) section 18 | velocity, dissipation, camera shake, shockwave block (Bungie's own port of `wiex` and the 13 Myth II effects) |
| `meli` | **converts** | per-map intensities not carried yet: every stock TFL lighting tag converts to the same lighting -- see [NOTES.md](NOTES.md) section 18 | ambient/diffuse/model/total intensities, smoothing, filter (Bungie's base-game values) |
| `obje` | **converts**, and each monster gets its own | TFL bytes 6..16 (zero in stock) | scale, vitality and 9 effect modifiers -- from the monster for per-monster objects, 1.0 otherwise; TFL objects read unconverted made every unit and tree invisible (scale 0) -- see [NOTES.md](NOTES.md) section 18 |
| `part` | **converts** | none -- first 92 bytes shared | splash box (`box_width` etc.) from Magma's majority; a zero width crashed the engine -- see [NOTES.md](NOTES.md) section 18 |
| `arti` | **converts** | 128 zero padding bytes after the declared 128 dropped | 4 extra effect-modifier slots; all-zero TFL modifiers become 1.0 (Magma's untuned default) rather than immune -- see [NOTES.md](NOTES.md) section 18 |
| `mesh` | **header + terrain + markers + map actions convert** | 6 TFL-only header fields dropped (`render_variables_tag`, `teams_*`, `annotation_*`); tag references inside map-action *parameter data* not yet remapped (marker-palette references are); terrain is upsampled to a 2x2 block per TFL cell, with heights blended between neighbouring points and every other field copied, as in Project Magma's hand port of *The Fallen Levels v2*; the media coverage region is copied verbatim (its values are already on Myth II's scale) | 38 Myth II-only header fields, defaulted from measurements of `Magma - The Fallen Lords v1.9`; per-cell `model_index` (none) and `media_height` (the "Water level" decision); `mesh_LOD_data` **zero-filled** at the new size -- its encoding is not understood |
| `mode` `geom` | **convert** | `mode`: footprint cells split 2x2; `geom`: header grows 96B to 128B; model markers move from TFL's corner anchor to Myth II's centre anchor. The mesh's per-cell `model_index` stays "none" (the engine builds obstruction from the footprint, verified in-engine) -- see [NOTES.md](NOTES.md) section 17 | `geom`: bounding box (derived from vertices), `center_z` 0; material tail and extra surface flag bits left as TFL has them |
| `prgr` `lpgr` `core` `soun` `amso` `phys` `medi` | pass-through | unverified whether these differ at all (`core` matches Magma's layout; Tandem loads and plays with the rest unconverted) | -- |
| *(all types)* | header converts | TFL `tag_version` and `flags` dropped -- measured safe, see [NOTES.md](NOTES.md) section 9; `version` clamped if it exceeds int16 | `identifier` (unique, sequential), `type` (mirrors container), `flags`, `destination`, `owner_index` |
| *(container)* | header converts | TFL `checksum`, `mod_time` dropped | `checksum` and `header_checksum` **written as zero** -- algorithm unknown; `type`=`PLUGIN`; `version`=0 |

"Pass-through" means the body is copied byte-for-byte and the tag is reported as
unconverted. It is never silently presented as converted.

**Entrypoints are synthesised**, one per mesh tag, so converted levels appear
in Myth II's campaign menu. A TFL plugin still depends on the original game's
stock tags: use `tagset` above to provide them alongside the converted campaign.
The two tested levels finish; unsupported tag layouts can still affect others.

The container side is confirmed working: a plugin built by `src/writer.py` with
**both checksums zeroed** loads and plays in Myth II 1.8.5. See below.

## Verified in-engine

Current gameplay results are in [NOTES.md](NOTES.md) section 18: *Tandem* and
*In the Name of Glory* reach the end-game screen. Earlier container checks used
**Myth II 1.8.5 build 471b** and a real 102-tag plugin (section 11):

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
- **Converting the original stock TFL tags resolves dependencies that Magma's
  port did not supply under the original IDs.** The `tagset` command implements
  this workflow. Earlier failures and their fixes are recorded in NOTES sections
  13 and 18.
- **Markers, marker-palette entries, and map-action headers need no format conversion at
  all** -- verified against a real, working 2011 community tool's source code as well as
  mythextract's own declared struct formats. The one genuine bug found: TFL's map-action
  parameter type numbering is missing a slot Myth II has, so every TFL type code from 12
  up is off by one -- a suspected cause of an earlier loading crash. Fixed and validated
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
src/studio/        the guided local browser app (swapping.py: the Swap units page)
src/swap.py        swap the units a Myth II plugin's maps place; restore stock units
src/plugindiff.py  tag-by-tag comparison of two containers
src/cli.py         command line entry point
tests/             unittest suite; fixtures.py builds synthetic containers
reference/         third-party material we study but do not redistribute --
                   git-ignored except its README, which says how to get each item
NOTES.md           research notes on the reference implementation and the format
```

## Honest limitations

Only two single-player levels have been tested through to the end-game screen.
Lighting uses standard values, and terrain heights are blended between the
original points (no hand detail as in Magma's ports). Mesh LOD data is zero-filled because
its encoding is not understood. References inside map-action parameter data
are not yet remapped. Sounds, projectile groups, collection references and
other unsupported bodies are copied unchanged. Expect manual finishing work
and verify each level in-game; a passing file round-trip is not a gameplay test.
See [NOTES.md](NOTES.md) sections 17-18 and the support matrix above.

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
[NOTES.md](NOTES.md) documents what was taken from it, file by file, with citations at
each use site in the source.

Myth: The Fallen Lords and Myth II: Soulblighter are trademarks of their respective rights
holders. This is an unofficial, non-commercial interoperability tool, not affiliated with
or endorsed by any rights holder.

The swap tool was checked against *Civil War Reloaded 1.8.4* by PoinT of
ARMY Munitions Factory, which builds on work by IronDuke (Project Magma),
Cydonian, Thoran and others credited in its own readme. It is a third-party
plugin; nothing from it is included here.
