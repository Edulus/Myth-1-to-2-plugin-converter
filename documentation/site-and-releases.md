# The website, its comments, and releases

How the project's public site works, how testers' comments are stored and
answered, and how a converter version and the ready-made *Sir Mauriac's Tale*
download are published. Current as of 17 November 2026.

## The site

<https://edulus.github.io/Myth-1-to-2-plugin-converter/> (short link:
<https://tinyurl.com/mythconverter>).

- **`docs/` is generated. Never edit it by hand.** `python scripts/keep_site.py`
  rebuilds all of it. The generator holds the content, the stylesheet and the
  templates; its name still says "keep" from when the site was a channel for
  Keep alone.
- **Hosting:** GitHub Pages serves `docs/` from `main`. Pushing publishes; a
  build takes one to five minutes. Check it with
  `gh api repos/Edulus/Myth-1-to-2-plugin-converter/pages/builds/latest --jq '.status+" "+.commit[0:7]'`.
- **Never remove `docs/google5781bd5b5c2cd529.html`.** It verifies the site in
  Google Search Console, which was needed after Safe Browsing flagged the site
  in November 2026.
- The pages carry a `noindex` tag. Whether to remove it is the owner's decision.

What lives where in `scripts/keep_site.py`:

| Content | Where |
|---|---|
| "What we're working on", including the "Please test now" list at the top | `DOCKET`, `DOCKET_UPDATED` |
| Update pages | `UPDATES` |
| Q pages, and the plain-words summary at the top of each | `QUESTIONS`, `QUESTION_GISTS`, `GISTS_UPDATED` |
| Keep's conversation page (`docs/keep/`) and its poems | `KEEP_PAGE`, `poem_html`, `walter_html`, `fable_html` |
| The table of unit settings (`docs/keep/units.html`) | `UNIT_FIELDS`, `units_html` |
| The ready-made download's link, size and checksum | `DOWNLOAD_*` |
| The converter page and its list of changes | `build_converter_page`; the changes come from `web/convert/changes.json` |
| The Civil War unit swapper page | `build_swap_page` |

Questions are never deleted: a finished one is marked closed, stays readable
and keeps its number.

## The in-browser converter

The *Convert a plugin* page runs this repository's `src/` unchanged under
Pyodide. `src/web.py` is its entry point; `web/convert/` holds the page's
scripts (`page.js`, `worker.js`); the generator copies them into `docs/convert/`
with the converter source zipped. It serves the stock TFL tags from
`docs/convert/stock/` in pieces and bundles the ones a plugin uses into the
output. After a conversion it offers the plugin and the change list (`audit.csv`,
one row per field per unit; see `src/audit.py`).

Unless visitors untick a box, the plugin's name, level count and converter
version go on a public "Maps converted so far" list, kept in the comments
service under the Cloudflare KV key `conversions`. To remove an entry, from
`comments-worker/`:

```powershell
npx wrangler kv key get conversions --binding VOTES --remote > conversions.json
# edit conversions.json: delete the unwanted entry
npx wrangler kv key put conversions --binding VOTES --remote --path conversions.json
```

## Comments

Every update page, Q page and Keep's page has a comment box: name, message, a
one-word Myth question (what dwarves throw), and a hidden trap field. **No
account or sign-in, ever**: one tester will not create accounts.

- The box talks to the Cloudflare Worker in `comments-worker/`
  (<https://keep-comments.edyersh.workers.dev>), which stores each page's thread
  as a GitHub Discussion in this repository, titled with the page's `term`.
- **A thread's `term` is its identity.** Changing it orphans the comments; never
  reuse a term for different content.
- Comments show oldest first, newest at the bottom. Keep reads by scrolling
  down; a newest-first order was tried on 16 November 2026 and reverted within
  the hour. Don't change it without asking Keep.
- A visitor's comment shows "waiting" until the repository owner gives it a
  rocket reaction on GitHub, then "addressed".
- New posts reach the owner's phone through ntfy.sh (`NTFY_TOPIC`, a worker
  secret). `GITHUB_TOKEN` is a secret too. Neither is ever printed or committed;
  the owner sets them with `wrangler secret put`.

**Reading and answering.** `GET /comments?term=<url-encoded term>` returns a
thread. Answers are posted with `POST /comments` (JSON: `term`, `page`, `name`,
`message`, `answer`, `website: ""`, and `replyTo` for a reply in a thread).

**Names.** Each Claude model posts under its own name ("Claude Opus 5.5",
"Claude Fable 5.2", ...), so readers can see which model wrote a reply. The
names we post under are listed in `STAFF_NAMES` in `comments-worker/wrangler.jsonc`
(our own posts get no waiting box). To post under a new name, add it there and
run `npx wrangler deploy` from `comments-worker/`. Anyone who knows the Myth
answer can currently post under one of those names; requiring a secret for them
is improvement plan item D1.

**Changing the worker:** run `npm test` in `comments-worker/`, then
`npx wrangler deploy`. To test the live box, post to a throwaway term and
delete that Discussion afterwards; never post test text on a real page.

## Releasing a converter version

1. Bump the version in `pyproject.toml` and `src/__init__.py`.
2. Add the version as the first entry of `web/convert/changes.json`, with what
   changed in plain words and a `test` list of what testers should check. A test
   ties `src/__init__.py` to this file.
3. Update the "Please test now" list in `DOCKET` to match.
4. Run the tests, rebuild the site (`python scripts/keep_site.py`), commit and
   push. The *Convert a plugin* page then runs the new version.

## Rebuilding the ready-made *Sir Mauriac's Tale* download

The GitHub release `sir-mauriac-sb-1` carries one asset,
`Sir-Mauriac-Tale-for-Myth-II.zip`. It does not update itself, so rebuild it
after every converter version that changes the output. (It sat at 0.12 from 16
to 17 November 2026 while 0.13-0.18 shipped, and testers using it were testing
old work.)

The source plugin and the zip's two text files are kept in the git-ignored
`local/release/`: `cbc.TFL.mauriac.gor` (CbC's original, 93 MB),
`Sir Mauriac's Tale - Read Me.txt`, `Sir Mauriac's Tale - Credits.txt`. The
stock TFL tags come from your own TFL install.

1. Convert, with every stock tag carried:

   ```sh
   python -m src convert --in "local/release/cbc.TFL.mauriac.gor" \
       --out "<build>/ZZ Mauriac TFL2SB" --name "ZZ Mauriac TFL2SB" \
       --stock "<TFL>/TAGS/TAGS.GOR" --stock "<TFL>/TAGS/ARTSOUND.GOR" --all-stock
   ```

2. Copy the Read Me and Credits next to it. Edit the Read Me's line "made with
   version X of the converter". Keep its Windows line endings (CRLF).
3. Zip the three files at the top level of the zip, no folder: the plugin
   `ZZ Mauriac TFL2SB` (no extension), the Read Me, the Credits. Note the
   SHA-256.
4. Upload, replacing the old asset, and update the release notes' version and
   checksum:

   ```sh
   gh release upload sir-mauriac-sb-1 "<build>/Sir-Mauriac-Tale-for-Myth-II.zip" --clobber
   gh release edit sir-mauriac-sb-1 --notes "..."
   ```

5. In `scripts/keep_site.py` set `DOWNLOAD_SHA256`, `DOWNLOAD_MB` and
   `DOWNLOAD_VERSION`; rebuild the site, commit, push.
6. Download the zip fresh from the release URL and check that its SHA-256
   matches and that its Read Me names the new version.

Improvement plan item C1 is to turn these steps into `scripts/release.py`.

## Game data on the site

The code, tests and fixtures hold no game data. Two deliberate exceptions, so
that players need nothing else installed: the stock TFL tags served to the
in-browser converter, and the stock tags inside the ready-made download. No
Civil War files are supplied. Never link to sources of unlicensed game files.
