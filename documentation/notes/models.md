# Models: mode and geom

**Where this stands (17 November 2026).** `mode` and `geom` convert (footprint
cells split 2x2, `geom` header 96 to 128 bytes with a derived bounding box), and
model markers move from TFL's corner anchor to Myth II's centre anchor. The
per-cell `model_index` stamp is not needed: the engine builds obstruction from
the footprint (in game, Crow's Bridge). Open: what Magma's extra geometry
material and surface bits mean.

## 17. Models — what is known, and what needs TFL data to settle

Prompted by KEEP, the community member who proposed this project: "models,
mesh, units ... those are 3D!" Models had not been looked at at all — not in the
support matrix, not measured — so this section records a first pass. It settles
one thing about the *mesh* and leaves the model tags themselves open for want of
data.

### The tag chain, and why the test plugin cannot answer the question

A placed building is a `mode` marker in the mesh. The `mode` tag names a `geom`
(the 3D geometry), which names a `core` (its texture collection); `anim` tags
sequence `mode`s for animated models. mythextract `scripts/myth_tags.py`
declares `ModelFmt`, `GeomFmt` and `AnimFmt` once, with no TFL variant, and
`tag2local.py` walks TFL game folders through them — weak evidence the layouts
match, since the walk only reads the tag-reference fields near the start of each
struct. Contrast `mons`, which mythextract does version (§16).

*Sir Mauriac's Tale* contains no `mode`, `geom` or `anim` tags at all: its
models come from the stock TFL tag library, like most of its other dependencies
(§12). Neither does the other TFL `.gor` to hand (`gofc2TFL.gor`: `.256`,
`mesh`, `soun`, `stli` only), and the Myth II disc image is Soulblighter alone.
**Comparing TFL and Myth II model tags needs the stock TFL tags**, from a TFL
install or disc — measured below, once KEEP supplied them.

Iron's 2011 mesh converter readme (`reference/mesh-converter/ReadMe.txt`) is the
only first-hand account: "For everything other than models you can use
placeholders & change the tags afterwards, but models have to be the TFL ones."
Models are tied to the map in a way scenery and units are not.

### Finding: Myth II stamps every placed model into the terrain cells under it

The Myth II terrain cell's last field, `model_index` (§15; `src/mesh.py`
`NO_MODEL_INDEX`), has no TFL counterpart. Measured across all 40 meshes of
`Magma - The Fallen Lords v1.9`:

| | Meshes |
|---|---:|
| place at least one `mode` marker, and have cells with `model_index` set | 21 |
| place no `mode` marker, and have no such cell | 19 |
| either one without the other | 0 |

- In every one of the 21, the number of distinct `model_index` values equals the
  number of `mode` markers exactly.
- 540 of the 541 stamped clusters have a `mode` marker sitting on them (marker
  position / 512 = cell coordinate, within the cluster's bounds ±1).
- Clusters are compact rectangles — 2x2 cells (303 of 541), 4x2 (81), 6x6 (37),
  4x4 (17) — consistent with building footprints.

So the ~1% of native cells that are *not* `NO_MODEL_INDEX` (§15) are exactly the
cells under buildings, and **the converter currently loses this**: it writes
`NO_MODEL_INDEX` into every cell of a converted mesh.

### Open: how the stamp is numbered, and whether the engine rebuilds it

> **Update:** settled below ("In-engine"): the engine builds obstruction from the footprint, so cells stay `NO_MODEL_INDEX`.

- **Numbering.** Each model gets its own value, 0..n-1, but the value matches
  none of the marker's list position, rank among `mode` markers, `id`, or
  `palette_index` (in *302 traitor*, the four models in marker order carry 2, 0,
  3, 1). Plausibly Loathing's internal model order at save time.
- **Encoding.** 18 of the 21 meshes store the value in the high byte (12032 =
  0x2F00 = model 47); 3 store it in the low byte. mythextract's `MeshCellFmt`
  declares a plain `H`.

Both point the same way: if the stored value followed no fixed rule and still
worked in shipped maps, the engine may rebuild it at load from the markers and
each model's own footprint. If it does, `NO_MODEL_INDEX` everywhere is harmless;
if not, converted buildings may lose collision, pathing or rendering. **One
in-engine test settles it**: load a converted level with buildings and see
whether units walk through them.

### Measured against the stock TFL tags

KEEP supplied the stock TFL `TAGS` folder (kept local, never committed).
`TAGS.GOR` holds 91 `mode` and 91 `geom` tags; Magma holds the same 91 `mode`
IDs and 95 `geom` (91 in common). No `anim` tags exist in either. Compared ID by
ID, as §16 did for `mons`:

**`mode` — one change: the footprint is in terrain cells, and cells halved.**

- The 64-byte header layout is identical; only `mesh_cell_count`,
  `mesh_cell_size` and `data_size` differ (85 of 91 — the other 6 match
  throughout).
- Geometry-vertex data is identical in 91 of 91, permutations in 90 of 91. No
  coordinate rescaling.
- The footprint (`ModelMeshCellFmt`: x, y, flags, 8 bytes each) is exactly 4x
  the cells: in **81 of 91**, Myth II's footprint is TFL's with each cell
  (x, y, f) split into the 2x2 block (2x..2x+1, 2y..2y+1, f). The other 10 have
  different shapes and flag values (`ambu` goes from flag 7 to 8) —
  hand-editing by Magma, not a different rule.

So converting a `mode` is: split each footprint cell 2x2, and grow
`mesh_cell_count`, `mesh_cell_size` and `data_size` to match.

**`geom` — a longer header, a derived bounding box, two judgment calls.**

- TFL's header is **96 bytes** (bytes 88..96 zero in all 91), Myth II's **128**
  (`data_offset` 96 → 128). Every count, offset and section size is identical.
- The 12 added bytes are a bounding box (`bounds_min/max_x/y/z`), equal to the
  min/max of the vertices in **90 of 91** (`enst`'s is garbled in Magma's copy).
  Derivable, not invented.
- `center_z` is zeroed in 90 of 91.
- Vertices and dependencies are identical. Two things are not:
  - **Materials (41 tags):** bytes 58..63 of each 64-byte material record —
    padding to mythextract, junk in TFL — hold three int16s in Myth II:
    (0,0,0) in 85 records, otherwise (1, 0, k) with k = 0..4+. Meaning unknown.
  - **Surfaces (39 tags):** byte 1 of a 64-byte surface record gains bits —
    0x10 (1,487 surfaces), 0x20 and 0x02 — none ever cleared. Meaning unknown.

  The other 43 geometries are byte-identical in data, so zeroed material tails
  and TFL's surface flags are a shape Myth II is known to accept. Whether the
  extra values are tool-computed (and matter for rendering or lighting) or
  Magma's own tuning is open.

**Also measured:** `core` is byte-identical in 99 of 152 common IDs and the same
size in all 152; `scen` is the same size in all 61 common IDs but never
identical. Both are worth the same treatment next.

### Converted (2026-10-27), checked against *The Fallen Levels v2*

KEEP asked for buildings after testing Crow's Bridge (§20), and
`src/convert/tags/mode.py` and `geom.py` now convert them. Against the 91
stock models and geometries in Magma's *The Fallen Levels v2* (porter
signatures after the data ignored):

- **`mode`: 72 of 91 byte-identical.** Each footprint cell splits 2x2 in rows,
  and the source cells are sorted by (x, y) first, as Magma's are. Of the other
  19, 9 differ only in cell order and 10 are hand-edited shapes or flags.
- **`geom`: 43 of 91 byte-identical.** The other 48 differ only in the material
  tails and surface bits below, plus `enst`'s garbled box in Magma's copy.
- The six bytes after `center_z`, padding to mythextract, are not padding:
  TFL and Magma hold the same values there, so they are kept.

Myth II-only defaults, agreed with the user on 2026-10-27:

| Field | Default | Agreement | Note |
|---|---|---|---|
| `geom` bounds min/max x, y, z | the vertices' extent | 90 of 91 | vertices are (x, y, z) int16 triples; derived, not invented |
| `geom` `center_z` | 0 | 90 of 91 | TFL holds half the model's height here |
| `geom` material record bytes 58..63 | TFL's bytes, unchanged | 85 records (0,0,0) | Magma sometimes sets (1, 0, k); meaning unknown |
| `geom` surface byte 1 extra bits | none added | 43 geometries identical | Magma adds 0x10, 0x20, 0x02 to some; meaning unknown |

### In-engine, and where Myth II anchors a model

On a clean 1.8.5 install, *On the road to Strand* (Crow's Bridge) showed its
two converted ambush inns, and units ordered across them walked around. So the
engine builds a model's obstruction from its footprint at load, and the
`model_index` stamp above is not needed: cells stay `NO_MODEL_INDEX`.

But one unit started inside an inn. Every model marker sits somewhere else in
Magma's port, by an amount fixed per model and independent of its facing
(Crow's Bridge: barn +3072/+1024, inn +3072/+3072, town house +2048/+2048).
Iron's 2011 converter has the same idea commented out (`marker[i].distancex
+= 2048`). Across the 17 levels of *The Fallen Levels v2* that pair with
stock TFL levels, the amount is the model geometry's (`center_x`,
`center_y`) rounded to a whole Myth II cell, whatever the facing: TFL anchors
a model by a corner, Myth II by its centre. `place_models_by_centre`
(`src/mesh.py`) applies that; afterwards 287 of 328 model markers sit exactly
where Magma's do. The rest are Magma's own: the farm one cell further east
(15, with a re-drawn footprint), 18 cave stalagmites not moved at all, 4 night
farmhouses placed by hand, and 3 world-knot stones nudged a fraction of a cell.

### Still needed
- The meaning of the geometry material tail and the added surface bits, if
  converted buildings render or light wrongly without them.
