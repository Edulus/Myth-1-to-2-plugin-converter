# NOTES — prior art, format facts, and the gap

Research notes for `myth-plugin-converter`. Written in Phase 0, before any converter code.

Everything here was read from a local clone of the prior art:

- **Repository:** [jwheare/mythextract](https://github.com/jwheare/mythextract)
- **License:** MIT, © 2025 James Wheare
- **Pinned commit studied:** `c747909f4d68cc37958c3704a6f4d2d14efdd4fc` ("mesh2map improvements")
- **Location:** `reference/mythextract/` — git-ignored, cloned for study, never vendored

Struct sizes quoted below were **computed by running `codec.data_size()` against the
reference**, not eyeballed. Anything I could not verify is called out as an open question.

---

## 1. What mythextract is, and what it is not

mythextract is an **extractor**. It reads TFL and Myth II tag containers and pulls things
*out* of them: individual tags, PNGs, AIFCs, level text, HTML dialogue dumps, map images.
It is very good at this, and its format knowledge is the reason this project is viable.

It does **not** produce plugins. That is the gap (§5).

---

## 2. File-by-file: what each reference file gives us

### `scripts/myth_headers.py` — the single most valuable file

Defines every container and tag-header layout we need, as declarative `codec` field lists.

| Structure | Format constant | Size (verified) |
|---|---|---|
| TFL monolith header (`.gor`) | `GORHeaderFmt` | 64 bytes |
| SB monolith header | `SBMonoHeaderFmt` | 128 bytes |
| SB entrypoint record | `'>16s 32s 64s'` | 112 bytes |
| TFL tag header | `TFLHeaderFmt` | 64 bytes |
| SB tag header | `SBHeaderFmt` | 64 bytes |

**`parse_mono_header(filename, data)`** — the container sniffer and normaliser. Detects
game version by two magic checks, then returns a `UnifiedHeader` namedtuple that hides the
difference between the two container formats:

- SB if `data[124:128] == b'dng2'`
- TFL if `data[:4] == b'\x00\x01\x00\x01'` (type=1, version=1)

The `UnifiedHeader` gives us `header_size`, `entry_tag_count`, `entry_tag_list_start`,
`tag_count`, `tag_list_start`, `tag_list_size`. Layout implied by it:

```
TFL (.gor):  [64B GOR header][ ...tag bodies... ][tag directory @ tag_list_offset]
SB:          [128B header][entrypoints: N×112][tag directory: M×64][ ...tag bodies... ]
```

Note the asymmetry: in TFL the tag directory offset is stored explicitly
(`tag_list_offset`) and in practice sits at the **end** of the file; in SB the directory
position is *derived* — `128 + entry_tag_count × 112` — and bodies follow it. Our packer
must lay out SB files in that order.

**`tfl2sb(tfl_header, tag_content)`** — converts one tag *header* from TFL to SB form and
returns `sb_header_bytes + tag_content`. This is the piece the project brief correctly
identifies as already solved. Field-by-field, here is exactly what it does:

```
TFL header (64B)                      SB header (64B)
------------------------------------  ------------------------------------
                                      0..2   identifier (h)   <- SET TO 0
                                      2..3   flags      (b)   <- SET TO 0
                                      3..4   type       (b)   <- SET TO 0 (ArchiveType.TAG)
0..32   name (32s)              --->  4..36  name (32s)
32..36  tag_type (4s)           --->  36..40 tag_type (4s)
36..40  tag_id (4s)             --->  40..44 tag_id (4s)
40..44  version (L, uint32)     --->  56..58 version (h, int16)   <- NARROWED
44..46  tag_version (H)               (no destination)            <- DROPPED
46..48  flags (H)                     (no destination)            <- DROPPED
48..52  tag_data_offset (i)     --->  44..48 tag_data_offset      <- FORCED TO 64
52..56  tag_data_size (l)       --->  48..52 tag_data_size        <- RECOMPUTED from body
56..60  user_data (L)           --->  52..56 user_data (L)
                                      58..59 destination (b)      <- SET TO 0
                                      59..60 owner_index (b)      <- SET TO -1
60..64  signature b'myth'       --->  60..64 signature b'mth2'
```

What `tfl2sb` does **not** handle, and we must:

1. **It converts headers only.** The body is passed through untouched. For every tag type
   whose body layout differs (§4), the output is a correctly-headed tag with wrong content.
2. **It normalises for standalone extraction, not for packing.** `normalise_tag_header()`
   hard-sets `tag_data_offset = 64`, correct for a loose tag file where the body follows
   its own header, wrong for a monolith where `tag_data_offset` is an **absolute file
   offset** (confirmed by `mono2tag.export_tag`, which slices `data[offset:offset+size]`
   straight out of the whole file). Our packer must compute real absolute offsets.
3. **TFL `version` is narrowed from uint32 to int16.** Fine for the observed values
   (the `.256` sample in `docs/` has `version=4`), but silently lossy above 32767. Worth a
   range check in our port.
4. **TFL `tag_version` and `flags` are discarded entirely.** Not yet known whether either
   carries meaning we need to translate. Open question (§6).

Also here: `create_tag_header()` (synthesise a fresh SB header), `generate_tag_id()` /
`increment_tag_id()` (derive and de-collide 4-char tag IDs), `parse_stli()` /
`update_stli()` (string-list bodies are just NUL/CR/LF-delimited text).

### `scripts/tfltag2sb.py`
A 51-line CLI wrapper: load one extracted tag file → `parse_header` → `tfl2sb` → write to
`output/tfltag2sb/local/<type-name>/<tag-name>`. Confirms the intended call shape of
`tfl2sb`; contains no logic of its own. Operates on **loose tags**, never containers.

### `scripts/tflmeshtext2sb.py` — our one worked example of body conversion + ID remapping
Converts a TFL level's `text` (pregame storyline) and `stli` (map description, picture
captions) tags to SB form. Two things matter to us:

- **Body conversion** is one line: `text_data.replace(b'\\', b'|')`. TFL used `\` as the
  text-formatting escape lead-in; Myth II uses `|` (cf. `utils.ansi_format`, which parses
  `|i`, `|b`, `|p` as italic/bold/plain). This is the entire `text`/`stli` body delta.
- **ID remapping** is the `TFLTagMap` table: 25 entries keyed by level number, each giving
  `(text_tag, desc_tag, caption_tag)` as `(new_id, new_name)` pairs — the IDs used by the
  *existing community TFL→SB ports*, so converted content lands where SB expects it.
  Applied by `tag_header._replace(tag_id=..., name=...)` **before** calling `tfl2sb`.

This is the seed for `src/idmap.py`. Note its shape is level-oriented, not
tag-type-oriented; our table needs to be keyed by `(tag_type, tfl_id)` so it can be applied
to IDs found *inside bodies* too, which `tflmeshtext2sb.py` never has to do.

Levels 15 and 16 map to `(None, None)` for captions — the TFL→SB ports have no caption tag
for those. Our remapper needs a defined behaviour for "deliberately absent".

### `scripts/mono2tag.py` — our reference reader
Lists and extracts tags from any monolith. The read path we will mirror:

```python
mono_header = myth_headers.parse_mono_header(path.name, data)
entrypoints = mono2tag.get_entrypoints(data, mono_header)      # SB only
for tag_header in myth_headers.get_mono_tags(data, mono_header):
    body = data[tag_header.tag_data_offset:][:tag_header.tag_data_size]
```

`get_mono_tags` picks `TFLHeader` or `SBHeader` by `game_version` and reads
`tag_count` records from `tag_list_start`. Entrypoints are `(16s id, 32s name,
64s long_name)` triples starting immediately after the 128-byte SB header.

`encode_entrypoints()` is the closest thing in the whole repo to a writer — and it only
splices a new entrypoint block into otherwise-untouched bytes. It is also buggy (§7).

### `scripts/mesh2tags.py` and `scripts/tag2local.py` — the dependency graph
`tag2local.TagDataGenerator.get_tag_data(tag_type, tag_id)` is a recursive generator that
walks every tag reference out of a parsed body and yields `(header, data)` for the whole
transitive closure, memoised via a `FETCHED` dict. `mesh2tags.py` is a thin wrapper that
starts the walk at a `mesh` tag — i.e. "a map is a mesh plus its dependency graph".

`tag2local.py` is effectively **the reference list of which fields in which tag bodies
contain tag IDs** — ~110 `get_tag_data(...)` calls across `mesh`, `soun`, `amso`, `lpgr`,
`core`, `unit`, `conn`, `part`, `medi`, `prgr`, `mode`, `geom`, `mons`, `anim`, `scen`,
`proj`, `arti`, `.256`, `ligh`, `dmap`. **For our purposes this doubles as the ID-remap
site list**: every field it reads an ID *out of* is a field we must write a remapped ID
*into*. That makes it the single most useful file for Phase 2 step 3.

Non-obvious cases it reveals — IDs that are *not* in fixed header fields and need custom
walking: mesh **marker palette** entries (`mesh_tag.Marker2Tag`), mesh **map action**
parameters (sound and lightning actions carry `soun`/`proj` IDs inside variable-length
parameter blobs), `.256` **sequence metadata** (three `soun` IDs per sequence), and `dmap`
entries (`dtex` IDs).

### `scripts/loadtags.py`
Multi-file tag resolution: builds `tags[tag_type][tag_id] = [(filename, header), ...]` with
last-wins override semantics across the load order, plus `data_map[filename] = bytes`.
Also encodes a lot of hard-won knowledge about **plugin load order** (`PluginFlag`,
`ArchivePriority`, tagset dependencies, vTFL). We need `build_tag_map` /
`lookup_tag_header` / `get_tag_data` to resolve a TFL plugin against the TFL install it
depends on. We do **not** need the load-order heuristics for conversion, but they tell us
what fields in the SB mono header mean (`type`, `version`-as-flags).

`PluginFlag` reinterprets the SB mono header's `version` field as a bit flag:
`TAGSETS_LAST`, `VTFL`, `URL_PLUGIN`, `MESH_LAST`. And `description` doubles as a plugin
dependency name when `URL_PLUGIN` is set. Our writer must set these deliberately.

### `scripts/codec.py`, `scripts/utils.py` — the primitives
`codec.py` is a small declarative binary codec: a format is `(name, [(struct_fmt, field,
decoder, encoder), ...])`, and `codec.codec(fmt)` builds a class that parses bytes into a
namedtuple-like object with a **`.value` property that re-encodes back to bytes**, plus
`_replace()`. Everything is big-endian (`fmt_string = '>'`). Fields named `None` are
padding, and — importantly for round-tripping — padding bytes are **preserved from the
original data** (`value_encoder(..., data_start, data_end)` slices `_original_data`), not
zero-filled. That is exactly the property a byte-exact round-trip needs.

Also provides `list_codec` / `list_pack` (fixed-count arrays with a filter for
empty/sentinel entries), scaled-value decoders (`FIXED_SF = 65536`, `WORLD_POINT_SF = 512`,
`TIME_SF = 30`, etc.), and `codec.String` (a lazy-decoding wrapper that keeps the raw
bytes in `.value` and treats all-`0xFF` as "unset").

`utils.py` gives `TagTypes` (the 37-entry tag-type → human-name map), `slugify`,
`ansi_format`/`strip_format` (Myth `|i`/`|b`/`|p` markup), and `load_file`.

**Design note for us:** this codec is worth porting/adapting rather than re-inventing, but
it is written for reading. `_Codec.__init__` takes either bytes or values, and `.value`
depends on `_original_data` for padding — a codec constructed purely from values encodes
zeros for padding. Fine for new tags, but we must never round-trip an existing tag through
a values-only reconstruction.

### `docs/*.txt` — annotated hex dumps
These are commented hex dumps of real tags, not prose specs.

- **`CoreTagFormat.txt`** — a `core` (collection reference) body: collection tag ID,
  permutation count, tint fraction, 5×8 hue-change table, tint colour, unused, runtime data.
- **`MonsTagFormat.txt`** — the most detailed: a full annotated `mons` body, field by field,
  ending in `208x unused` + `264x runtime unused`. Cross-checks `mons_tag.MonsTagFmt`.
- **`256TagCollectionFormat.txt`** — a `.256` collection: 64B tag header, 349B collection
  header, then `256 × 8` colour table, then bitmaps. The sample is a **TFL** tag
  (signature `myth`), which usefully shows a real TFL tag header in hex.
- **`SoundTagNarrationFormat.txt`**, **`ActionParamElementFormat.txt`**,
  **`FontTagFormat.txt`** — same treatment for `soun`, mesh action parameters, and `font`.

### Bonus: `hexfiend_templates/Myth.tcl` and `Myth2.tcl`
Hex Fiend binary templates for both games' containers. Not mentioned in the brief, but
directly useful for eyeballing a real plugin while debugging the packer.

---

## 3. Container format: consolidated facts

```
SB monolith                              TFL monolith (.gor)
-----------------------------------      -----------------------------------
0    h   type (ArchiveType)              0    H   type        (== 1)
2    H   version (also PluginFlag bits)  2    H   version     (== 1)
4    32s name                            4    32s name
36   64s description (or dep. plugin)    36   L   checksum
100  H   entry_tag_count                 40   L   tag_list_offset
102  H   tag_list_count                  44   H   tag_list_count
104  4s  checksum                        46   H   header_size (== 64)
108  L   flags                           48   H   flags
112  L   size (total file size)          50   2x  --
116  4s  header_checksum                 52   L   mod_time
120  4x  --                              56   8x  --
124  4s  signature b'dng2'
128  entrypoints: entry_tag_count × 112  64   tag bodies ...
     tag directory: tag_list_count × 64       tag directory @ tag_list_offset
     tag bodies ...                           (tag_list_count × 64)
```

Per-tag `tag_data_offset` inside a monolith is an **absolute offset into the file**;
`tag_data_size` is the body length excluding the 64-byte header. When a tag is extracted to
a loose file, `normalise_tag_header()` rewrites the offset to 64.

**Intra-body offsets are body-relative, which is good news for the packer.** Verified in
two places: `mesh_tag.get_offset()` resolves mesh sub-block offsets as
`TAG_HEADER_SIZE + MESH_HEADER_SIZE + offset`, and `myth_collection.parse_collection_header`
adds `header.tag_data_offset` to the stored `data_offset`. So bodies are position
independent — moving a tag within the container does **not** require rewriting offsets
inside it. Only the directory needs recomputing.

---

## 4. Known TFL vs SB *body* differences

Measured from the reference's own dual format definitions:

| Tag | TFL size | SB size | Notes |
|---|---:|---:|---|
| `mons` | 512 | 1024 | `MonsTagFmtTFL` vs `MonsTagFmt` — SB doubles the struct and reorders/adds fields |
| monster attack | 32 | 64 | `AttackDefFmtTFL` vs `AttackDefFmt`; 4 attacks per `mons` (128B vs 256B block) |
| `arti` | 128 | 168 | `ArtifactFmt(game_version)`; effect-modifier slots 12 → 16, and it embeds the attack def, which also grows |
| `mesh` header | 1024 | 1024 | Same size, **different field meanings** — e.g. TFL `render_variables_tag` sits where SB has `connector_tag` |
| `text` / `stli` | — | — | Body is plain text; only the format-escape lead-in changes (`\` → `|`) |
| `.256`, `soun`, `proj`, `core` | — | — | No version-conditional parsing in the reference at all |

Two important cautions on that last row: **absence of version-conditional code in
mythextract is not evidence that the formats are identical.** mythextract mostly reads SB
data; where it reads TFL it may simply not have hit the divergent fields. `.256`, `soun`
and `proj` need independent verification before we claim they pass through.

Other version-sensitive details spotted:

- `mesh_tag.ParamType.PROJECTILE_OR_WORLD_POINT_2D` — the same map-action parameter type
  code means `WORLD_POINT_2D` in TFL and `PROJECTILE` in SB. Map actions cannot be
  passed through blindly.
- `mesh_tag.NetgameFlag.KING_OF_THE_HILL_TFL` — netgame flag bits are remapped between
  games (see `mesh_tag.py:519-523`).
- `MeshFlags.USES_VTFL` and `min_vtfl_version`/`max_vtfl_version` in the SB mesh header —
  Myth II has a built-in TFL-compatibility mode. Understanding vTFL may let us convert
  *less* rather than more, and is worth investigating before writing a `mons` converter.
- `myth_projectile.ProjFlag.HAS_TFL_COLLISION_RADIUS` — SB `proj` explicitly carries a
  TFL-compatibility flag.

---

## 5. THE GAP — what this project has to build

**mythextract has no code path that writes a monolithic plugin container.**

Every write in the repo is one of:
- a loose extracted tag (`mono2tag.export_tag`, `tfltag2sb`, `tflmeshtext2sb`, `tag2local`),
- a derived media file (PNG, AIFC, MP4, HTML),
- or an **in-place byte splice** of an existing container (`fixentrypoints.py` via
  `mono2tag.encode_entrypoints`), which reuses the original tag directory and bodies
  verbatim and never recomputes a single offset.

There is no function that takes a set of tags and produces
`[mono header][entrypoints][tag directory][concatenated bodies]` with a rebuilt directory
and correct offsets. **That packer is the core new work of this project**, along with:

1. **Offset rebuilding.** Directory at `128 + entry_count × 112`, bodies after it, each
   tag's `tag_data_offset` set to its real absolute position. (Made tractable by the
   body-relative-offset finding in §3.)
2. **Checksums.** The SB mono header carries `checksum` and `header_checksum` (4 bytes
   each). **Nothing in mythextract computes either one** — grep for checksum/CRC/adler
   turns up only field declarations and an unrelated PNG CRC. Algorithm unknown. See §6.
3. **`size` field.** Total file size, trivially computed, but must not be forgotten.
4. **Entrypoint synthesis.** A TFL `.gor` has no entrypoints (`entry_tag_count = 0`); an SB
   *plugin* needs one 112-byte entrypoint record per playable mesh, or the level never
   appears in the game's menu. This has no analogue on the TFL side at all — it must be
   synthesised from the mesh tags plus their description `stli`s. `fixentrypoints.py` shows
   where the printable name comes from (first string of the mesh's
   `map_description_string_list_tag`).
5. **Archive typing.** Set `type = ArchiveType.PLUGIN`, and choose `version` bits
   (`PluginFlag`) deliberately rather than copying the TFL header's `version = 1`.
6. **Body conversion + ID remapping**, per §4 and `src/idmap.py`.

---

## 6. Open questions to resolve before/while building

1. **What are `checksum` and `header_checksum`, and does Myth II validate them?**
   The highest-risk unknown. Phase 1 sidesteps it entirely (a byte-exact round-trip
   preserves the originals), but Phase 2 cannot. Plan: build a plugin with a deliberately
   wrong checksum and see whether 1.8.x loads it; if it does, we can defer. If it doesn't,
   we reverse it from a corpus of known-good plugins. This is a real risk to Phase 2 and
   should not be discovered late.
2. **Do TFL `tag_version` and `flags` (dropped by `tfl2sb`) carry anything we need?**
   Survey the distribution of both fields across a real TFL install.
3. **Are `.256`, `soun`, `proj`, `core` bodies genuinely version-identical?** The reference
   has no version-conditional code for them, which is suggestive but not proof.
4. **Is the SB layout really `[header][entrypoints][directory][bodies]`, and does the
   directory need to be sorted?** The ordering is *inferred* — from `tag_list_start` being
   derived rather than stored, and from `encode_entrypoints` treating everything from
   `tag_list_start` onward as one opaque trailing block. Unverified against a real file,
   and unknown whether the engine binary-searches the directory. Phase 1's round-trip
   answers both by observation.
5. **Can vTFL do part of our job?** If Myth II's built-in TFL compatibility mode covers
   `mons`/`proj` semantics, converting a mesh with `USES_VTFL` set may beat converting
   every unit tag. Investigate before writing the `mons` converter.
6. **What actually happens to intra-body offsets in `mesh` sub-blocks?** §3 says
   body-relative, verified for two paths; confirm across the marker palette, map actions,
   media coverage region, LOD data and editor data blocks before trusting it for `mesh`.

---

## 7. Bugs in the reference — do not port these

Found while reading. Worth knowing so we don't faithfully reproduce them.

- **`mono2tag.encode_entrypoints` (lines 84-87) discards its own update.**
  `sb_mono_header._replace(entry_tag_count=..., size=...)` is called but the result is
  never assigned, and the *original* header is encoded on line 90. `_replace` on a
  namedtuple returns a new object. So `fixentrypoints.py` writes files whose
  `entry_tag_count` and `size` are stale whenever the entrypoint count changes. It happens
  to be harmless in its only caller (which only edits names, never adds/removes entries).
- **`mesh2tags.py:38` calls `TagDataGenerator(tags, data_map, plugin_names)`** with 3
  arguments, but the constructor takes `(game_version, tags, data_map, plugin_names)`.
  `mesh2tags.py` is broken at this commit. `tag2local.py:44` calls it correctly.
- **`TagDataGenerator.FETCHED` is a class attribute**, so the memo dict is shared across
  every instance for the life of the process. Fine for one-shot CLIs, wrong for a library.
  Ours must make it per-instance.
- **`myth_headers.parse_mono_header` has unreachable code** after its `return` (lines
  284-288) — a leftover from the `UnifiedHeader` refactor. Cosmetic.

---

## 8. What Phase 1 needs from all this

To read and byte-exactly rewrite an SB plugin:

- `src/reader.py`: `parse_mono_header` → entrypoint records → tag directory → bodies.
  Port `GORHeaderFmt`, `SBMonoHeaderFmt`, `TFLHeaderFmt`, `SBHeaderFmt` and enough of
  `codec.py` to drive them, **keeping the preserve-original-padding behaviour**.
- `src/writer.py`: emit header, entrypoints, directory, bodies; recompute offsets, `size`,
  counts. For round-trip fidelity, carry the original `checksum`/`header_checksum` through
  untouched — do not attempt to compute them yet.
- The byte-exactness bar will fail loudly on any field we decode lossily (narrowed ints,
  zeroed padding, `codec.String` round-trips, all-`0xFF` sentinels). That is precisely why
  it is the correctness gate.

**Honest expectation:** this tool gets a map most of the way, not all the way. `text`,
`stli` and pass-through types are tractable. `mons`, `arti` and map actions involve real
format changes with fields that have no TFL source and must be defaulted. `mesh` is the
hardest. Anything we default rather than translate is a lossy field and belongs in the
README support matrix as such.

---

## 9. Addendum — learned while building Phase 1

Two container-layout subtleties that only surfaced once a packer existed. Both are
properties of the format, not of our code, so they are recorded here rather than in a
commit message.

1. **A tag's body offset does not uniquely identify its body.** Two directory entries can
   legitimately share a `tag_data_offset` for two unrelated reasons: genuine
   *deduplication* (several tags aliasing one body), and a **zero-length body**, which
   necessarily sits at the same offset as whatever follows it without being related to it.
   A packer that deduplicates on offset alone will silently drop the following tag's real
   body. `src/writer.py` keys on `(offset, length)` and skips empty bodies, and preserves
   directory order for ties.

2. **Repacking must preserve body aliasing, not just body content.** Expanding aliased
   bodies into separate copies produces a container that is *valid* but not byte-exact, and
   larger than the original. Since we cannot compute the container checksums (§6), silently
   changing the file size is exactly the kind of drift we cannot verify away later.

Neither is visible from an extractor's point of view, which is why mythextract has no
reason to encode them.

3. **Tag bodies do not start where the header says they do.** The first real plugin tested
   (*Sir Mauriac's Tale*, a 93 MB / 427-tag TFL `.gor`) declares `header_size = 64` and
   then places its first tag body at **128**, with 64 zero bytes in between that no
   structure accounts for. Whether the convention is "align to 128", "reserve a second
   header slot", or something else is unknown, and guessing is unnecessary: the reader
   locates bodies only by absolute `tag_data_offset`, and the writer copies unaccounted
   bytes through verbatim, keyed to the body that follows them. Worth re-checking against a
   Myth II container, where the block after the directory may follow a different rule.

This is a good argument for the round-trip gate as designed. All three points were invisible
against synthetic fixtures built from our own understanding, and the third was caught within
seconds of pointing the packer at real data.

### Gate results

The gate now passes on 282 real containers totalling ~10.5 GB: 276 Myth II plugins, the 5
Myth II core install archives (including the 344 MB `large install`), and one TFL `.gor`.
Between them they cover every archive type the format defines -- `PLUGIN`, `PATCH`,
`ADDON`, `INTERFACE`, `METASERVER`, `FOUNDATION` -- up to 923 tags / 624 MB in one file and
2,649 tags in another.

Three things this settles, all previously open questions from §6:

* **The SB layout really is `[header][entrypoints][directory][bodies]`** (§6 Q4, first
  half). 276 files agree.
* **The directory does not need re-sorting.** We write it back in the order we read it and
  every file matches, so whatever order the engine wants, real files already have it.
* **Checksums are not our problem yet, but they will be.** Every one of these round-trips
  preserves the source checksum untouched, so none of them exercises the algorithm. §6 Q1
  is unchanged and remains the biggest risk to Phase 2.

Note for Phase 2: this install carries several TFL→SB ports (`Magma - The Fallen Lords
v1.9` at 2,110 tags / 40 entrypoints, `Magma - The Fallen Lords DX 1.3` at 2,649 tags).
Those are hand-made conversions of exactly the content we are trying to convert
automatically, which makes them the reference to diff our output against -- and a likely
source of real TFL→SB tag ID mappings for `src/idmap.py` beyond the 25 levels in
`tflmeshtext2sb.py`.
