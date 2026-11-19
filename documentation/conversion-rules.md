# Conversion rules, per tag type

What the converter does to each kind of tag, as of **converter 0.18 (17 November
2026)**. Each rule cites the section of the notes that measured it; the section
numbers (§) are listed by file in [README.md](README.md). When this page and an
older passage of the notes disagree, this page is current.

"Pass-through" means the body is copied byte for byte and the tag is reported
as unconverted. It is never presented as converted.

| Tag type | Status | What is lost or changed | Myth II fields the converter fills in |
|---|---|---|---|
| `text`, `stli` | **converts** | TFL's `\` markup lead-in becomes Myth II's `\|`; a literal `\` followed by `i`, `b` or `p` cannot be told from markup | -- |
| `.256` | **converts** | none: records shared; Myth II's data block gains 32 bytes (every internal offset moves) and TFL's saved runtime pointers are zeroed; 48 of 79 unedited Magma collections reproduce byte for byte (§18). A landscape's stray extra bitmap after its tiles is dropped from the count (§21) | -- |
| `d256` | pass-through | body unconverted | -- |
| `mons` | **converts** | TFL-only fields dropped (`visual_distance`, `sound_pitch_*`, `melee_power`, `intelligence`); scale, vitality and effect modifiers move to the monster's own `obje`. `sequence_indexes` 16 slots to 26, an empty pause or turning slot taking idle or moving (§29). Attacks rebuilt 32 to 64 bytes; flag bits 12-13 move to 11-12 and bit 11 is dropped; other attacks of a unit with a giants-only attack are prohibited against giants (§30) | `size`: man, giant for `ent.` and `trra` (§30). `pathfinding_radius` and `more_hack_flags` per collection from Magma's port (§28). 15 other Myth II-only fields at Magma's value for every unit (§16). `use_attack_frequency` on. Friendly-use flag on special abilities that fire a healing projectile (§31) |
| `unit` | **converts** | none: same 128-byte layout; only its two tag references may be remapped | -- |
| `obje` | **converts**, and each monster gets its own | TFL bytes 6-16 (zero in stock) | scale, vitality and 9 effect modifiers: from the monster for per-monster objects, scale times 0.728 and its random spread divided by 12 (§32), the 7 TFL modifiers as the first 7 of 9 (§18); 1.0 otherwise |
| `proj` | **converts** | TFL's 4 bytes at 76-80 dropped (meaning unknown); TFL flag bit 1 (thrown debris) cleared, as Myth II reads it as *guided* (§18) | zero references written as none |
| `scen` | **converts** | TFL words at 32-44 dropped (no Myth II destination) (§18). Netgame flags and balls Myth II has its own of are not carried; maps point at Myth II's (§26) | netgame scoring type and flag number (0xFFFF) |
| `arti` | **converts** | 128 zero padding bytes after the declared 128 dropped (§18) | 4 extra effect-modifier slots; all-zero TFL modifiers become 1.0 rather than immune |
| `meef` | **converts** | TFL's word at 16 and constant at 10 not carried; no shockwave (TFL has none) (§18) | velocity, dissipation, camera shake, shockwave block (Bungie's own port of `wiex`) |
| `meli` | **converts** | per-map intensities not carried yet: every stock TFL lighting tag converts to the same lighting (§18) | ambient, diffuse, model and total intensities, smoothing, filter (Bungie's base-game values) |
| `part` | **converts** | none: first 92 bytes shared | splash box from Magma's majority; a zero width crashed the engine (§18) |
| `amso` | **converts** | none: same 64-byte layout; Bungie's retuned radii not copied | unused sound slots written as none (`FFFFFFFF`) (§33) |
| `mode`, `geom` | **convert** | `mode`: footprint cells split 2x2. `geom`: header 96 to 128 bytes. Model markers move from TFL's corner anchor to Myth II's centre anchor (§17) | `geom`: bounding box from the vertices, `center_z` 0; material tails and surface bits left as TFL has them |
| `mesh` | **converts**: header, terrain, markers, map actions | 6 TFL-only header fields dropped (`render_variables_tag`, `teams_*`, `annotation_*`) (§12). Terrain: each TFL cell a 2x2 block, heights blended between original points, other fields copied (§15, §20); cell flags translated by table (§23); ground lowered beside models (§22); edge buffer widths doubled (§21). Markers: scenery, unit and observer markers set onto the ground (§20); palette `netgame_flags` filled in (§26). Map actions: parameter types from 12 up shift by one; sound and projectile ids inside parameters follow the ID map (§14). Media coverage copied (§20) | 38 Myth II-only header fields from measurements of Magma's port (§12); header version 11 (§24); level-of-detail block written as `00f0` words, as Loathing does (§27); per-cell `model_index` none (the engine builds obstruction from footprints, §17); per-cell water height from the "Water level" decision |
| `prgr`, `core`, `soun`, `phys` | pass-through | measured against Myth II's stock and Magma's copies: no systematic difference (§33) | -- |
| `lpgr`, `medi`, `ligh`, `wind` | pass-through | `medi` (water) differs widely from Magma's and needs a converter; `lpgr`'s stretch factors are 0 in TFL and usually 1.0 in Myth II; `ligh` and `wind` have too few samples (§33) | -- |
| *(every tag)* | header converts | TFL `tag_version` and `flags` dropped, measured safe (§9); `version` clamped to int16 | `identifier` (unique, sequential), `type` (mirrors the container), `flags`, `destination`, `owner_index` (§9) |
| *(container)* | header converts | TFL `checksum` and `mod_time` dropped | `checksum` and `header_checksum` written as zero: Myth II validates neither (§11); `type` = `PLUGIN` |

**Entrypoints** are synthesised, one per mesh, so converted levels appear in
Myth II's campaign menu (§12).

**Stock tags.** A TFL plugin depends on the stock TFL tags. `tagset` converts
them into a tagset; `convert --stock` builds the ones a plugin uses into the
plugin itself (§18). Engine-facing tags (dialogs, interface, fonts, internal
string tables) are left to Myth II's own versions (§18).

**A tag that fails to convert** is copied unchanged and reported as "could not
be converted"; it no longer stops the conversion (§33).

## Checked in the game

On Myth II 1.8.5:

- *Tandem* and *In the Name of Glory* (Sir Mauriac's Tale) play to the end-game
  screen (§18).
- Water, riverbanks and heights (Keep, 0.9; §20); Crow's Bridge's deck and arch
  (§23); buildings that units walk around (§17).
- Hosted multiplayer games show units, scenery, flags and balls (Keep, 0.11-0.12;
  §26).
- No black ground after explosions; units stand still when they stop (Keep,
  0.16; §27, §29).
- Containers: a plugin with both checksums zero loads and plays; padding after
  the directory is optional; a plugin filename over 32 characters is silently
  ignored; only plugins without entrypoints can be tagsets (§11, §13).

- Forest Giants, Old Growth Forest Giants and Trow attack (0.17); healers heal
  and Yearlings heal themselves only (0.18) (Keep, 19 November; §30, §31).

**Not yet checked in the game:** unit size since 0.13 (Keep is measuring), any
level beyond the ones above. **Known bugs:** Yearling death pieces turn teal
after promotion; Dwarf Heroes cannot throw uphill.
