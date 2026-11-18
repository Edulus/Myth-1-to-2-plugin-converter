# Units: mons, unit and their objects

**Where this stands (17 November 2026).** The rules now in force:

- Same-name fields copied; `sequence_indexes` and `attacks` rebuilt (§16).
- `size`: man, or giant for collections `ent.` and `trra` (§30). **Not** TFL's
  `intelligence`, as §16 first assumed.
- Attack flags: TFL bits 12-13 move to 11-12, bit 11 dropped; a unit with a
  giants-only attack has its other attacks prohibited against giants (§30).
  A special ability that fires a healing projectile may target friendly units
  (§31).
- Empty pause and turning animation slots take idle and moving (§29).
- Myth II-only fields: 15 take Magma's value for every unit (§16);
  `pathfinding_radius` and `more_hack_flags` are set per collection (§28).
- Each monster gets its own object with its vitality and effect modifiers (§18,
  in [stock-tags.md](stock-tags.md)) and its scale times 0.728, random spread
  divided by 12 (§32).
- In game: moonwalking fixed (Keep, 0.16). Giants and heals (0.17, 0.18) await
  testing. Heroes may still be 10-14% taller than Magma's (§32).

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

> **Update: wrong.** TFL's `intelligence` is AI intelligence, not size; copying it made nearly every unit giant-sized. `size` is now set by collection (§30).

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

> **Update:** the attack flag word also needs its giant bits moved (§30), and healing special abilities need Myth II's friendly-use flag (§31).

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

> **Update:** `pathfinding_radius` and `more_hack_flags` are now set per collection from Magma's port (§28); the other 15 defaults hold for all 39 of Magma's stock units.

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

> **Update:** done in §18 ([stock-tags.md](stock-tags.md)): each monster gets its own `obje` carrying its effect modifiers, vitality and scale.

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

> **Update (17 November 2026):** `effect_modifiers` and `arti` are done (§18). Decisions-file wiring for `mons` is still not done, but `pathfinding_radius` no longer needs it (§28).

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

## 28. Per-unit values for the two Myth II-only fields that vary (0.15)

Keep asked which settings "fill each unit's Myth II-only settings from Magma's
own version" meant. Measured against Magma - The Fallen Lords v1.9's ports of
the 39 stock TFL monsters it carries: 15 of the 17 synthesised `mons` fields
hold our default in all 39. Only `pathfinding_radius` (51 to 220; 77 in 17 of
39) and `more_hack_flags` (0, 50, 90, 100) vary, and neither follows the size
class (Bungie's own man-sized units run 26 to 205). So the mons converter now
takes both from `PER_COLLECTION`, keyed by the collection the monster draws
with: 21 collections, each the value most of its monsters share in Magma. The
Forest Giant (220) and trow (154, 90) had 77 and 0, and are the two units Keep
reports will not attack. 16 of Sir Mauriac's 17 monsters are covered; CbC's
repainted thrall (`thmo`) is not. The table is on the site at keep/units.html.

## 29. Pause and turning animations, and the change list (0.16)

**Animations.** `convert_sequence_indexes` copied TFL's 16 animation slots as
they are and assumed each means the same in Myth II. Against the 24 stock TFL
units in both Myth II's own tags and Magma's port, slots 0-2 and 5-15 mostly
agree (13 to 22 of 24), but slots 3 (pause) and 4 (turning) agree in only 1
and 4: TFL leaves them -1 and Bungie fills them. Bungie's pause is the unit's
idle_1 in 16 of 24, another standing animation (holding, idle_2) in most of
the rest, empty in 1; its turning is moving in 16. Myth II plays pause when a
unit stops, so an empty pause fits the moonwalking (units jog on the spot
after stopping until the space bar is pressed; Keep). 0.16 fills an empty pause
with idle_1 and an empty turning with moving. Not yet confirmed in-game. The
remaining per-slot differences (celebration, holding, idle_2) are per-unit
tuning and not modelled.

> **Update:** confirmed. Keep's 0.16 tests: units stand still when they stop.

**The change list.** Keep asked for every `mons` field the converter edits to
be written down so he can audit its work, ideally as a trail of what changes
by how much. `src/audit.py` builds it: one row per field per monster and per
monster object, with the TFL value, the Myth II value, what happened (copied,
converted, changed, moved, dropped, Myth II only: set / per unit) and why. The
CLI writes it with `convert --audit FILE`; the website offers it as a CSV next
to the plugin. Sir Mauriac's Tale gives 4,752 rows for 108 tags. Building it
is what exposed the sequence-slot assumption above. Other tag types are to
follow.

## 30. Why the Forest Giants and Trow would not attack (0.17)

Keep's 0.16 tests (Q7, 16 Nov): moonwalking, explosions and netgame flags and
balls fixed; Forest Giants, Old Growth Forest Giants and Yearlings still do not
engage smaller, non-giant units. Two bugs, both found by comparing our output
with Bungie's and Magma's versions of the same units.

**1. Every unit was giant-sized.** The converter copied TFL's `intelligence`
into Myth II's `size`, because they share a byte slot and mythextract declares
both as `Size`. But TFL's field is AI intelligence: 2 for 40 of 46 stock units
(0 for 4, 1 for 2). Myth II's size is small 0, man 1, giant 2, and in Bungie's
and Magma's versions of the TFL units it is 1 for all but the forest giants and
trow (`ent.`, `trra`): 21 of 23 mismatched. Now set by collection, man by
default (`GIANT_COLLECTIONS`); 24 of 24 paired units match both references.
Only tiny creatures (chickens, frogs, birds; none in TFL) are small.

**2. Attack flag bits were copied raw.** TFL's flag word has CHOOSES_SEQUENCES_
RANDOMLY at bit 11, then VS_GIANT_SIZED and PROHIBITED_VS_GIANT_SIZED at 12-13.
Myth II has no random-sequences flag, so its two giant flags sit at bits 11-12.
Copied raw, the Forest Giant's first attack (TFL 0x1b00: random + vs giant)
became 0x1b00 in Myth II: vs-giant AND prohibited-vs-giant, which can never be
used; its second (0x0b00) became "vs giant only". Now bits 12-13 move down and
bit 11 is dropped. And in all 9 units of Bungie's tags and Magma's port with a
giants-only attack (forest giants, trow, the changeling), every other attack is
prohibited against giants, since Myth II does not choose between them as TFL's
engine did; the converter does the same. The result for the Forest Giant and
trow is exactly Bungie's and Magma's `0xb00`, `0x1300`. Not yet confirmed
in-game.

A giant-sized, giants-only attack on every unit would have kept the giants
fighting only each other, which fits the symptom; the pathfinding radius fix
(0.15) was real but not the cause.

## 31. Heals, and Assassin targets (0.18; Keep, Q7, 17 Nov)

**Heals.** Journeymen and Heron Guards could neither heal themselves nor others
(Keep, long-standing); the Yearlings' mandrake heal did not work on themselves.
Myth II's `AttackExtraFlag.CAN_BE_USED_AGAINST_FRIENDLIES` (bit 0 of the u16 at
byte 60 of the 64-byte attack) lets an attack target friendly units; TFL had no
such flag and the converter wrote `extra_flags = 0` on every attack. In Bungie's
tags every Journeyman- and Heron Guard-type heal (a special ability, flags
0x290, firing the healing projectile `johg`: damage type 3 = HEALING, 20) has it
set, 7 of 8 (the exception, `20hg`, the crystal Heron Guard, is a statue); Magma's
journeyman does too. TFL's Journeyman projectile `jo#2` has the same signature.
So `allow_healing_friendlies` sets it on any special-ability attack whose
projectile has damage type HEALING. Only the stock Journeyman and Mauriac's
Yearling match. The Yearling is less certain: its heal has TFL's "avoids
friendly units" bit (0x400) and no reflexive bit, and Keep says it should heal
only itself, which no Bungie unit shows us; whether Myth II then lets it heal
others is for the game to say. Not yet confirmed in-game.

**Assassin targets.** A target is a placed unit whose marker has
`IS_NETGAME_TARGET` and whose palette entry's netgame types include Assassin
(bit 11). Keep's suggestion, that targets are the units players cannot trade,
holds in Bungie's data: of 282 targets in 38 Assassin maps, all 282 are on
non-tradable palette entries and none on a tradable one; but only 282 of 1,132
non-tradable units are targets, and 129 of the 207 TFL community meshes that
declare Assassin have non-tradable units (many are arenas where all are). In
Sir Mauriac's two (`swda`, `swed`) every placed unit is tradable, so the rule
finds none; they would need a unit added in Loathing. Not derivable, so the
converter does not guess. (The palette index counts within a marker type, not
across the whole palette; an earlier look at this that did not know that was
wrong.)


## 32. Unit scale (0.13)

Written up on 17 November 2026 from the code (`src/convert/tags/obje.py`) and
the 0.13 release; the work itself was done on 16 November.

Copied unchanged, TFL's monster scale drew converted units about a third too
tall in Myth II (Keep: thrall stood out of water they wade in up to the chest in
TFL). Myth II's own stock tags ship seven of TFL's collections with the same
pixels (thrall, dwarf, ghol, soulless, spider, avatara, balor), and Bungie gave
every one TFL's scale times 0.728: the standard 0.934 became 0.680 for the
thrall, dwarf, ghol and avatara, the spider's 0.797 became 0.590, the balor's
1.188 became 0.879. Bungie also cut the random spread on top to about a twelfth
(thrall +0.129 to +0.012, dwarf +0.117 to +0.008). Magma's *The Fallen Lords
v1.9* reuses those values.

So the per-monster object (§18) takes the lower bound times `SCALE_FACTOR`
(174/239, which maps 0.934 onto 0.680 exactly) and the delta divided by
`SCALE_DELTA_DIVISOR` (12). Two units Bungie retuned by eye (villagers x0.91,
the Shade x0.80) are not modelled.

**Open.** Heroes may come out 10-14% taller than in Magma's port: ours give the
berserk hero and fir'bolg hero about 0.80, Magma's about 0.70. Waiting for Keep's
measurements against the Butcher's shop on Crow's Bridge before changing it.
