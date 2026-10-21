# Progress log for KEEP

Updates on the converter, newest first, and the questions we need your help
with. Answer by number whenever it suits you -- a line in Myth chat like
"Q1 yes, Q3 coop maps first" is plenty.

---

## 21 October 2026 -- TFL levels now play in Myth II

**The headline: two levels from *Sir Mauriac's Tale* now load, play and finish
in Myth II 1.8.5, converted entirely by the tool.**

- **Tandem** -- the river level with 77 buildings. Rain falls, units and trees
  are drawn, the fighting works, and it ends on the normal end-game screen.
- **In the Name of Glory** -- the snow level, with 146 scripted map actions.
  Plays from the start to the end-game screen with no errors in the log.

Your TFL tags folder is what made this possible. A TFL plugin leans on the stock
TFL tags the way a Myth II plugin leans on the base game, and Magma's port
doesn't carry them all under their original names -- *Tandem* alone needed 76
it lacked. Converting your `TAGS.GOR` and `ARTSOUND.GOR` into a Myth II tagset
solved all of them at once. (Your files stay on our machine; no game data goes
into this repository.)

### What converts now

Everything below goes from TFL format to Myth II format automatically:

| | |
|---|---|
| Maps | terrain (upsampled to Myth II's finer grid), markers, map actions, buildings' footprints |
| Units | monsters, units, and each monster's own "object" (its size, health and damage resistances) |
| Combat | projectiles, artifacts, mesh effects (explosion ripples) |
| World | scenery, weather (rain/snow), lighting, sprite art |
| Text | level names, captions, subtitles |

Some of what we learned along the way, in case it's useful to you:

- **Why units were invisible at first:** in TFL a monster's size, health and
  damage resistances live on the monster. Myth II moved them into a separate
  "object" tag that TFL shares between every monster. Read by Myth II, TFL's
  object says "size 0", so every unit and tree was there (you could hear them
  fight, and see their shadows) but drawn at zero size. Each monster now gets
  its own object, which is what Project Magma did by hand in their port.
- **Myth II halved the world unit**, as the Fear manual warns. It shows up in
  places -- a ground ripple's height doubles, for instance -- but not
  everywhere: unit speeds and ranges did not need doubling.
- **Your point about models was right.** TFL stores each building's footprint
  in terrain cells, and Myth II's cells are half the size, so footprints have
  to be split 2x2. That's measured against your tags; the converter for it is
  next on the list.
- **Some stock TFL tags must not replace Myth II's.** The end-of-level
  statistics screen crashed until we stopped TFL's versions of Myth II's
  internal text, dialogs and fonts from overriding the originals.

### What's still rough

- **Lighting** converts, but every map currently gets the same standard
  lighting. A dark cave would come out as bright as a meadow.
- **Sounds, collection references, projectile groups and a few other types**
  are still copied across unchanged. Both test levels play fine with them as
  they are, but they haven't been checked one by one.
- **Building models** (`mode`/`geom`) are measured but not converted yet.
- **Terrain is upsampled by copying**, not smoothing -- each TFL cell becomes a
  2x2 block. Faithful, but blockier than a hand-made port. (See Q2.)
- Only two levels have been tested so far, both single-player.

### How to try it yourself

You need Python 3.12 or later, and Myth II 1.8.5. From this repository:

```sh
# 1. Once: turn your TFL tags folder into a Myth II tagset.
python -m src tagset --in "TFL/tags/TAGS.GOR" --in "TFL/tags/ARTSOUND.GOR" \
    --out "Myth II/plugins/ZZ TFL stock"

# 2. Convert a TFL plugin.
python -m src convert --in "Sir Mauriac's Tale.gor" --out "Myth II/plugins/ZZ Mauriac"
```

In Myth II: New Game -> pick the converted campaign -> **Tagsets** -> activate
`ZZ TFL stock` -> pick a level. Choosing a campaign clears the tagset, so pick
the tagset *after* the campaign.

---

## Questions for you

**Q1. Which TFL content matters most to you?** The original campaign? Specific
community plugins? Multiplayer maps or single-player? Whatever you name, we'll
test next.

**Q2. Terrain: faithful or smooth?** TFL's terrain is a quarter of Myth II's
resolution. We copy each TFL cell into a 2x2 block, which invents nothing but
looks blockier than Myth II maps. Smoothing it would look closer to a native
map but means inventing detail. Which would players rather have?

**Q3. Is there a coop map with known scoring we could test against?** You
mentioned coop scoring and map actions -- we've converted the map-action format,
but we don't yet know whether TFL and Myth II scripts *mean* the same thing in
play. A map whose correct behaviour you know would tell us.

**Q4. TFL gameplay or Myth II gameplay?** Myth II has a built-in "TFL Gameplay"
option that changes the rules to behave more like TFL. We've been testing with
normal Myth II rules. Should converted levels be meant for TFL rules?

**Q5. Would you play-test?** A converted level played by someone who knows TFL
well would find the subtle problems -- wrong unit sizes, sounds, balance -- that
logs can't.

**Q6. What does "done" look like for you?** A tool anyone can run? A finished
pack of converted maps to share? Both?

---

## Earlier progress, briefly

- **July 2026** -- The groundwork: reading and writing Myth containers, checked
  byte-for-byte against 282 real files (about 10.5 GB). Confirmed in-game that
  Myth II doesn't check plugin checksums, which removed the biggest early risk.
  Converted maps first appeared in Myth II's level list but wouldn't start.
- **August 2026** -- Map terrain, markers and map actions; monsters and units.
  Found and fixed a numbering mismatch in TFL map-action parameters that was a
  likely cause of early crashes.
- **October 2026** -- Your tags arrived; the rest is the October entry above.
