# The Civil War unit swapper

**Where this stands (17 November 2026).** Works on the command line, in the local
app and in the browser; played on *Fort Sumter* and *Little Flat Top*. Needs more
testers on more maps and packs.

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

  > **Update:** explained in §31 ([units.md](units.md)): a marker's palette index counts within its marker type, not across the whole palette.

## 25. The unit swapper in the browser

The command-line swap (section 19) reads every container whole: the Civil War
Reloaded 1.8.4 maps are 518 MB, its tagset 174 MB, Myth II's own archives about
500 MB, and the output is as big as the maps again. A browser tab cannot hold
that, so `swapstream.py` does the same job in pieces:

* `LazyContainer` reads a file's header, entrypoints and directory and fetches
  a tag's body from the file only when asked. Under Pyodide the page mounts the
  visitor's files with WORKERFS, which reads them in place without copying.
* A Myth II container is [header][entrypoints][directory][bodies]. Palette
  swaps are same-size edits, and adding K restored tags grows the directory by
  K x 64 bytes, so every body moves by exactly that. The output is the source
  body region streamed in 8 MB chunks with the palette patches laid over it,
  then the added bodies. Gaps and shared bodies in the source are kept.
* `Restorer` finds which stock tags the tagset changed by comparing bodies
  only when asked, once each, instead of indexing every archive.

Checked on the real Civil War Reloaded 1.8.4 maps, tagset and Myth II archives:
the same 275 placed units and the same 481 modified stock tags as `swap`; for
the same swaps, the same 2,452 tags with identical bodies, the same entrypoints
and name. It runs in about a second (`swap`: about 2.5 s) in under 100 MB.
The output is 832 bytes larger than `swap`'s because it keeps the source's
padding. The same code runs under Pyodide in Node, and the page runs in
Chrome (WORKERFS, folder picker, Blob download): 121 side units swapped across
77 maps and downloaded as a 519 MB plugin equal to `swap`'s. A Pyodide quirk
found on the way: `py.toPy` of a JS object gives a Python dict, which has no
`to_py`. Not yet played in Myth II; `swap`'s output was, and the contents are
the same.
