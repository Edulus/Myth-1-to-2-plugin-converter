# Documentation

Everything written about this project apart from the code, its user guide (the
[README](../README.md)) and the public website. Newer documents take precedence
over older ones; where an older passage was overturned, it carries an
**Update** note saying what replaced it.

## Start here

| Document | What it is for |
|---|---|
| [conversion-rules.md](conversion-rules.md) | What the converter does to each tag type **now**, and what has been checked in the game |
| [site-and-releases.md](site-and-releases.md) | The website, its comments, and how to publish a converter version and the ready-made download |
| [plans/improvement-plan.md](plans/improvement-plan.md) | Fable 5.2's codebase review of 16 November 2026, with the status of every item |

## The notes

The research record: how each format fact and conversion rule was found, with
the measurements behind it. Written as the work happened, so a section can be
overturned by a later one; each file opens with a short "Where this stands"
summary, and overturned passages carry an **Update** note.

Sections keep their original numbers (§1 to §35), which the code cites as
`documentation/notes/<file>.md section N`. There is no §10.

| File | Sections | Topic |
|---|---|---|
| [notes/prior-art.md](notes/prior-art.md) | 1, 2, 7 | mythextract: what it gave us, file by file, and its bugs |
| [notes/containers.md](notes/containers.md) | 3, 4, 5, 6, 8, 9, 11 | Container and tag-header layout, the round-trip gate, checksums, the 32-character filename limit |
| [notes/maps.md](notes/maps.md) | 12, 13, 14, 15, 20, 21, 22, 23, 24, 27 | Mesh header, entrypoints, markers and map actions, terrain resolution, heights, edges, cell flags, map version, the level-of-detail block |
| [notes/units.md](notes/units.md) | 16, 28, 29, 30, 31, 32, 34, 35 | `mons` and `unit`: attacks, Myth II-only fields, animations, size, attack flags, heals, Assassin targets, scale, teal death pieces, uphill throws |
| [notes/models.md](notes/models.md) | 17 | `mode` and `geom`: footprints, anchors |
| [notes/stock-tags.md](notes/stock-tags.md) | 18, 33 | Converting the stock TFL tags layer by layer until levels played; the types still copied unchanged |
| [notes/multiplayer.md](notes/multiplayer.md) | 26 | Netgame types on palette entries; flags and balls |
| [notes/unit-swapper.md](notes/unit-swapper.md) | 19, 25 | The Civil War unit swapper, on the command line and in the browser |

## Elsewhere

- [../reference/README.md](../reference/README.md): the third-party material
  studied (mythextract, the Fear and Loathing manuals, Iron's mesh converter)
  and how to get it back; the material itself is not in the repository.
- [../NOTICE](../NOTICE): attribution and the trademark position.
- `tests/regression/manifest.json`: hashes of every tag of the reference
  conversion, checked by `scripts/regression.py` (see the README's Tests section).
- `web/convert/changes.json`: every converter version and what it changed,
  shown on the website's converter page.
- `local/` (ignored by git): the release source plugin and texts
  (`local/release/`), and finished one-off documents (`local/archive/`).
