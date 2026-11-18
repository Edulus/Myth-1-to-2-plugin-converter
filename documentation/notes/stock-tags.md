# Converting the stock TFL tags, layer by layer

**Where this stands (17 November 2026).** Every layer in the table below is now
converted: `proj`, `scen`, `unit`, `arti`, `meef`, `part`, `.256`, `obje`,
`meli`, and since 0.13 `amso` (§33). Engine-facing tags are left to Myth II's
own versions. Still copied unchanged: `prgr`, `core`, `soun`, `phys` (measured:
no systematic difference, §33), and `lpgr`, `medi`, `ligh`, `wind` (they differ,
or there are too few samples; `medi` needs a converter). Unit scale is no
longer copied (§32, in [units.md](units.md)).

## 18. In-engine experiment 3 — converting the stock TFL tags, layer by layer

Myth II 1.8.5 build 471b, *Sir Mauriac's Tale* level **Tandem** (zm04: 77
model markers, single-player), driven one change at a time against
`myth_log.txt`.

### Supplying the stock tags: Magma is not enough, the TFL originals are

The §13 tagset (Magma's port with its entrypoints stripped) was rebuilt. Two
things learned on the way:

- **Myth II identifies a plugin by the name inside it, not its filename.** The
  rebuilt tagset still carried Magma's internal name and was silently hidden
  as a duplicate of the Magma campaign. Renaming the header's `name` fixed it.
- **Selecting a campaign clears the tagset choice** until it is re-picked in
  the Tagsets dialog; the log line `Starting mesh ... with N plugins` is the
  check that it took.

With it loaded, Tandem still failed on `medi.mawa`: Magma has no `mawa` (it
renamed or dropped many stock IDs). Mapping it in a decisions file exposed a
converter bug — the mapping reached the report but not the mesh header — fixed
in `src/convert/tags/mesh.py`. The next failure was `amso.am05`, and a full
listing showed **76 references** Tandem needs that Magma does not carry under
their stock IDs.

Converting the stock TFL tags themselves (`TAGS.GOR` + `ARTSOUND.GOR`, from
KEEP; 2,672 tags) into a tagset resolved all 76 at once. That is route 1 of
§12, and it also puts the converter to work on the whole stock library.

### Each layer, in the order the engine reported it

| Run | First failure | Cause | Fix |
|---|---|---|---|
| 1 | `couldn't read header for projectile definition '    '`, cascading to splashes, the marsh media, the mesh | `proj` passed through in TFL layout | `src/convert/tags/proj.py` |
| 2 | `object definition 'fasc'`, `collection reference '    '` on every bush, tree, barrel | `scen` passed through | `src/convert/tags/scen.py` |
| 2 | `couldn't read unit definition for 'mits'` | the `unit` converter wrote 8 bytes of a 128-byte body | keep the 120 undeclared bytes |
| 3 | `collection reference '    '` in mesh effect `sace`; `arti` bow of stoning | `meef`, `arti` passed through | open |

> **Update:** both converted later in this section (`arti` in "Run 4 onward", `meef` in "Built by the commands alone").

Every fix was measured against Magma's ports of the same stock IDs before the
next run.

**`proj`** (104 IDs in common, 256 bytes in both). TFL has 4 extra bytes at
76..80; everything after sits 4 bytes later, anchored by the references
(promoted projectile 96 → 92, artifact 124 → 120, local projectile group
140 → 136). TFL flag bit 1 marks thrown debris — set on body parts, bones,
apples, barrel boards; never on swings, lightning or splashes — and Myth II
reads it as `IS_GUIDED`, so it is cleared. TFL zero-fills unused references,
Myth II writes 0xFFFFFFFF, except `script_tag` (zero in all 273 of Magma's).
81.4% → 92.8% byte agreement; the rest is Magma's editing.

**`scen`** (61 IDs in common, 128 bytes in both). Not a single shift — a map:
flags 0 → 0, collection 8 → 4, object/projectile 24 → 8, projectile groups
44 → 24, sequence indexes 60 → 40; TFL's six words at 32..44 have no Myth II
destination. 60.8% → 94.2%.

### Run 4 onward: the level starts

With `arti` converted (`src/convert/tags/arti.py`) and Magma's Myth II-native
`meef` tags standing in for the stock ones (a test stand-in in the build
script, not a conversion), every definition error cleared and the engine began
rendering — then crashed with EXCEPTION_INT_DIVIDE_BY_ZERO in
`_build_particle_system_surface_list` (particle_systems.c:352). Myth II's
particle systems end in a splash box TFL does not have; a zero `box_width` is
the divisor (`src/convert/tags/part.py`).

With that fixed, **Tandem starts and plays** — the first converted TFL level to
run in Myth II. The log is clean. Terrain, the river, the rain and the minimap
render; units exist (dots on the minimap) and cast shadows, but neither units
nor scenery are drawn.

Marker positions were ruled out first: across 1,078 markers matched between
the two stock maps both games carry, the SB/TFL position ratio has a median of
exactly 1.000 in x and y.

The cause is the `.256` collections (still passed through). Against the 198 in
both the stock TFL tags and Magma: Myth II's data block starts with 32 bytes —
`"This tag was saved by Amber 2.0"`, an editor stamp — and every section offset
in the header is 32 later (empty sections have offset 0). That accounts for the
header; inside the data, each bitmap's own offsets also move by 32, and TFL
carries stale runtime pointers where Myth II has zeros. Converting `.256`
means walking the bitmap records, not just the header.

That conversion is now done (`src/convert/tags/collection.py`: 48 of the 79
collections Magma left unedited reproduce byte-for-byte) — but it did **not**
make units appear, and neither did swapping in Magma's own Myth II sprites, or
mapping the level's lighting to Myth II's `gras`. Those A/B tests cleared the
sprite chain and pointed at what units and scenery share outside it: the
`obje` tag.

### The cause: object scale

A TFL `obje` is 16 bytes of physics — gravity, elasticity, terminal velocity —
and all 46 stock monsters share one, `baob`. Myth II's is 64 bytes
(mythextract `ObjeTagFmt`) and also carries vitality, **scale** and the
damage-type modifiers, which TFL kept on the monster. Read as Myth II's, a TFL
object has scale 0 at byte 12: every unit and tree was drawn at size zero,
while shadows, sounds and minimap dots — which do not use it — were fine.

`src/convert/tags/obje.py` converts objects with neutral 1.0 values, and
`convert_container` gives each monster an object of its own from its TFL
`maximum_vitality`, scale and `effect_modifiers` (the cross-tag write §16
deferred). Against the 24 monsters Magma shares, Magma's per-monster objects
hold the TFL vitality exactly and the 7 modifiers as the first 7 of 9.

> **Update:** per-monster scale is no longer copied: since 0.13 it is TFL's times 0.728 (§32 in [units.md](units.md)).

**With that, Tandem plays with its units and scenery drawn** — warriors,
archers, villagers, barrels, trees — on converted terrain in converted rain.

### Built by the commands alone

With `meef` converted (`src/convert/tags/meef.py`) and the stock tags turned
into a tagset by `python -m src tagset` rather than a script, Tandem starts with
units visible on **nothing but the converter's own output** — no Magma tags.
The one remaining stand-in is a decisions-file line mapping the level's
lighting to Myth II's `gras`.

Two runs on the way are worth keeping:

- The first converted `meef` crashed the engine in `__output` (output.c, the C
  runtime's printf) — formatting an error message, not doing physics.
  Swapping Magma's mesh effects back in stopped it; bisecting gave a clean log
  line: `sequence #16 not in [#0,#14) for "internal monster effects"`.
- **Stock TFL tags in a tagset replace Myth II's base tags of the same ID.**
  Myth II's own mesh effects name sequence 16 of `inme`; the tagset's TFL
  `inme` has 14. Anything converted must be valid against the TFL tags it
  will actually meet, not Myth II's — and Myth II content that expects its own
  `inme` (or any other shared ID) may break while a converted stock tagset is
  active.

### Lighting, and no stand-ins left

`meli` is 128 bytes of IEEE floats in TFL and 64 of 16.16 fixed point in Myth II
(`src/convert/tags/meli.py`). The light direction (TFL floats 16..18) and the
maximum shadow distance map cleanly; the intensities do not, and Bungie's
base-game values are used, so every stock TFL lighting tag currently converts
to the same lighting. With the `gras` mapping removed, Tandem plays on its own
converted lighting and looks right. The only decisions-file entry left for it
is `medi.mawa` → `ma2w` from the first run.

### A second level, and the end-game crash

*In the Name of Glory* (zm18: snow lighting, Bagrada snow, 146 map actions)
loaded with no missing references — and crashed in `__output` (printf), as
had Tandem after ten minutes' play. Both at the **end-game screen**. Myth II
fills that screen's statistics into string templates printf-style; the
converted tagset's `stli.in03` ("internal solo postgame") replaced Myth II's,
with 13 placeholders to Myth II's 14, so a `%s` received a number.

876 of the converted stock tags replace Myth II base tags of the same ID. For
content that is the point; for what Myth II's *code* drives it is not.
`convert_tagset` now leaves 141 engine-facing tags to Myth II's own versions:
dialogs, templates, fonts, the interface, observer constants, the internal
sound list, and the "internal ..." string tables. Internal art stays — TFL
projectiles index it by sequence. *In the Name of Glory* now plays through to
its end-game screen with a clean log, save one harmless warning: its pregame
picture asks for sequence 3 of *Mauriac*'s two-sequence `zp08`.

### Bundling only the stock tags a plugin uses

`convert --stock` first carried all 2,432 eligible stock tags (306 MB), making
*Sir Mauriac's Tale* 419 MB. That is heavy for a browser to build (1.7 GB of
WebAssembly memory in a Pyodide test). It now carries only the stock tags the
plugin can reach, found cautiously: any four bytes at any offset that equal a
stock tag ID pull in every stock tag with that ID, repeated from each one pulled
in. `soun` bodies are not searched, since they hold samples, not references.
Result for *Mauriac*: 2,068 stock tags, 293 MB.

At first `.256` bodies were skipped too, as pixels (1,666 tags, 245 MB).
*Tandem* played, but *On the road to Strand* would not start: `couldn't read
header for sound definition 'myce'`, the myrmidon's `celebrate` sequence sound.
A collection's sequences name their sounds, so collections must be searched,
false matches and all. A typed walk of each tag's
reference fields would cut deeper but could miss one, and a missing tag fails
silently. `--all-stock` restores the old behaviour.

### Open

- **Pregame picture sequence**: `sequence #3 not in [#0,#2) for "zp08"` at
  the pregame screen.
- **`meli` per-map tone**: TFL's float 9 is a candidate for maximum total
  intensity (0.85 for moon light, as in Magma's moon); the other TFL floats are
  unmapped.
- ~~`meef`~~ converted (above). Was: 32 bytes in TFL, 36 in Myth II, which adds a shockwave block
  (the Fear manual lists amplitude, velocity, cutoff radius, dissipation,
  epicenter offset, camera shaking type, inverted, then shockwave collection,
  sequence, radial points, thickness, height offset). Only 3 IDs in common, all
  retuned by Magma — too few to map by measurement alone. 4 stock tags.
- **`arti`**: 128 → 168 bytes, embeds an attack definition (§16 Deferred).
- Still unconverted in the tagset after this round: 1,698 of 2,672 tags,
  mostly `.256` and `soun` (art and sound, untested), `core`, `prgr`, `amso`.

> **Update:** `arti` converted (above). The types still unconverted are listed at the top of this file.


## 33. The types still copied unchanged, measured; ambient sounds; one bad tag (0.13)

Written up on 17 November 2026 from Fable 5.2's review of 16 November (the
measurement) and the 0.13 code.

**Measured.** Pairing each stock TFL tag with the tag of the same id in Magma's
*The Fallen Lords v1.9* and in Myth II's own files, same-size pairs only:

| Type | Pairs (Magma / Bungie) | Byte-identical | Bytes that differ in 60% or more of pairs |
|---|---|---|---|
| `amso` ambient sound | 22 / 33 | 0 / 0 | 20-36 in both; TFL has zeros where Myth II has `FF` |
| `lpgr` local projectile group | 13 / 11 | 0 / 3 | 62-76 on even bytes; TFL 0, Myth II 1 |
| `medi` media (water) | 7 of 9 same size | 0 | many, from byte 26 on; 2 of 9 also change size |
| `ligh` lightning | 3 / 2 | 0 / 0 | 15, 18, 27, 52, 55 (too few pairs to be sure) |
| `prgr` projectile group | 41 / 90 | 3 / 24 | none |
| `phys` | 6 / 10 | 1 / 4 | none |
| `core` | 152 / 68 | 99 / 4 | none against Magma |
| `soun` | 272 / 182 | 118 / 65 | none |

`prgr`, `phys`, `core` and `soun` show no systematic difference, so copying them
is right. `medi` differs widely and needs its own converter. `lpgr`'s run of
16-bit fields is 0 in TFL and usually 1.0 in Myth II, though Myth II's own stock
also has all-zero ones; undecided. `ligh` and `wind` need more samples.

**Ambient sounds** (`src/convert/tags/amso.py`). Same 64-byte layout in both
games; an unused sound slot is zero in TFL and `FFFFFFFF` in Myth II. Of 220
slots that are zero in TFL, 208 are `FFFFFFFF` in the Myth II copies; every slot
that names a sound is carried as it is; bytes 38-64 are identical in all 55
pairs. The converter writes unused slots as `FFFFFFFF`, the same rule as the
`proj` converter's "zero references written as none". Bungie's retuned radii are
tuning and are not copied.

**One bad tag no longer stops a conversion.** `convert_container` now catches an
error from any one tag's converter, copies that tag unchanged and reports it as
"could not be converted". Community plugins are hand-edited and sometimes odd.
