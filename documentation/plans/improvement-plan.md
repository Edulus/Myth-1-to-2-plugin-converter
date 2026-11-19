# Improvement plan (Fable 5.2's review, 16 November 2026)

Reviewed 16 November 2026 at commit `8097018` (0.12 released; the unit-scale fix
committed locally but not yet released). The review covered `src/`, `tests/`,
`scripts/`, `web/`, `comments-worker/`, README and NOTES, plus two measurements
made for this document against the stock TFL tags, Myth II's stock tags and
*Magma - The Fallen Lords v1.9*. What was not reviewed is listed at the end.

## Status (17 November 2026)

Converter 0.18. The plan below is kept as written on 16 November; this table
says what has happened to each item since.

| Item | Status |
|---|---|
| A1 Level-of-detail block | **Done** in 0.14: written as `00f0` words, as Loathing does ([notes §27](../notes/maps.md)). Keep confirmed on 0.16: no black ground after explosions |
| A2 Types copied unchanged | `amso` **done** (0.13, [§33](../notes/stock-tags.md)). `prgr`, `phys`, `core`, `soun`: no change needed. `medi` **open** (needs a converter). `lpgr` undecided. `ligh`, `wind`: need samples |
| A3 References in map-action parameters | **Done** 18 November: sound and projectile ids follow the ID map and are counted as references ([notes §14](../notes/maps.md)) |
| A4 Unit behaviour, per unit | **Done** in substance: per-collection values (0.15, §28), pause and turning animations (0.16, §29), size and attack flags (0.17, §30), heals (0.18, §31), in [notes/units.md](../notes/units.md). Moonwalking confirmed fixed; 0.17 and 0.18 await testing. Still open: per-map lighting, the villager and Shade scale exceptions, hero height (§32) |
| A5 One bad tag stops a conversion | **Done** in 0.13 (§33) |
| B1 Compare command | **Done** 18 November: `python -m src compare --ours ... --ref ...` pairs tags by id (or name), and per type reports identical and resized pairs, the byte ranges that differ systematically, their commonest value changes and, where the layout is declared, the fields. About 2 seconds on Myth II's whole stock. Reproduces the [§33](../notes/stock-tags.md) table |
| B2 Real-data regression gate | **Done** 18 November: `scripts/regression.py` converts *Sir Mauriac's Tale* with every stock tag and checks every tag's hash against `tests/regression/manifest.json`, plus per-type counts of tags identical to Magma's port. Proved by changing the scale rule (caught: 14 objects). Runs locally, not in CI (no game files there) |
| B3 Continuous integration | **Done** 18 November: `.github/workflows/ci.yml` runs the Python suite, the comment service's tests, and checks `docs/` is what the generator builds. The generator now builds identically on Windows and Linux (Unix line endings, stored zip, pinned zip system byte). A test ties `pyproject.toml`'s version to the converter's |
| B4 In-game checks | Partly: each version's `test` list in `web/convert/changes.json` and the home page's "Please test now" list |
| C1 Script the release | **Done** 18 November: `scripts/release.py` (build only, or `--publish`); checked to reproduce the published 0.18 plugin and Read Me byte for byte. Steps in [../site-and-releases.md](../site-and-releases.md) |
| C2 Site content apart from its generator | **Done** 19 November: updates, questions and their summaries, the work list, the poems, the unit table and Keep's page text are TOML files in `site/content/`; `scripts/keep_site.py` (1,382 lines before, about 1,125 now) reads them and stops with a clear message on a missing or malformed file. The rebuilt `docs/` is byte-identical to the previous build. Steps in [../site-and-releases.md](../site-and-releases.md); `tests/test_site_content.py` checks every file |
| C3 Stock TFL files in the repository | **Decided** 18 November: keep hosting them, so the converter page and the ready-made download need nothing from the player. The Safe Browsing flag, once a suspect, was traced to the owner's separate Space Pong page, not to these files, and is resolved |
| C4 Housekeeping | **Done** 18 November: `git gc` took `.git` from 1.2 GB to 187 MB (28 leftover temporary objects removed, `git fsck` clean); `debug.log` deleted and ignored; `CODEX-HANDOFF.md` in the ignored `local/archive/` |
| D1 Our posting names can be claimed by anyone | **Done** 18 November: posts under our names need the `X-Staff-Key` secret (see [../site-and-releases.md](../site-and-releases.md)). Look-alike spellings (a Cyrillic Е in "Еdward", fullwidth letters, accents) are also reserved since 18 November. Checked in the Cloudflare dashboard on 18 November: Workers Logs shows `x-staff-key` as REDACTED, so the key is not exposed there. Nothing remains |
| E1 Stale comments | The three listed are fixed; one more found and fixed on 17 November (mesh LOD comment) |
| E2 Split `src/mesh.py` | Done 18 November: the conversion policy (terrain upsampling, grounding and anchoring, LOD, netgame masks, map-action fix-ups, ID remapping) moved to `src/convert/meshrules.py`; `src/mesh.py` keeps the layouts. |
| E3 Browser memory | Open; no failures reported |
| F Documentation | **Done** on 17 November: NOTES.md split by topic into [../notes/](../notes/), superseded passages marked, current rules in [../conversion-rules.md](../conversion-rules.md) |

## Summary

The converter's foundations are sound. The container reader and writer are
byte-exact on 282 real archives, every conversion rule in the code cites the
measurement behind it, 380 tests pass, and the local app's web server is
properly locked down. The weak points are elsewhere:

1. **Three tag types are copied unchanged but do differ in Myth II** (`amso`,
   `lpgr`, `medi`). This is new evidence from this review; see A2.
2. **The explosion glitch has one prime suspect that has never been decoded**:
   the level-of-detail block, which the converter fills with zeros (A1).
3. **Every correctness fix so far came from one method, done by hand each
   time**: compare our output with Bungie's or Magma's version of the same
   thing. That method should be a command, and its results a regression test
   (B1, B2).
4. **Releasing is manual and undocumented.** The steps for the Sir Mauriac zip
   exist only in old session logs (C1).
5. **Anyone who knows the Myth answer can post on the site under a staff
   name** (D1).

The recommended order is at the end.

## A. Conversion correctness

These are the items players will notice.

### A1. Decode the level-of-detail block (explosion glitch)

`mesh.build_lod_data` (`src/mesh.py:942`) writes zeros at the right size
because the block's encoding is unknown. Keep found that saving a converted map
in Loathing, with any trivial change, removes the black patches explosions
leave. Loathing therefore rewrites something we write wrongly, and this block
is the only part of a mesh the converter invents wholesale.

Plan:

- Do not wait for Keep's before-and-after pair to start. Myth II's 65 stock
  meshes and Magma's 40 are 105 examples of a correct block next to the
  terrain it was computed from. Test the obvious hypotheses against them:
  per-cell or per-block minimum and maximum heights, error bounds for a
  quadtree, flags per 2x2 or 4x4 group. The function's own comment records
  that real blocks are about half zero bytes with `0xF0` and `0xFF` common,
  which suggests packed nibbles or bit masks.
- When Keep's pair arrives, diff it block by block. If only the LOD block
  changes, the hypothesis is confirmed and the pair is the test case. If
  something else changes, that is the lead instead.
- Fallback if the encoding resists: document "open in Loathing and save" as a
  finishing step, and install Fear and Loathing locally so pairs can be made
  on demand.

Size: medium to large, uncertain. Highest player-visible value.

### A2. Three "copied unchanged" types need converting

The README says of the pass-through types that it is "unverified whether these
differ at all". Measured for this review, pairing each stock TFL tag with the
tag of the same id in Magma's port and in Myth II's own files, same-size pairs
only:

| Type | Pairs (Magma / Bungie) | Byte-identical | Bytes that differ in 60% or more of pairs |
|---|---|---|---|
| `amso` ambient sound | 22 / 33 | 0 / 0 | 20-36 in both; TFL has zeros where Myth II has `FF` |
| `lpgr` local projectile group | 13 / 11 | 0 / 3 | 62-76 on even bytes; TFL 0, Myth II 1 |
| `medi` media (water) | 7 of 9 same size | 0 | many, from byte 26 on; 2 of 9 also change size |
| `ligh` lightning | 3 / 2 | 0 / 0 | 15, 18, 27, 52, 55 (too few pairs to be sure) |
| `prgr` projectile group | 41 / 90 | 3 / 24 | none |
| `phys` | 6 / 10 | 1 / 4 | none |
| `core` | 152 / 68 | 99 / 4 | none against Magma |
| `soun` | 272 / 182 | 118 / 65 | none |

Reading:

- **`amso`**: bytes 20-36 look like unset tag references. TFL writes zero for
  "none" and Myth II writes `FFFFFFFF`, the same difference the `proj`
  converter already handles. Unconverted, Myth II may look up a tag with id
  zero. Small fix.
- **`lpgr`**: a run of 16-bit fields that are 0 in TFL and 1 in both Myth II
  sources. Probably a field Myth II added in space TFL left empty. Small fix
  once the field is named from mythextract or the Fear manual.
- **`medi`**: the water definition differs widely and sometimes in size. It
  deserves a proper converter. Water is a known sore point (thrall in water,
  riverbanks).
- **`prgr`, `phys`, `core`, `soun`**: no systematic difference. Pass-through is
  right; the README can say so with these numbers.
- `wind` (2 pairs) and `ligh` need more samples; community plugins can supply
  them.

Size: small for `amso` and `lpgr`, medium for `medi`.

### A3. Remap tag references inside map-action parameters

Marker palettes and mesh headers follow the ID map; `SOUND` and `PROJECTILE`
typed map-action parameters do not (`src/convert/tags/mesh.py:41-45`). With the
default map this is harmless because IDs do not change. It matters as soon as a
decisions file renames a tag, and it matters now for the netgame flags and
balls that 0.12 redirects to Myth II's ids: a script that names one of the four
renamed objects still points at the TFL id. `mesh.PARAM_TYPE_TAG` already says
which parameter types hold which tag type, so the walk exists; only the rewrite
is missing. The same walk should feed `unresolved_references` and the stock
bundler, which today find these references only by scanning for byte patterns.

Size: small to medium.

### A4. Unit behaviour: use Bungie's own values, per unit

Open reports: units jog on the spot when they stop, Forest Giants and Trow will
not attack. The `mons` converter fills 17 Myth II-only fields with one default
each, and two are admitted guesses: `pathfinding_radius` (77, the plurality at
28 of 60) and `more_hack_flags` (a three-way tie).

Today's scale fix shows a better source. Myth II ships seven TFL units with the
same sprites, and Magma ports 24. For those, the correct value of every Myth
II-only field is known per unit, not as a majority vote.

Plan:

- Build a table keyed by TFL monster id (and collection) of Bungie's and
  Magma's values for the synthesised fields. Use it where a converted monster
  matches; keep the defaults for custom monsters, but choose them by unit size
  class instead of globally.
- For the two bugs, diff our converted Forest Giant and Trow field by field
  against Magma's (`fg`, `trow`) rather than guessing. Attack definitions and
  sequence indexes are the first place to look for "will not attack"; the
  16-to-26 sequence slot mapping is the first for "jogs on the spot".
- Same idea for the two scale exceptions (villager, Shade) and for `meli`,
  where every TFL lighting tag currently becomes the same lighting although
  Magma's port has per-map values to compare with.

Size: medium. High value.

### A5. One malformed tag should not stop the whole conversion

`convert_container` calls each converter with no guard
(`src/convert/plugin.py:275`). Converters check body length, and the mesh
converter guards its blocks one by one, but an unexpected `struct.error` or
`ValueError` inside any other converter ends the run. Community plugins are
hand-edited and sometimes odd. Catch per tag, pass the body through, and report
it as "could not be converted: reason", which is the pattern the mesh converter
already uses for its blocks.

Size: small.

## B. Verification

### B1. Make "compare with a reference port" a command

Scale, edge widths, netgame masks, collection layout and water were all settled
by pairing our output with Magma's or Bungie's and reading the differences.
Each time the pairing script was written from scratch and thrown away. Three
were written today.

Add `python -m src compare`:

- pair tags between a converted plugin and a reference (by id, with fallbacks
  by name and, for meshes, by size);
- per tag type, report same-size and identical counts and the byte ranges that
  differ systematically, named by field where the layout is known;
- write the result as a table that can be kept.

This turns every open question in section A into running one command, and it
is how the two tables in this document were made.

Size: medium. It pays for itself on A2 and A4.

### B2. A real-data regression gate

The 380 tests use synthetic fixtures. The five real-data tests skip unless
environment variables are set, so in practice nothing checks that a change
leaves *Sir Mauriac's Tale* alone except by hand. Today's scale change was
checked by an ad hoc script ("only 57 `obje` bodies changed").

- Keep a manifest in the repo: for each tag of the converted reference plugins,
  a hash of its body. No game data is committed, only hashes.
- A test, run when the local game files are present, converts and compares
  against the manifest and prints which tag types changed. An intended change
  updates the manifest in the same commit, so the diff shows its reach.
- Add the similarity scores from B1 for the stock tags against Magma as
  tracked numbers, so a rule change that moves us away from the reference
  shows up.

Size: small to medium.

### B3. Continuous integration

There is no `.github/workflows`. Add one job that runs the Python suite and the
worker's tests on every push, and fails if `python scripts/keep_site.py` leaves
`docs/` different from what was committed. The version number lives in three
places (`pyproject.toml`, `src/__init__.py`, `web/convert/changes.json`); a
test ties the last two together but not `pyproject.toml`. Read the version from
one place.

Size: small.

### B4. In-game checks

In-game testing is the scarce resource: it needs a person, and Keep is one
volunteer. Write the checks down once as a short list per release (which
level, what to look at, what "right" looks like) so that any tester can run
them and results can be compared between versions. Where a check can be
replaced by a file comparison against a port (B1), do that instead.

## C. Release and site engineering

### C1. Script the release

To publish 0.12 today the steps had to be recovered from earlier session logs:
which source file, which stock archives and flags, how the Read Me's version
line is edited, the fixed zip layout, the upload and the checksum check. The
source plugin itself sits in a temporary folder from an October session.

Add `scripts/release.py` that builds the plugin, writes the Read Me from a
template with the version filled in, zips, prints the checksum, and, with an
explicit flag, uploads, updates the release notes and `DOWNLOAD_SHA256`, and
verifies a fresh download. Keep the source plugin under `local/`, which is
already ignored.

Size: small. Removes a recurring risk of releasing the wrong build.

### C2. Separate the site's content from its generator

`scripts/keep_site.py` is 1,242 lines holding the templates, the stylesheet,
every update, every question and its summary as Python strings. Each content
edit is a code edit, and one long line holds a whole page summary. Move
updates, questions and summaries to data files (TOML or Markdown with front
matter) that the script reads. The generator then changes rarely and content
changes are reviewable.

Size: medium. Do it when the next round of site changes is due, not before.

### C3. The stock TFL files in the repository

`docs/convert/stock/` holds TFL's `TAGS.GOR` and `ARTSOUND.GOR` in pieces, 320
MB, committed and served from GitHub Pages. The README records this as a
deliberate choice so that visitors need nothing installed. Three costs are
worth weighing again:

- It is the one place the project republishes game data in bulk. The rights
  position is the owner's call; the review only notes that everything else in
  the repository is careful to avoid it.
- The site was flagged by Safe Browsing in November. The cause was later found
  to be the owner's separate Space Pong page on the same host (resolved), not
  these files.
- Every clone carries the files.

An option that keeps the convenience: let the page accept the visitor's own
`TAGS.GOR` and `ARTSOUND.GOR` (it already caches large files), and serve only
the stock tags needed for the common case, or host the pieces as a release
asset instead of in Pages. This is a decision for the owner, not a
recommendation to remove them.

### C4. Repository housekeeping

- `.git` is 1.2 GB, of which 993 MB is 28 leftover temporary objects from
  interrupted operations, and nothing has ever been packed. `git gc --prune=now`
  should bring it to roughly the size of the real history. Run it when no
  other git process is active.
- `debug.log` (browser crash-reporter noise) and `CODEX-HANDOFF.md` sit
  untracked in the root. Ignore the first; delete or archive the second once
  it is no longer needed.

Size: minutes.

## D. Security

### D1. Staff names can be claimed by anyone

The comment service marks a post as staff when its name matches `STAFF_NAMES`
(`comments-worker/src/core.js:157-161`). Posting needs only the shared Myth
answer, which is how replies as "Claude Opus 5.5" are posted today. A visitor
can therefore post under a staff name and the page will show it as an official
answer. On a site that hands out downloads, a false "official" post pointing
somewhere else is the realistic abuse.

Fix: require a secret for staff names. Add a worker secret, accept it in a
header, and reject a staff-named post without it. Roughly ten lines plus a
test.

Size: small. Do this first; it is the only finding that exposes other people.

### D2. What was checked and found sound

- The studio server binds to loopback, rejects foreign `Host` and `Origin`
  headers, requires a per-run token and guards against path traversal, with
  tests for each.
- The worker rate-limits posts, votes and conversion logging per address,
  caps body size, sniffs image types and refuses SVG.

## E. Code health

### E1. Stale comments in the modules that matter most

The code's habit of explaining itself is one of its strengths, which makes the
out-of-date passages costly: a future session will believe them.

- `src/convert/tags/mesh.py:43-45` says terrain is upsampled by copying each
  cell; heights have been blended since section 20 of NOTES.
- `src/convert/tags/mons.py:33-41` says carrying `effect_modifiers` to the
  object is out of scope; `plugin._give_monsters_objects` does it.
- `src/convert/plugin.py:10-13` uses `arti` as the example of a passed-through
  type; `arti` converts.
- README "Honest limitations" and the support matrix need the results of A2.

Size: small. Fix alongside the next change to each file.

### E2. `src/mesh.py` does two jobs

At 1,067 lines it holds both the format (header layouts, marker and map-action
structures) and conversion policy (terrain upsampling, ground lowering beside
models, netgame masks). The policy belongs under `src/convert/`, next to the
mesh converter that calls it, leaving `src/mesh.py` as the layout module the
swap tool and the reader also depend on. Move, do not rewrite; the tests
already cover the functions.

Size: small to medium, mechanical.

### E3. Memory in the browser

A conversion holds the upload, both stock archives, the combined container and
the packed output in memory at once; the README measures about 1.1 GB for
*Sir Mauriac's Tale*. Phones and small laptops will fail. The reader slices
bodies out of one buffer and the writer builds one `bytes`; a `memoryview`
reader and a writer that streams to the output file would remove most of the
copies without changing any converter. Measure first with the largest
community plugin available.

Size: medium. Worth doing only if testers report failures.

## F. Documentation

NOTES.md is 1,917 lines in the order things were discovered. That is the right
record, but the current rule for a given tag type is spread over several
sections, some superseded (object scale appears in sections 16, 18 and now
today's change). Add a short "current rules" index at the top: one line per
tag type and per mesh block, stating the rule and pointing at the section that
justifies it. Keep the history below it untouched.

## Suggested order

| Step | Items | Why now |
|---|---|---|
| 1 | D1, C4, A5 | Small, independent, and D1 protects visitors |
| 2 | C1, B3 | Makes every later release safe and repeatable |
| 3 | B1, then A2 | The comparison command, proved on the three types that need converting |
| 4 | A1 | The explosion glitch, with B1 as the tool |
| 5 | A4, A3 | Unit behaviour and script references |
| 6 | B2, E1, E2, F | Lock in what has been learned |
| Later | C2, C3, E3 | When site work is due, or when the owner decides |

## Not reviewed

- The Civil War swap tool (`swap.py`, `swapstream.py`, `webswap.py`) beyond
  its structure.
- The site's pages and copy, and `web/*/page.js`.
- `src/views/html.py`, `src/plan.py` and `src/decisions.py` in detail.
- Behaviour in the game itself. Nothing in this document was tested in Myth II.
