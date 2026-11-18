# Containers, tag headers and body formats

**Where this stands (17 November 2026).** Settled. The reader and writer are
byte-exact on 282 real archives (§9). Myth II validates neither container
checksum, so the converter writes zeros (§11). Plugin filenames must be 32
characters or fewer (§11). Tag headers: TFL's `tag_version` and `flags` are
dropped safely, `identifier` is unique and sequential, `type` mirrors the
container (§9). §5, §6 and §8 are the plan and questions from before the code
existed; notes below each say how they were answered. (There is no §10.)

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

## 5. THE GAP — what this project has to build

> **Update:** built. `src/writer.py` packs containers, checksums are written as zero (§11), entrypoints are synthesised one per mesh (§12 in [maps.md](maps.md)), and body conversion covers most tag types ([../conversion-rules.md](../conversion-rules.md)).

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

   > **Update:** body-relative throughout; the mesh header is the same size in both games, so nothing after it moves (§14 in [maps.md](maps.md)).

   > **Update:** no for `.256` and `proj`, which now convert (§18 in [stock-tags.md](stock-tags.md)); yes in practice for `soun` and `core`, which show no systematic difference from Myth II's copies (§33).

## 8. What Phase 1 needs from all this

> **Update:** historical. Phase 1 is complete; this is the plan that was followed.

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

> **Update:** settled by §11: Myth II validates neither checksum.

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
