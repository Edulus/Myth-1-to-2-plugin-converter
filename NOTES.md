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

1. ~~**What are `checksum` and `header_checksum`, and does Myth II validate them?**~~
   **ANSWERED — Myth II 1.8.5 does not validate either.** See §11. We never have to compute
   them, which removes what was the single biggest risk to the whole project.
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

### Tag header fields, measured (answers §6 Q2)

**Q2 was: do TFL's `tag_version` and `flags`, which `tfl2sb` drops, carry anything we
need?** Measured across the 427 tags of a real TFL plugin, and against 35,683 Myth II tag
headers from 211 real plugins. Short answer: no, dropping both is safe — but the survey
turned up two *other* fields mythextract normalises that we should not copy.

**TFL `tag_version`** — 70 distinct values from 0 to 1321, spread smoothly, correlating with
tag complexity (meshes reach 1321, 774, 711; string lists sit at 0–1). That is an
**authoring revision counter**, not a format version. Nothing to translate. Safe to drop.

**TFL `flags`** — only four bits ever set (`0x0001`, `0x0002`, `0x0004`, `0x2000`), giving
nine observed values. Meaning unknown, but Myth II's own tag-header `flags` field is `0` in
**35,656 of 35,683** real tags, so whatever TFL recorded there, Myth II does not expect it.
Safe to drop.

**But two fields `normalise_tag_header` zeroes are wrong for tags inside a container.**
mythextract zeroes `identifier`, `type` and `destination` and sets `owner_index = -1`, which
is correct for its purpose — writing a standalone extracted tag file. For a tag *in a
plugin*, real data says otherwise:

| SB tag header field | mythextract writes | Real plugins (n=35,683) |
|---|---|---|
| `identifier` | `0` | **`0` occurs once.** Unique per tag, near-sequential, clustered in a narrow negative int16 band — an authoring-tool handle counter |
| `type` | `0` (`TAG`) | Mirrors the **container's** archive type in 194 of 211 plugins; tags inside a `PLUGIN` are `type=PLUGIN` |
| `flags` | `0` | `0` in 35,656 — mythextract is right |
| `owner_index` | `-1` | `-1` in 35,657 — mythextract is right |
| `destination` | `0` | varies (`0`, `-1`, `3`, `2`, `1`); `0` most common — mythextract is fine |

So our converter assigns unique sequential identifiers and mirrors the container type. It is
still unknown whether the engine *reads* `identifier` at load time; matching observed
practice is the conservative choice, and it costs nothing.

Note for Phase 2: this install carries several TFL→SB ports (`Magma - The Fallen Lords
v1.9` at 2,110 tags / 40 entrypoints, `Magma - The Fallen Lords DX 1.3` at 2,649 tags).
Those are hand-made conversions of exactly the content we are trying to convert
automatically, which makes them the reference to diff our output against -- and a likely
source of real TFL→SB tag ID mappings for `src/idmap.py` beyond the 25 levels in
`tflmeshtext2sb.py`.

---

## 11. In-engine experiment — checksums are not validated

Run against **Myth II 1.8.5 build 471b** on Windows, using *The Greatest Library*
(487,770 bytes, 102 tags, 1 entrypoint) as the subject. Each variant was placed in the
game's `plugins` folder and selected on its own from the New Game screen's Campaign list.

| Variant | Change | Listed? | Loads and plays? |
|---|---|---|---|
| 1 | one byte flipped in `checksum` | yes | — |
| 2 | one byte flipped in `header_checksum` | yes | — |
| 3 | repacked by `src/writer.py`, source checksums carried over (now stale: 448 bytes of padding dropped, `size` changed) | yes | **yes** |
| 4 | repacked by `src/writer.py` with **both checksums zeroed** | yes | **yes** |

**Conclusion: neither checksum field is validated at scan or at load.** Variant 4 is the
decisive one — it is exactly what this tool emits, and it plays. Writing zeros is
therefore correct and honest, and the algorithm never needs reversing.

Variant 3 also settles a second question: it drops the 448 bytes of zero padding that sat
between the container's tag directory and its first tag body, and the game does not care.
That matches the corpus, where 51 of 186 entrypoint-bearing plugins have no such padding
at all. It is authoring slack, not structure. Our reader preserves it for byte-exact
round-trips and our writer drops it when building canonically; both are fine.

### A practical gotcha, found the hard way

Variant 3 initially did not appear in the Campaign list at all, and the padding looked like
the culprit. It was not. The file was named `ZZ test 3 - rebuilt by our packer` — **33
characters**. Variant 2, at 31 characters, listed fine. Renaming it to 20 characters made it
appear immediately, with no change to its contents.

**Myth II silently ignores a plugin whose *filename* exceeds 32 characters.** That is the
same width as the container's internal `name` field, so the limit is presumably shared.
Nothing reports it; the plugin simply is not there. `convert` now warns when the output
filename would exceed 32 characters.

Worth recording as a caution about method, too: the corpus survey that "explained" the
missing plugin via padding was measuring a real thing that turned out to be irrelevant. The
experiment that settled it was renaming one file.

---

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

---

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

---

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

Tag references *inside* map-action parameter **data** (a `SOUND`- or
`PROJECTILE`-typed parameter's element bytes, per `PARAM_TYPE_TAG` in
`src/mesh.py`) are not yet remapped through `id_map` — only the marker
palette's references are. That is a data-completeness gap, not a
structural one: the type-code fix above is what should stop the crash;
finishing ID remapping inside action parameters is follow-up work toward a
fully self-contained conversion, using the same `PARAM_TYPE_TAG` mapping
already ported and ready for it.

---

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

---

## 16. `mons`/`unit` conversion, and the world-unit-doubling question resolved

`src/mons.py` (the format layer, mirroring `src/mesh.py`) and
`src/convert/tags/mons.py` / `unit.py` (the body converters, mirroring
`src/convert/tags/mesh.py`) convert TFL's `mons`/`unit` tags to Myth II's. Same
approach as mesh: rebuild the header field by field, by name, not by position.

### The layout, and one trap in porting it from mythextract

`MonsTagFmtTFL` looks 512 bytes short of `MonsTagFmt` at a glance, but the two
are not simply "SB added fields at the end" — TFL's format has its own internal
padding that a naive field-by-field port drops silently. A first attempt at
`TFLMonsHeader` came out 464 bytes, 48 short. The missing bytes were three gaps
mythextract's `MonsTagFmtTFL` has and a hand-copy missed: a 32-byte gap right
after `sequence_indexes` (TFL only stores 16 slots' worth of data there but
reserves room as if for more), a 14-byte gap after `terrain_costs`, and a
2-byte runtime gap before `movement_modifiers`. All three are silent unless you
assert the struct size against the known 512, which is exactly why `src/mesh.py`
and `src/mons.py` both do that assertion at import time rather than trusting
the transcription.

Two fields share a byte slot under different names between the games: TFL's
`intelligence` and SB's `size` both decode via mythextract's `Size` enum
(small/man/giant) and sit at the same offset — SHARED_FIELDS (computed by name
intersection, same mechanism as mesh.py) misses this because the names differ,
so it is mapped explicitly (`values["size"] = tfl.intelligence`).

`sequence_indexes` (32→52 bytes) and `attacks` (128→256 bytes) share a name but
not a size, so a naive same-name copy would silently zero-pad rather than
convert — both are excluded from SHARED_FIELDS and rebuilt by dedicated
converters (`convert_sequence_indexes`, `convert_attacks`).

### Attacks: TFL's three fixed roles become Myth II's four-slot array

TFL names three sequence roles as separate fields (`sequence_index`,
`elevated_sequence_index`, `declined_sequence_index`); Myth II holds up to four
`(flags, index, skip_fraction)` entries in one array, with `flags` saying which
role a slot plays. mythextract does not decode this `flags` field at all
(`AttackSequenceFmt` has no enum for it), so the bit meanings used here (1 =
Normal, 2 = Elevated, 4 = Declined) are an *inference* from Fear's three
attack-editing checkboxes, corroborated by a real converted attack in the
reference port having flags = 7 (1|2|4, "serves every role") — not a confirmed
fact. TFL's three roles map onto the first three slots by role; the fourth slot
and any unset role use mythextract's own empty-slot convention (`flags=1,
sequence_index=-1, skip_fraction=0`).

**A real bug caught before it shipped:** the first `convert_attacks` ignored
`attack_count` and ran all `MAX_ATTACKS` (4) slots through `convert_attack`
regardless of how many were real. TFL zero-fills unused attack slots, and zero
is not TFL's "no sequence" sentinel (-1 is) — so an unused slot's
`sequence_index` decodes as 0, a real value, and would have been converted into
a bogus "attack sequence 0, Normal" entry rather than being recognised as
empty. Fixed by only converting the first `number_of_attacks` slots and writing
a genuinely empty `SBAttackDef` (`EMPTY_ATTACK`) for the rest. Caught by writing
a test around the exact zero-vs-sentinel distinction, not by manual review —
worth remembering as a category of bug: TFL's "unused" representation is not
always Myth II's "unused" representation, and the two must never be assumed to
be the same encoding.

### Measured defaults, from 60 real converted `mons` tags

Same methodology as mesh (§12): every Myth II-only field's default comes from
measuring `Magma - The Fallen Lords v1.9`'s 60 `mons` tags, not from guessing.
All but four fields are unanimous (60/60):

| Field | Default | Agreement | Note |
|---|---:|---:|---|
| `burning_death_projectile_group_tag` | unset (0xFFFFFFFF) | 60/60 | |
| `burning_death_projectile_group_type` | -1 | 40/60 | gated by `HAS_BURNING_DEATH`, never set by TFL content, so inert either way |
| `experience_kill_bonus` / `experience_bonus_radius` | 255 / 255 | 60/60 | 0xFF = "use `enemy_experience_kill_bonus` instead" |
| `propelled_system_shock` / `damage_to_propulsion` | 65535 / 65535 | 60/60 | gated by `CAN_BE_PROPELLED`, never set by TFL content |
| `pathfinding_radius` | 77 (plurality) | 28/60 | the unit's "space bubble" — genuinely per-monster, no single default is meaningful; see below |
| `map_action_tag` | unset | 60/60 | |
| `hack_flags` | 0 | 60/60 | |
| `more_hack_flags` | 0 | tied 23/60 (50) vs 23/60 (100), 13/60 (0), 1/60 (90) | what this controls was not found documented anywhere; 0 chosen as the most conservative reading of a genuine tie |
| `maximum_mana` / `mana_recharge_rate` / `berserk_system_shock` / `berserk_vitality` | 0 / 0 / 0 / 0 | 60/60 | TFL predates the mana/berserk subsystem entirely |
| `maximum_artifacts_carried` | 0 | 60/60 | |
| `initial_artifacts_projectile_group_tag` | unset | 43/60 | |
| `extra_flags` | 0 | 60/60 | |

`pathfinding_radius` is the mesh converter's `transition_point` situation
again: not unanimous because it is not *supposed* to be uniform, so no honest
single default exists. Flagged in the code as worth a decisions-file-style
override once that mechanism is extended to `mons` (not done in this pass —
see Deferred, below).

`use_attack_frequency` is **forced to 1** rather than taking the measured
value (37/60 off, 23/60 on). TFL applied `attack_frequency` unconditionally —
it had no gating flag for it at all — so the real port's split reflects
per-monster editorial tuning done *after* the port, not a technical default.
Forcing it on preserves TFL's actual behaviour; copying the majority would have
silently disabled a mechanic TFL always used for 37 of 60 monsters.

### `effect_modifiers`: a real architecture change, deliberately deferred

TFL's `mons.effect_modifiers` is a 7-channel per-monster damage-vulnerability
profile (close/long-range physical, explosive, electric, magical, paralysis,
stone). Myth II does not have an equivalent field on `mons` at all — it moved
the concept to `obje.effect_modifiers` (a *different* tag, 9 channels, adding
gas/confusion — `myth_projectile.ObjeEffectFmt`) plus a single damage type per
projectile (`ProjDmgFmt`). There is nowhere on `mons` to put TFL's value.

Wiring this up means a cross-tag write: `mons.object_tag` names an `obje` tag,
and that tag's `effect_modifiers` would need to be synthesised from TFL's
`mons.effect_modifiers` for every monster. That is out of scope for this pass —
consistent with how embedded map-action projectile-tag remapping was deferred
in the mesh converter — and is reported like any other dropped field
(`dropped TFL-only mons field effect_modifiers=...`) rather than silently
discarded, so the gap is visible in every conversion report.

### The world-unit-doubling question (§15) — resolved against doubling, on a small sample

§15 flagged, but deliberately did not act on, Fear's own account of a Bungie
bug: "When Bungie made myth 2 they halved the size of a world unit... most
values throughout the game, such as unit and projectile speeds, were doubled to
take this into account." That raised the possibility that `mons` gameplay
fields — speeds, ranges, distances — need doubling on conversion, not just
relaying-out, and it was recorded as a lead for this converter to check
empirically rather than a rule to apply blindly.

It can now be checked directly: the test TFL plugin (a custom Mauriac-authored
map) and `Magma - The Fallen Lords v1.9` (a converted port of the *stock* TFL
campaign) both use unmodified stock TFL monster tag IDs, so three monsters —
`balo`, `behe`, `waca` — exist in both, TFL-native and Myth-II-converted, under
the same ID. Comparing them field by field:

| Field | ratio (SB ÷ TFL), 3 monsters | Doubled? |
|---|---|---|
| `activation_distance`, `warning_distance`, `critical_distance`, `turning_speed` | exactly 1.0 for all three | No |
| `base_movement_speed` | 1.07, 1.44, 1.06 | No — inconsistent, not a fixed factor |
| `longest_range` | 1.25, 0.5, 0.33 | No — inconsistent, and mostly *below* 1.0 |

A genuine unit-doubling bug would show up as a uniform ~2.0 ratio across every
distance/speed field. What is measured instead is exact equality for four
fields and scattered, sub-2 and even sub-1 ratios for the other two — the
signature of hand balance-tuning by Project Magma's designers (nerfing a
troll's range, adjusting pacing), not a coordinate-system correction applied
mechanically to every value. **Conclusion: `mons` gameplay fields do not need
doubling, and `SHARED_FIELDS`'s straight copy is correct.**

Caveat proportional to the evidence: this is a 3-monster sample, because that
is how many stock TFL tag IDs happen to appear in both files available. It
settles the question well enough to build on — a systematic doubling bug would
not hide from even 3 samples showing exact 1.0 ratios on 4 different fields —
but it is not the 40-or-60-sample confidence the mesh and `mons`-default
measurements above have, and is worth re-checking if a wider stock-TFL sample
becomes available.

### Deferred

- **`effect_modifiers` → `obje`**, discussed above.
- **Decisions-file wiring.** Mesh's synthesised fields are overridable through
  `decisions.toml` and surfaced for review in the plan/CLI/studio (§12, `src/
  decisions.py`, `src/plan.py`). `mons`'s synthesised fields (the table above)
  are not yet wired into that mechanism — they are baked-in module constants,
  same shape as mesh's `SB_ONLY_DEFAULTS` but not yet plumbed through
  `ConversionContext`/`Decisions`/the views. `pathfinding_radius` is the field
  that most needs this, since no single default is honest for it.
- **`arti` (artifacts).** Grows 128→168 bytes and embeds an attack def
  (`ArtifactFmt(game_version)`), same shape as `mons` but not started.
- Attack-slot tag references inside `arti`'s `override_attack` are unaffected
  by this pass; only `mons`'s own attack projectile tags are remapped.

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

### Still needed

- One in-engine test of a converted level with buildings — for the
  `model_index` question above.
- The meaning of the geometry material tail and the added surface bits, if
  converted buildings render or light wrongly without them.

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


## 19. Swapping the units a map places — and a tagset that redefines the stock ones

Written for the Civil War plugins; code in `src/swap.py`, page in
`src/studio/swapping.py`. Tested with *Civil War Reloaded 1.8.4* (`CWR-Maps-184b`,
81 maps; `CWR-Tagset-184b`, 580 unit tags) in a clean Myth II 1.8.5 copy.

### How a map says which unit goes where

A unit marker names a slot in the mesh's **marker palette**, and the slot holds a
unit tag id. Rewriting that id changes every marker using the slot and nothing else.
`mesh.remap_marker_palette` already did this for TFL conversion; `swap.swap_units`
reuses it with an id map that only touches `unit` ids.

Map actions need no change. All 8,323 `MONSTER_IDENTIFIER` parameters in the CWR
maps hold 2-byte values (marker ids), none a unit tag id, and no action type takes
a unit tag by name.

Proof the engine reads the palette: with every Fort Sumter unit slot set to the
non-existent id `zzzz`, the level did not load and the log said
`couldn't read header for unit definition 'zzzz'`.

### Stock ids are not stock units

The first swap used `ogre`, `wam1`, `arch`, `dwar`: Myth II's maul, warrior,
archer and dwarf. The game still showed Civil War soldiers. The tagset redefines
**all 165** of the base game's unit tags, and for 87 of them the unit now points at
a different `mons` (`wam1` "M2-warrior" -> `_zuv` Union veteran; `arch` -> `_zus`
sharpshooter; `ogre` -> `_zcs` Confederate soldier). The names are stale labels.
Only 78 stay as they were: ambient and animals, peasants, cannons, posts.

The fix is to restore the original unit tags. The tagset repointed the *unit* tags
and mostly left the base `mons` alone, so the restore is tiny: for the tested
units the closure is just the one 128-byte `unit` tag. `swap.restore_stock_units`
compares the tagset to the base game (installs, then the patches, later wins) and
carries only tags the tagset changed. 481 stock tags are changed in total (154
units, 64 scenery, 58 projectiles, 57 objects, 45 monsters ...). The reference
scan that finds dependencies is a heuristic over even offsets, limited to those
481, because a full per-type reference walker does not exist.

The swapped plugin has to load **after** the tagset, as later wins. Choose the
campaign first, then the tagset.

### Result

On *Fort Sumter*, real warriors (`wam1`) and ghols (`ghol`) replaced the Civil War
soldiers, from a plugin built on the command line and from one built in the
studio's Swap units page.

A second pack, *CWR Fields of Battle Map Pack A* (25 maps) with the 1.7 tagset
(`CWR-12-02-09-Tagset.TM2`, 3,709 tags, 420 units), behaved the same: 110 side
units swapped across 25 maps, and warriors and ghols appeared on *Little Flat Top*.
That tagset also redefines the base game's units (`wam1`, `ghol`, `arch` among
them; 154 stock units, 376 stock tags). Ten unit types those maps place are not in
the 1.7 tagset (animals, flags); they come from the base game or the 1.8.4 tagset
and need no swap. The tagset left active from an earlier test persisted in the
Tagsets list, so switch it before playing a pack that needs the other one.

### Open

- Only one map and two replacement units have been played.
- The base-game load order (`swap.STOCK_ARCHIVES`) is inferred from the log's
  "monolithic tags" list plus the "1.8.5 gameplay" line; the three Unity/Maps
  patches' position is a guess.
- Restoring a stock unit at its own id also changes any other slot that uses it.
- The marker records read by `mesh.MarkerHead` disagree with palette entry types
  for most markers (e.g. marker type 3 pointing at a type 1 palette entry), so the
  marker `type` / `palette_index` fields as declared are probably misread. The swap
  does not use them; counts of "units placed" per map are unreliable until fixed.
- Campaign levels unlock in order, so a swap is only checkable on unlocked levels.
