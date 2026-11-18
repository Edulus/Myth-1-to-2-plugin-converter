# Multiplayer: netgame types, flags and balls

**Where this stands (17 November 2026).** Fixed and confirmed by Keep: units,
scenery, flags and balls appear in hosted games (0.11, 0.12). Assassin targets
cannot be derived from TFL maps and are not guessed (§31, in
[units.md](units.md)).

## 26. Which game types a palette entry appears in

Keep (Q7, 15 Nov) found why hosted free-for-all games on converted maps had no
teams, flags, balls or scenery although Loathing showed them all in the map:
each marker palette entry carries `netgame_flags`, the "Appears in Netgame Type"
list (Body Count, Steal the Bacon, Last Man on the Hill, Scavenger Hunt, Flag
Rally, Capture the Flag, Balls on Parade, Territories, Captures, King of the
Hill, ...; one bit each). TFL's maps leave it 0 on nearly every entry (the odd
0x763d8 and 0x76a78 on a few are not game types), and Myth II reads 0 as "in no
game". With "Single Player Map" ticked the field is not consulted, which is why
every element then appeared.

Bungie's Myth II maps (47 in `small install`, 18 in `Patch 1.8.5 Maps`) and
Magma's ports mark almost every unit, scenery and model entry 0xFFFF (Magma
also 0x3FFF, the fourteen types). Observers, sounds and projectiles are 0 about
as often as 0xFFFF in Bungie's netgame maps, and are left as they were. The
netgame objects carry one game type each, Bungie's as 0xC000 plus the bit:

| Object (TFL id) | Mask | Game |
|---|---|---|
| steal the bacon ball (`neto`) | 0xC002 | Steal the Bacon |
| last man flag (`nefl`) | 0xC004 | Last Man on the Hill |
| balls 1-5 (`neb1`-`neb5`) | 0xC008 | Scavenger Hunt |
| flags 1-5 (`nef1`-`nef5`) | 0xC010 | Flag Rally |
| capture the flag flag (`nect`) | 0xC020 | Capture the Flag |
| balls on parade ball (`nebo`) | 0xC040 | Balls on Parade |
| territories flag (`nedf`) | 0xC080 | Territories |
| captures ball (`necb`) | 0xC100 | Captures |
| king of the hill flag (`nelm`) | 0xC200 | King of the Hill |
| rugby ball and goal (`nerb`, `nerg`) | 0 | none in Myth II |

(Myth II's own ids differ: `nest`, `nelf`, `netf`, `neko`; the converted plugin
carries TFL's, so the table is keyed by those.) Units whose game type is narrower
in Bungie's maps (assassin targets 0x800, stampede herds 0x400, heroes missing
one type) depend on how each map was authored and are not derived: they are
marked for every type until a rule for them is found. 0.11. The `version` 7 to
11 change of 0.10 did not fix the explosion glitch, which Keep reproduced on 0.10.

> **Update:** Assassin targets examined in §31 ([units.md](units.md)): not derivable.

**No rule is to be had from TFL's maps (16 Nov).** Bungie's own TFL netmaps
(`TAGS.GOR`, `SCRAP.GOR`) never set the Stampede (bit 10) or Assassin (bit 11)
header bits, so stock TFL had neither game. Community maps do: of 971
multiplayer TFL meshes scanned (Mauriac, the UMM set, Fallen Levels v2), 219
declare Assassin and 47 Stampede, presumably for later community patches. But
in all 219 Assassin maps every unit palette entry's `netgame_flags` is 0 (4,724
entries): nothing marks which unit is a target. So units stay marked for every
type. Two Mauriac meshes declare Assassin (`swda`, `swed`, both "07 Bagrada in
Winter" variants); whether Myth II picks targets on them is for an in-game test.


### Flags and balls: Myth II's own (0.12)

With 0.11 units and scenery appeared in hosted games but the flags and balls
did not (Keep, Q7). The bundled TFL copies are the cause. Seven share an id with
a Myth II tag (`neb1`-`neb5`, `nebo`, `necb`, `nect`, `nef1`-`nef5`), so they
override Myth II's own; the converted `nef1` differs from Myth II's in the
collection it names (`baob` against `inob`) and in a flag word at byte 16 (4 in
Myth II's, 0 in ours), and the engine does not treat it as a flag. Four have
ids Myth II lacks: `neto`, `nefl`, `nedf`, `nelm`, which are Myth II's `nest`,
`nelf`, `netf`, `neko` (checked by name in `small install`).

So the converter no longer carries them (`MYTH_II_NETGAME_SCENERY`, via
`is_engine_facing`), points maps at Myth II's ids (`NETGAME_OBJECT_IDS`), and
does not report them unresolved. Only the rugby ball and goal, which Myth II
has no counterpart for, are still carried, with a mask of 0.

Not yet understood: Keep found that opening a converted mesh in Loathing and
saving it with any trivial change makes the explosion ripple glitch disappear,
on 0.9, 0.10 and 0.11 alike. So Loathing writes something in the mesh that the
converter writes differently. Candidates: the level-of-detail block, which the
converter fills with zeros and whose structure is not per cell (Magma's shows a
period-4 pattern of 0 and 0xF), the cell normals (copied from TFL, and equal to
Magma's on about half of the cells), and the media coverage region. A pair of
meshes, converted and Loathing-saved, would show which.

> **Update:** understood in §27 ([maps.md](maps.md)): Loathing rewrites the level-of-detail block, which the converter had written as zeros. Fixed in 0.14.
