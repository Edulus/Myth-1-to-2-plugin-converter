# Maps: mesh header, terrain, markers, map actions

**Where this stands (17 November 2026).**

- *Header*: converted field by field (§12); map header version 7 becomes 11 (§24).
- *Terrain*: each TFL cell becomes a 2x2 block of Myth II cells, heights blended
  between the original points, other fields copied (§15, §20); cell flags
  translated by table (§23); ground lowered beside models where TFL's corners
  step down to the model's base (§22).
- *Edges*: edge-of-mesh buffer widths doubled (§21).
- *Markers and map actions*: same layout in both games; map-action parameter
  types from 12 up shift by one (§14); scenery and unit markers set onto the
  ground (§20); model markers moved from corner to centre anchor (§17, in
  [models.md](models.md)).
- *Water*: the media coverage block is copied (§20).
- *Level of detail*: written as `00f0` words, as Loathing does (§27). Keep
  confirmed on 0.16 that the black ground after explosions is gone.
- *Still open*: tag references inside map-action parameter data are not remapped
  (§14; improvement plan item A3).

## 12. Mesh headers, entrypoints, and the dependency problem

### Mesh header port, validated against real data

`src/mesh.py` ports `MeshHeaderFmt` and `MeshHeaderFmtTFL`. Both are 1024 bytes, which is
what makes them dangerous: the same offset means different things in the two games. The
divergence starts at offset 76 (TFL `render_variables_tag` / Myth II `connector_tag`) and
the layouts never re-converge — TFL has `teams_*` and `annotation_*` blocks where Myth II
has lighting colours, and Myth II adds reverb, connectors, cutscene filenames, fog and
narration fields where TFL has 730 bytes of padding.

Validated by measurement rather than by fixture: for every entrypoint in the Myth II
corpus, the printable level name was derived from the mesh's
`map_description_string_list_tag` and compared against what the plugin actually ships —
**667 exact matches, no mismatches**. The 32 non-resolving cases are meshes whose string
list lives in a different archive. The TFL side was checked against the test plugin: all
73 meshes resolve their description string list, yielding real level names.

### Entrypoint synthesis, measured not guessed

Across 703 entrypoints in 166 real plugins: every `entry_id` resolves to a `mesh` tag in
the same container, every `entry_name` equals that mesh tag's name exactly, and the
entrypoint count equals the mesh count in all 166. So it is **one entrypoint per mesh**,
ID and name lifted from the mesh tag, with only the printable name coming from the
description string list.

Confirmed in-engine: the converted test plugin lists all 25 of its single-player levels in
Myth II's New Game screen by their correct names, including markup converted from TFL's
`\i` to Myth II's `|i`. The other 48 meshes are multiplayer maps, which is why they do not
appear there.

### The dependency problem — the real blocker

> **Update:** solved by converting the stock TFL tags themselves (§18 in [stock-tags.md](stock-tags.md)): `tagset` builds them into a tagset, `convert --stock` into the plugin. `meli` now converts too.

Starting a converted level fails. The engine log is precise:

```
Starting mesh "Tandem" with 1 plugin...
Error: couldn't read header for media definition 'mawa'.
Error: mesh definition postprocess failed on 'zm04 - zm22 - bstm - bstm'.
```

`medi.mawa` is not a format problem. **It is not in the plugin at all**, and never was.

**A TFL plugin is not self-contained.** It references the stock TFL tag library the way a
Myth II plugin references the base game's. Walking the mesh headers of the test plugin
finds 84 distinct referenced tags that the plugin does not contain:

| Where the missing tag lives | Count |
|---|---:|
| Nowhere on this system | 50 |
| The Magma TFL→Myth II port plugin | 24 |
| Myth II's own core install | 10 |

So converting a TFL plugin in isolation cannot produce a working plugin, no matter how
good the body converters get. The stock tags it depends on have to come from somewhere:

1. **A TFL installation as a second input.** The honest fix, and what mythextract's
   `loadtags.py` is built for — resolve the plugin against the game directory, then convert
   the referenced stock tags too. Requires TFL game data, which is not on this machine.
2. **Target an existing TFL→Myth II port as a required tagset.** The Magma port already
   contains 24 of the 84 under their *original TFL IDs*, so they resolve with no remapping
   at all. Cheaper, but the output then depends on a third-party plugin.
3. **Map TFL stock IDs onto Myth II equivalents** where one exists — this is what
   `src/idmap.py` is for, and what the remaining 50 would need.

With the Magma port loaded, several levels drop to a **single** unresolved tag, always mesh
lighting (`meli.deml` for 59 meshes, `meli.mo#1` for 8). Myth II ships 25 distinct `meli`
tags, all 64-byte bodies, so a mapping is plausible — though picking one is an aesthetic
judgement about lighting, not a correctness one, and belongs in `idmap` as an explicitly
lossy substitution.

Note this is orthogonal to body conversion: the 73 meshes, 17 `mons` and 90 `.256` tags
that *are* in the plugin still need their bodies converted regardless. The dependency
problem blocks end-to-end testing, not the remaining Phase 3 work.

## 13. In-engine experiment 2 — dependencies resolve; mesh sub-blocks do not

Myth II 1.8.5 build 471b, converted *Sir Mauriac's Tale* plus a stock-tag tagset.

### Only plugins without entrypoints can be tagsets

The New Game screen's `Tagsets` dialog lists nothing matching "fallen", even though
`Magma - The Fallen Lords v1.9` is installed. Its 40 entrypoints make it a *campaign*, and
the Campaign list is single-select, so two entrypoint-bearing plugins cannot load together.

The workaround is one line with our own tools: read the port, drop its entrypoints, pack it
back out.

```python
m = reader.read(port_path)
m.entrypoints = []
writer.pack(m, preserve_layout=False)
```

The result — 2,110 tags, 328 MB — is offered by the game as a tagset and loads. That is
also a useful independent check on `src/writer.py`: it rebuilt a third-party 320 MB
container with a structural change and the engine accepted it, banner artwork and all.

### Dependency resolution works

With that tagset active alongside the converted plugin, the log shows both loading:

```
Starting mesh "Wild River" with 2 plugins...
	ZZ TFL stock tagset
	ZZ Mauriac TFL2SB
```

and **the `couldn't read header for media definition 'mawa'` error is gone**. Supplying the
stock TFL tags from a converted port resolves the §12 dependency problem. Route 2 is viable.

### The next blocker: mesh sub-block layout

> **Update:** resolved by the map-action type fix (§14), terrain upsampling (§15, §20) and, later, the level-of-detail block (§27).

It now crashes deeper in:

```
Myth Crashed: EXCEPTION_ACCESS_VIOLATION
 0 __byte_swap_data + 0x0089 (corelibrary\cseries\byte_swapping.c:187)
 1 _byte_swap_data + 0x000d (corelibrary\cseries\byte_swapping.c:72)
 2 _initialize_mesh_for_new_map + 0x0102 (myth2code\mesh.c:447)
 3 _initialize_myth_for_new_map + 0x0180 (myth2code\myth.c:515)
```

Myth stores tags big-endian and byte-swaps them on load, driven by a per-structure format
description. A fault *inside* `byte_swap_data`, reached from `initialize_mesh_for_new_map`,
means the engine is walking the mesh's data blocks with Myth II's field description over
TFL-shaped bytes and running off the end.

This is exactly the scope `src/convert/tags/mesh.py` declines to handle and reports: the
1024-byte header is converted, everything after it — terrain, marker palette, markers, map
actions, media coverage, LOD data — is copied verbatim. The crash confirms that is not
merely lossy but fatal, and identifies the mesh body sub-blocks as the next piece of work.

Progression across the two experiments is worth noting as a method: each fix moved the
failure one layer deeper and the engine named the layer each time. The log is a better
oracle than any amount of static analysis of the format.

## 14. Markers, marker palette, and map actions — from a 2011 community tool

The user found and shared [Iron's Mesh Converter](https://tain.totalcodex.net/items/show/mesh-converter-mac-and-windows-w-source-code)
(Mac and Windows binaries, released with source, uploaded 2011, 1,481 downloads).
Its README documents a fully manual TFL-to-Myth-II mesh porting workflow —
rebuild the terrain and the unit/scenery/model lists by hand in each game's
level editor ("Loathing"), matching them exactly, then run a small C program
that splices the TFL mesh's markers and map actions into the freshly-built
Myth II mesh. Both the Mac (`converter.c`) and Windows (`winconverter.c`)
source files are included and are near-identical.

This is source code that shipped real, playable ported levels (the author
references completing "the second TFL Mappack"), and it is the only place
this project has found an actual **working** implementation of the mesh
body conversion this tool has been missing. Cross-referenced against
mythextract's own struct declarations and doc examples before trusting any
of it — three independent sources agreeing is a much stronger basis than
one 13-year-old hobbyist tool with a README that says "sometimes it gets it
horribly wrong."

### Markers, marker palette entries, and map-action heads need no conversion

All three are the **same size and field layout in TFL and Myth II** —
unlike the mesh header itself (§4), which is the same size but different
layout, this is the first mesh sub-structure found to be genuinely shared.
Verified three ways:

* mythextract declares one `MarkerHeadFmt` (64 bytes), one
  `MarkerPaletteEntryFmt` (32 bytes), and one `ActionHeadFmt` (64 bytes) —
  no TFL variant of any of the three, and no game-version branch when
  reading them.
* Both the Mac and Windows converter tools copy all three wholesale —
  `fwrite(tfl_data + tfl_header.markers_offset + 1088, ...)` — with no
  per-record field remapping at all.
* The byte sizes match exactly by direct calculation from both mythextract's
  field lists and the tools' C structs (`struct marker_data` = 64 bytes,
  `struct m2_marker_palette_entry` = 32 bytes, `struct map_action` = 64
  bytes).

Ported into `src/mesh.py` as `MarkerHead`, `MarkerPaletteEntry`,
`MapActionHead` — one struct each, no `_TFL_` variant needed, the first
mesh sub-structure in this project not to need one.

### A structural discovery this project had missed: offsets don't need to move at all

Both community tools spend most of their code recomputing offsets
(`insert_section`, `data_size +=`, `if X_offset >= Y_offset: X_offset +=
size`) because they are **splicing TFL data into a separately-built Myth II
mesh** that started with different section sizes. That entirely doesn't
apply to this project: we convert one mesh's header in place, and every
offset stored in it (`markers_offset`, `marker_palette_offset`,
`map_actions_offset`, ...) is already a `SHARED_FIELDS` entry copied
verbatim by the existing header converter, unchanged. Since the header is
1024 bytes long in both formats and offsets are body-relative (§3), the
trailing data literally never has to move. This makes the actual fix here
much smaller than the two community tools' offset-juggling code would
suggest — it is a surgical patch of specific bytes in place, not a splice.

### The real bug: TFL's ParamType numbering is missing a slot

This is very likely a direct cause of the `EXCEPTION_ACCESS_VIOLATION`
inside `byte_swap_data` from §13. Both community tools independently
implement a fixup that increments certain map-action parameter type codes
by one when converting from TFL, triggered on TFL raw values 13-19
generally and specifically on raw value 12 when the parameter's 4-character
name matches one of eleven geometry-related names (`wayp`, `cent`, `deci`,
`line`, `grce`, `poly`, `poin`, `focu`, `dest`, `pnts`, `radi`).

mythextract's own **read-side** handling of this (`parse_map_actions`,
`scripts/mesh_tag.py:1285-1296`) gives the complete, principled version of
the same fact, and is what `src/mesh.py:resolve_param_type` ports:

```python
tfl = (game_version == 1)
if param_type == ParamType.PROJECTILE_OR_WORLD_POINT_2D:      # raw 12
    param_type = ParamType.WORLD_POINT_2D if tfl else ParamType.PROJECTILE
if tfl and param_type == ParamType.WORLD_RECTANGLE_2D:         # raw 14
    param_type = ParamType.OBJECT_IDENTIFIER
if tfl and param_type == ParamType.MODEL_IDENTIFIER:           # raw 16
    param_type = ParamType.SOUND_SOURCE_IDENTIFIER
if tfl and param_type == ParamType.WORLD_POINT_3D:              # raw 18
    param_type = ParamType.LOCAL_PROJECTILE_GROUP_IDENTIFIER
```

In plain terms: Myth II's `ParamType` enum has a slot for a standalone
`PROJECTILE` element type (value 12, named `PROJECTILE_OR_WORLD_POINT_2D` in
mythextract precisely because of this ambiguity) that TFL's enum does not
have. Every TFL code from 12 upward therefore means something one position
earlier than the same numeric code means in Myth II. Cross-checked directly
against `docs/ActionParamElementFormat.txt`'s own worked example: type 13,
field name `wayp`, is documented as `WORLD_POINT_2D` — exactly the target
the community tools' `type++` fixup produces from TFL's raw 12.

This is a materially better fact than what either community tool
implements: their field-name whitelist for the raw-12 case is incomplete by
their own admission ("sometimes it gets it horribly wrong"), whereas the
rule above requires no whitelist at all — it is a direct function of the
raw type code alone.

**Nothing about the underlying data changes.** The scale factors, byte
widths, and element counts for every parameter type are identical between
the games (confirmed against all three of `docs/ActionParamElementFormat.txt`'s
worked examples). Converting a parameter is therefore never a matter of
re-encoding values — only of correcting **which 2-byte type code sits in
front of already-correct data**, so `src/mesh.py:convert_tfl_map_actions`
walks the parameter stream (correctly computing each parameter's byte
length via `param_data_length`, itself ported from mythextract's own sizing
rules) and rewrites only that one field per parameter, in place.

### Marker palette: the natural point to apply ID remapping

A marker's actual tag reference lives one level removed — on the *palette
entry* its `palette_index` points at (`marker_tag`, a plain 4-byte tag id),
not on the marker record itself. `src/mesh.py:remap_marker_palette` applies
the plugin's `id_map` here, exactly the same substitution mechanism already
used for the top-level tag directory and mesh header fields. This also
means `unresolved_references()` in `convert/plugin.py` was undercounting:
it previously only walked mesh *header* fields. Extended to also walk each
mesh's marker palette, the real test plugin's honest reference count goes
from 84 tags (582 references, header fields only) to **383 tags (4,006
references, headers + palettes)**. That is not a regression — the
dependency was always there; the tooling simply could not see most of it
until now.

### Validated against the real plugin, not just synthetic fixtures

Every one of the 73 meshes in the 93 MB test plugin was walked with the new
code: **2,760 real map actions, 7,942 real parameters, 4,068 real marker
palette entries, zero parse errors, zero "unrecognised type" warnings.** 589
of those 7,942 parameters carried a TFL raw type of 12 or 14 and needed the
shift; the fix changed exactly 589 bytes (the low byte of a big-endian
`uint16` going from 12→13 or 14→15 never touches the high byte) and nothing
else. No parameter in this plugin used raw 16 or 18, so
`MODEL_IDENTIFIER`→`SOUND_SOURCE_IDENTIFIER` and
`WORLD_POINT_3D`→`LOCAL_PROJECTILE_GROUP_IDENTIFIER` remain validated only
against mythextract's documented rule, not against real bytes from this
particular plugin.

### Still not done

> **Still open** (17 November 2026): improvement plan item A3.

Tag references *inside* map-action parameter **data** (a `SOUND`- or
`PROJECTILE`-typed parameter's element bytes, per `PARAM_TYPE_TAG` in
`src/mesh.py`) are not yet remapped through `id_map` — only the marker
palette's references are. That is a data-completeness gap, not a
structural one: the type-code fix above is what should stop the crash;
finishing ID remapping inside action parameters is follow-up work toward a
fully self-contained conversion, using the same `PARAM_TYPE_TAG` mapping
already ported and ready for it.

## 15. The Fear and Loathing manuals — the terrain question, answered

The user supplied the official Myth II editor manuals: **Fear** (the tag editor)
and **Loathing** (the map editor), v1.8.5, as saved HTML. These are the primary
authority on what every tag field *means*, as opposed to how it is laid out —
which is the one thing neither mythextract nor the community converter source
could tell us.

**They are copyright 1998 Bungie Software / Tyson (Ferrex) Green, distributed by
Project Magma.** They are git-ignored (`*Documentation*.html`) and never
committed, on the same principle as game data: read locally, cite here, do not
redistribute. Everything below is a fact learned from them, not a copy of them.

### The terrain resolution question is settled

§13 left an open question: is Myth II's 32×32-cells-per-submesh a genuinely
finer grid, or just different bookkeeping over the same cells? The manuals plus
one measurement settle it.

Loathing, on the basic unit of map size:

> "A submesh is a 256x256 pixel section of the mesh. This is the basic unit of
> size for mesh tags, and as such, all meshes must have dimensions that are a
> multiple of 256 pixels."
>
> "A submesh is a 256x256 unit. Therefore, a 1792x1792 size map would have
> forty-nine submeshes (7x7)."

So one submesh is 256×256 colormap pixels in Myth II. Myth II puts 32×32 cells
in that space (8 pixels per cell); TFL puts 16×16 (16 pixels per cell).

The measurement that closes it: **marker world-coordinate extents are identical
between the two games for the same submesh dimensions.** Comparing the test
plugin's TFL meshes against Myth II's own campaign meshes from `small install`:

| Submeshes | TFL mesh | extent (world units) | Myth II mesh | extent (world units) |
|---|---|---|---|---|
| 3×3 | `cp00` | x 6.6–92.5 | `00 Training Map` | x 6.0–92.1 |
| 5×5 | `apev` | x 5.0–152.3 | `08 library` | x 1.7–153.8 |
| 7×6 | `FX#1` | x 5.0–221.7 | `01 village` | x 3.1–215.5 |

One submesh spans **32 world units in both games**. Therefore:

* Myth II: 32 cells per submesh ÷ 32 world units = **1 cell per world unit**
* TFL: 16 cells per submesh ÷ 32 world units = **1 cell per 2 world units**

**Conclusion: Myth II has genuinely double the linear cell resolution (4× the
cells) over an identically-sized map.** Converting TFL terrain therefore requires
real upsampling — each TFL cell becoming a 2×2 block of Myth II cells — not a
relabelling. Four independent lines of evidence now agree: the measured
`mesh_size` formula (§13), the community converter's
`SUBMESH_WIDTH_BITS` 4-vs-5 comment (§14), the Loathing manual above, and the
marker extents here.

A useful corollary: because the world-coordinate extent is unchanged, **marker
positions need no rescaling** — which is exactly why Iron's converter can copy
markers verbatim and have them "land in their exact original positions".

### The world unit was halved between the games — a flag for the unit converters

Fear, in the lightning tag section, explaining a bug Bungie left behind:

> "When Bungie made myth 2 they halved the size of a world unit as part of making
> the mesh more detailed. Most values throughout the game, such as unit and
> projectile speeds, were doubled to take this into account. They forgot,
> however, to look at the lightning code."

This independently explains Iron's otherwise cryptic workflow instruction —
*"Set the height parameters to double what TFL Loathing had"* — and is the
strongest hint yet about what `mons`, `unit` and `proj` conversion will involve:
**TFL gameplay values (speeds, ranges, distances) plausibly need doubling**, not
merely re-laying-out.

Deliberately **not** acted on yet, and worth stating why. Two measurements
suggest it does *not* apply to mesh data:

> **Update:** checked in §16 ([units.md](units.md)): `mons` distances and speeds are not doubled in Magma's ports, so they are copied.

* Marker coordinates are numerically compatible as stored (table above), and the
  community tool relies on exactly that.
* Raw terrain heights occupy comparable ranges in both games — TFL meshes span
  roughly −1,992…5,080, Myth II's own campaign meshes −3,344…5,799 — rather than
  Myth II's being systematically doubled.

So the doubling appears to be about gameplay statistics inside unit/projectile
tags, not about coordinates in mesh tags. Since the precise physical-scale
semantics are not yet pinned down, this is recorded as a lead for the `mons`/
`proj` converters to verify empirically, not as a rule to apply.

Fear also notes a related gameplay divergence worth remembering for `mons`:
Myth II introduced elevation-dependent missile range ("your archers can only
shoot 20 world units? Wrong. Put them on a high hilltop…"), where "In TFL this
was not the case — maximum range was maximum range."

### The manuals grade our synthesised mesh defaults

§12 chose 38 Myth II-only mesh header values by measuring a community port. The
manuals give those fields meaning, and mostly vindicate the measurements:

| Field | What Fear says | Our default | Verdict |
|---|---|---|---|
| Dark Color Fraction | "1.00 results in maximum color, while numbers in the 0.75 to 0.9 range are more common" | 229 (≈0.90 of 255) | in the documented range |
| Light Color Fraction | "usually much smaller than the Dark Color Fraction, in the 0.10 to 0.50 range" | 25 (≈0.10 of 255) | at the documented floor |
| Transition Point | "the zero point — the illumination level at which there is no lightening or darkening on the mesh" | 62259 | **correction**: a global brightness control, *not* terrain-derived as our comment claimed. Rightly flagged `CHECK` |
| Ceiling Height | "the height of the ceiling in world Units. This number is **ignored if the Has Ceiling flag is not checked**" | 2048 | de-risked — inert on most maps |
| TFL Min/Max Version | "the minimum/maximum version of the TFL gameplay (vTFL/Unity) patch that this mesh supports" | 0 | documents what our `use_vtfl` option is actually talking to |
| Minimum Player Zoom | "Valid range is between −5.0 and −0.99998" | 0.0 | outside the stated range, but measured 40/40 and the field is 1.8.2+, so 0 reads as "unset" |

### What else is in them

Fear's *Section III: Tag Specific Documentation* is a field-by-field reference
for **every** tag type this project still has to convert — `mons`, `unit`,
`proj`, `prgr`, `lpgr`, `core`, `soun`, `amso`, `phys`, `scen`, `part`, `medi`,
collections, and the rest. Loathing's covers the map editor's own model of
meshes, markers, passability and map actions.

That makes them the natural reference for the remaining tag-body converters:
mythextract gives the byte layout, the community tool gives worked conversion
logic, and these manuals give the semantics needed to know *which* fields
actually matter and what a sane value looks like.

### Folded back into the application

`src/fieldinfo.py` carries this knowledge as data — one entry per synthesised
mesh field, with the label Fear's own editor uses, a short summary in our words,
the scale factor the value is stored in, and the typical range where the manual
states one. Every view reads from it, so the CLI report, the decisions file and
the studio all explain the same thing the same way.

The concrete difference this makes: a user reviewing a conversion used to be
shown `transition_point = 62259` and asked to judge it. They are now shown

> **Transition Point** — the lighting zero point: the illumination level at which
> the mesh is neither lightened nor darkened. Lower makes the whole map brighter,
> higher makes it darker.
> `62259` means **0.95 of 1.0**.

`fieldinfo.check` additionally compares a value against the manual's stated
range and says so when it falls outside — advice, not enforcement, since an
unusual map may well want an unusual value. Run against our own measured
defaults, exactly one trips it: `light_fraction` at 0.098 sits a hair under the
manual's 0.10 floor, because that is what 38 of the reference port's 40 meshes
actually ship. A real disagreement between documentation and practice, now
visible rather than buried.

## 20. Benchmarking against *The Fallen Levels v2* — water fixed

KEEP's play-test of *Sir Mauriac's Tale* reported water not acting as water,
blocky heights, and no 3D models, and proposed a yardstick: Project Magma's
faithful port of the TFL solo levels, *The Fallen Levels v2*
(projectmagma.net/downloads/TFL_Solo/, kept in the git-ignored `local/`).
KEEP asked for v2 specifically; the `Magma - The Fallen Lords v1.9` used in
earlier sections is a different, later product.

*Crow's Bridge* is TFL `mesh.ambu` and the port's `mesh.30cb`. Both are 6×5
submeshes (TFL 96×80 cells, Myth II 192×160). Our conversion against the port,
cell by cell:

| | Ours | Port |
|---|---|---|
| Media coverage block | dropped (0 bytes) | 7,668 bytes |
| Heights identical | 5,887 of 30,720 (19%) | — |
| Height range | −1,020 to 2,070 | −3,072 to 2,064 |
| Cells with a model index | 0 | 916, 22 distinct |
| Per-cell media height | 0 everywhere | 0 everywhere |

### Media coverage is not resolution-dependent

The converter had dropped the media coverage region as "resolution-dependent
and not understood". It is neither a problem nor grid-sized: TFL's block is
7,810 bytes and the port's 7,668, both runs of 6-byte records
(`00 3b 00 b6 06 00`, ...) whose values already count on Myth II's scale (up to
182 on a 192-cell-wide map). The port's block is TFL's re-traced: 77.5% of
bytes match in sequence, and the differing records are off by 1 in the second
value or one record added or dropped.

So the block is now copied verbatim (`src/convert/tags/mesh.py`). In-engine, on
a clean 1.8.5 install, *Tandem*: before the change units walked on top of the
river; after it they slow down and wade with the water at their thighs.

### Heights are blended, not copied

The scale was never wrong. At the original TFL points (every second cell each
way) the port's heights fit ours at 0.996× with r = 0.9965, and the median
ratio is 0.98. The difference is the cells in between: we copied each TFL cell
into a 2×2 block, and the port sets them halfway between their neighbours (mean
gap to the neighbours' average 5.8, against 38.0 to the nearest original
point). The "three times deeper" range is 43 cells at −3,072, hand edits in the
port, not a rule.

The normals are copied in the port, not blended or recomputed. At the
in-between cells copying is closer to the port than blending (mean gap 7.3
against 8.0, and 4.4 against 7.2). So `upsample_terrain` (`src/mesh.py`) now
blends heights only, rounding down, with the last row and column kept level, and
copies every other field. Crow's Bridge against the port:

| | Before | After |
|---|---|---|
| Mean height gap | 48.3 | 21.4 |
| Median height gap | 16 | 10 |
| Within 16 of the port | 50% | 72% |

What is left is mostly hand work in the port: 785 cells still differ by more
than 64.

### Scenery and units sit on the ground

With blended heights, plants floated on *On the road to Strand*. A marker's
`pos_z` is an absolute height that Myth II draws at; TFL seems to have
ignored it for scenery and units. Ours kept TFL's values, within 4 of our
ground for only 71 of 274 scenery markers on Crow's Bridge. The port's sit on
its ground: 240 of 273 scenery and 96 of 108 units, and both observers.
Ambient sounds, models and projectile groups are not re-seated.

The port's heights reveal how Myth II reads its ground: each cell is two
triangles, split from top-left to bottom-right where column + row is even and
the other way where it is odd. That rule puts 99.2% of the port's scenery and
units at their stored height within 1, and all within 3. A single split
direction misses by up to 45, a bilinear blend by up to 21.

So `place_markers_on_ground` (`src/mesh.py`) now sets every observer, scenery
and unit marker to the ground under it. In-engine, the floating plants on
*On the road to Strand* came down. One bush on the lip of a steep trench still
looked raised, possibly its shadow falling down the wall; not yet checked from
the side.

### Open

- **Heights**: check the blended ground in the game.
- **The trench-edge bush** on *On the road to Strand*: floating, or a shadow?
- **3D models**: the port stamps model indexes into 916 cells (§17).
- **Units**: KEEP asks that the port's units be used to correct ours
  (walking in place, giants not attacking, sizes), with some licence to adopt
  the port's proven units, including for vTFL mode.

> **Update:** Keep checked water, riverbanks and heights on 0.9 and saw no problems. Models were converted (§17). Units were corrected against the ports in §28-§32 ([units.md](units.md)). The trench-edge bush is still unchecked.

## 21. A crash at the map's edge -- ground tiles and edge borders

KEEP reported a hard crash on crazyglue's *Along the way to...* (Crow's Bridge)
when scrolling along its south-west edge, in `_build_mesh_tile_texture`
(`render_maps.c`). Reproduced on the clean 1.8.5 copy (build 471b, DirectX 11)
with the 0.6 converter; with the two changes below, the same scroll does not
crash. Which of the two stops it was not isolated.

### A landscape keeps only its tiles

A level's landscape (`.256` named by the mesh's `landscape_collection_tag`) is
the only kind of collection with no sequences: all 34 in the stock TFL tags.
Each is two 256x256 tiles per submesh, in TFL and in *The Fallen Levels v2*
alike (Crow's Bridge, 6x5 submeshes: 60). Seven TFL landscapes end with one
more, smaller bitmap: `ambu` 153x128, `rend`/`de#1`/`mutr` 149x128, `balo`
256x128, `dehc`/`fore` 256x116. Magma's port drops it from every one it ports.
It is not the minimap: that is its own collection (`01om` for Crow's Bridge).

`src/convert/tags/collection.py` now drops bitmaps after a no-sequence
collection's run of 256x256 tiles, if none of them is a tile. Only the
reference count and section size change; the bytes stay, unreferenced, so no
offset moves. Of the 307 stock collections, exactly those seven change.

### Edge-of-mesh buffer zones count cells

`edge_of_mesh_buffer_zones` is four 16-bit widths in cells. Magma's are about
twice TFL's (Crow's Bridge 16/16/13/18 becomes 32/36/26/32; Marsh 2's 74
becomes 150); all 47 native Myth II meshes keep at least 16. Copied unchanged,
converted borders were half as wide, as narrow as 5 cells. The mesh converter
now doubles them.

**The order is not swapped (16 Nov).** Crow's Bridge doubled is 32/32/26/36
against Magma's 32/36/26/32, as if the second and fourth widths traded places.
Diversion, the other stock level Magma ported with uneven widths, says no: TFL
13/18/18/8 doubles to 26/36/36/16, Magma has 26/26/36/16 (same order, one width
retuned), and the swap would give 26/16/36/36. Pairing every asymmetric TFL
mesh with Magma's by size found no other clean case. Magma tuned some borders
by hand; Crow's Bridge's south and east edges sitting differently from Magma's
port is that tuning, not a converter error.

### The detail map warning is unrelated

KEEP's log had "Detail map not applied because its dimensions do not match
mesh" before the crash. The clean copy's log does not: a detail map (`dmap`)
shares its id with the landscape, and KEEP's install loads detail-texture
plugins that supply one. Harmless; the converter writes no `dmap`.

## 22. The ground beside Crow's Bridge's bridge

KEEP (Q7): along the east and west sides of the bridge "the mesh height slopes
sag downward instead of raising up" to the model's walls.

### What was wrong

The bridge model (`crow`, byte-identical in TFL and Magma's port) is 4096
square. Its railings stand over Myth II columns 102 and 106, on a causeway of
TFL ground (678 to 830) crossing the river, and from each railing a sloping
stone wall runs down to the model's base, height 0, at columns 100 and 108.
The in-between column `upsample_terrain` blends between the riverbank (0) and
the causeway (101 and 107: 339 to 385) lies a little above that wall, so the
ground hid it: in game only the railings showed, the ground falling away from
them. TFL drew a model over its ground, so the same slope never hid it there.
Magma's port has those 14 points at the foot of the wall (0, or -140).

The first in-game look misled: a plugin converted on its own, without the
stock tags, has no model geometry, so its bridge stays at its TFL corner
anchor, 4 cells off its causeway. The web converter bundles the stock tags,
so Keep's bridge was placed right; convert with `--stock` to test.

### The rule, and how far it carries

`lower_ground_beside_models` (`src/mesh.py`): an in-between point inside a
model's reach (its vertices' furthest x or y from its centre, a square that
holds it whichever way it faces), whose TFL corners step 400 or more and whose
lowest corner is the model's base (marker height, within 32), takes that
lowest height. Measured against the 17 paired levels of *The Fallen Levels
v2*, in mean distance from Magma's height over the points it changes:

| Model | Points | Blended | Lowered |
|---|---|---|---|
| crows bridge (Crow's Bridge) | 14 | 351 | 48 |
| ent small bridge (Forest Heart) | 44 | 2,339 | 1,885 |
| hanging bridge model (Five Champions) | 52 | 1,294 | 1,077 |
| desert arch model (Five Champions) | 34 | 858 | 807 |
| cave at covenant (Flight) | 16 | 733 | 498 |
| Knot Waterfall (Force Ten) | 2 | 475 | 490 |
| waterfall rocks model (Great Devoid) | 17 | 1,424 | 1,615 |

Every Crow's Bridge and ent-bridge point moves nearer. The large distances
elsewhere are Magma reshaping the ground under those models by hand, which no
rule from TFL's heights reproduces. Dropping the base condition, taking the
lowest corner under any model on a 400 step, is further off on five of those
seven models (Five Champions: 118 of 167 points further).

In game (clean 1.8.5 copy, crazyglue's *Along the way to...*), the bridge's
walls now run down to the bank and the water, as in Magma's port.

### Still different: the ground under the arch

> **Update:** solved in §23: the cell flags byte, translated by table, gives the dark arch and the drawn deck.

Through the arch ours shows the bank, lit; Magma's shows black. Magma stamps
the bridge's model index on the cells under it (`0x0009`, ours `0xFFFF`) and
sets bit 0x40 of the cell flags on the wall cells (columns 100, 101, 106, 107)
but not the road. Across Crow's Bridge bit 0x40 is set on 456 cells, every one
of them carrying a model index. Most likely the engine leaves such cells
undrawn. Not yet tried.

## 23. Cell flags: Crow's Bridge's invisible deck

Keep's 0.8 screenshot (Q7, 5 Nov) showed dwarves on Crow's Bridge walking on
air. The bridge model is only railings, an arch underside and a water plane at
height 0: the deck is the ground between the railings, and ours has the same
heights as Magma's (680-830). Myth II simply did not draw it, and through the
arch showed the bank where Magma's port shows black.

Ruled out first: the model (byte for byte Magma's, plus their signature), its
marker (same place, height 0), the ground heights, the lighting tag (Bungie's
`gras` values but for incident I 1.0 against 0.95). Then, in game on a clean
1.8.5 copy, crazyglue's Crow's Bridge with fields copied from Magma's:

| Copied from Magma | Deck and arch |
|---|---|
| light bytes, flags, model index, LOD block | like Magma's |
| LOD block | wrong |
| light bytes (cell bytes 2-3) | wrong |
| flags and model index | like Magma's |
| flags byte (cell byte 4) | like Magma's |
| bit 0x40 and model index only (5 Nov) | wrong |

So the flags byte alone decides it. TFL and Myth II share the byte's offset,
not its meaning. On the deck TFL has 0x21; Magma has 0x20 or 0x00.

Across the 11 levels Magma's port shares with TFL's TAGS.GOR (paired by
heights), each TFL value maps to one Myth II value most of the time:

| TFL | Myth II (Magma's most common) |
|---|---|
| 0x00 | 0x00 |
| 0x01, 0x18, 0x19, 0x20, 0x3d | 0x00 |
| 0x10 | 0x38 |
| 0x11, 0x15, 0x1d | 0x3d |
| 0x21, 0x28, 0x29 | 0x20 |

Applied to all four Myth II cells of each TFL cell, the table matches Magma's
flags (ignoring 0x40) on 95.5% of 484,352 cells; copying matches 84.2%. Bit
0x40 is left out: Bungie's own meshes set it only on cells carrying a model
index, and the stored indexes follow no order a load could rely on (Magma's
and Bungie's are shuffled against the marker list, and one stock mesh has them
byte-swapped), so the engine probably rebuilds them. A crazyglue built with the
table and nothing from Magma drew the deck and the dark arch in game. What
each bit means is still unknown; in Bungie's meshes 0x3d is the usual value
under water.

## 24. Map header version: 7 in TFL, 11 in Myth II

ZeroPipeline of Project Magma told Keep that converted maps carry header
version 7 and that Myth II's editor Oak needs 11. Checked: every `mesh` tag in
TFL's TAGS.GOR is version 7; every one in Bungie's Myth II install (47) and in
Magma's ports (The Fallen Lords v1.9: 40, TFL Multipack v2.6: 60, The Fallen
Levels v2: 52) is 11. Across all other tag types the version is the same in
both games. The converter copied the number, so all 73 of Sir Mauriac's Tale's
maps were 7. From 0.10 a converted map takes 11 (`SB_VERSIONS` in
`convert/headers.py`); a body left in TFL's layout keeps 7.

Possibly related, not yet confirmed: hosted free-for-all games on converted
maps have no teams, flags or balls, although Keep found them all in the maps
with Loathing and saw them appear when "Single Player Map" was ticked in Fear;
and explosions leave a mirrored, streaky patch on the ground, which goes away
when the explosion's mesh effect is removed (Keep, on the advice of Point),
although our wight explosion's `meef` body equals Bungie's own.

> **Update:** neither was related. Netgame elements were missing because of palette `netgame_flags` (§26 in [multiplayer.md](multiplayer.md), 0.11-0.12); the explosion glitch was the level-of-detail block (§27, 0.14).

## 27. The explosion glitch: what Loathing rewrites (Keep's pair, 16 Nov)

Keep sent one converted mesh twice (Q7): "virgin", exported with Untag from a
crazyglue plugin converted by 0.12, and "loathing", the same mesh after a
trivial edit and save in Loathing, verified free of the black ground after
explosions. Compared block by block:

| Part | Changed | What |
|---|---|---|
| Mesh header | 1 field | `connectors_offset` 0 -> end of data (the block is empty either way) |
| Heights, water heights, models | nothing | no geometry changed |
| Cell normals (bytes 2-3) | 14,299 of 25,600 cells | recomputed; not a plain slope of the heights, encoding unknown |
| Cell flags | 438 cells | bit 0x01 (`VERTEX_IS_MEDIA`) added |
| `first_object_index` | 1,369 cells | runtime values, not 0xFFFF |
| Marker palette bytes 28-31 | 39 entries | little-endian runtime counts and indexes |
| Markers | all | reordered; Keep's own edit is among them |
| **Level-of-detail block** | **all** | **ours all zero; Loathing's `00f0` in 5,892 of 6,400 words, `fff0` in 508** |

The LOD block is one 16-bit word per four cells. Across every real Myth II
mesh available (Bungie's 65, Magma - The Fallen Lords v1.9's 40, The Fallen
Levels v2's 52: 1,353,472 words) **not one word is zero**. The second byte's
high nibble is 0xF in 99.3%, the first byte 0x00 (92%) or 0xFF; Bungie's carry
flag bits in the low nibble too (`00ff`, `00f1`, `00f2`, `00f4`, `00f8`).
Loathing writes only the minimal `00f0`/`fff0`; which groups get `fff0` follows
neither roughness nor water, and is not understood. Ours was the only all-zero
LOD block in existence, and the glitch is a rendering one, so 0.14 writes `00f0`
everywhere (`mesh.build_lod_data`). Not yet confirmed in-game.

> **Update:** confirmed. Keep's 0.16 tests (Q7, 16 November): every explosion shows a good ground ripple.

If the glitch survives 0.14, the next suspects from the same pair are the
recomputed normals and the water-vertex flag.
