"""Build the progress site for KEEP into docs/ (served by GitHub Pages).

    python scripts/keep_site.py

Each update and each question gets a page of its own with a comment thread
(giscus, stored as GitHub Discussions in the repo's Announcements category), so
KEEP can answer and reply section by section. To add to the site, add an entry
to UPDATES or QUESTIONS below -- newest update first -- and rerun.

A thread is tied to its entry's ``term``, not its URL: keep terms stable once
published, or the comments already on them will no longer show.
"""

import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
REPO = "Edulus/Myth-1-to-2-plugin-converter"
REPO_URL = f"https://github.com/{REPO}"

GISCUS = {
    "data-repo": REPO,
    "data-repo-id": "R_kgDOTmqt9g",
    "data-category": "Announcements",
    "data-category-id": "DIC_kwDOTmqt9s4DJWN2",
    "data-mapping": "specific",
    "data-strict": "1",
    "data-reactions-enabled": "1",
    "data-emit-metadata": "0",
    "data-input-position": "top",
    "data-theme": "preferred_color_scheme",
    "data-lang": "en",
    "data-loading": "lazy",
}

UPDATES = [
    {
        "slug": "2026-10-21",
        "term": "Update 2026-10-21: TFL levels now play in Myth II",
        "date": "21 October 2026",
        "title": "TFL levels now play in Myth II",
        "summary": "Two levels from Sir Mauriac's Tale load, play and finish in Myth II, converted entirely by the tool.",
        "body": """
<p><strong>Two levels from <em>Sir Mauriac's Tale</em> now load, play and finish in Myth II 1.8.5, converted entirely by the tool.</strong></p>
<ul>
<li><strong>Tandem</strong> &mdash; the river level with 77 buildings. Rain falls, units and trees are drawn, the fighting works, and it ends on the normal end-game screen.</li>
<li><strong>In the Name of Glory</strong> &mdash; the snow level, with 146 scripted map actions. Plays from the start to the end-game screen with no errors in the log.</li>
</ul>
<p>Your TFL tags folder is what made this possible. A TFL plugin leans on the stock TFL tags the way a Myth II plugin leans on the base game, and Magma's port doesn't carry them all under their original names &mdash; <em>Tandem</em> alone needed 76 it lacked. Converting your <code>TAGS.GOR</code> and <code>ARTSOUND.GOR</code> into a Myth II tagset solved all of them at once. (Your files stay on our machine; no game data goes into the repository.)</p>

<h2>What converts now</h2>
<table>
<tr><th>Maps</th><td>terrain (upsampled to Myth II's finer grid), markers, map actions, buildings' footprints</td></tr>
<tr><th>Units</th><td>monsters, units, and each monster's own &ldquo;object&rdquo; (its size, health and damage resistances)</td></tr>
<tr><th>Combat</th><td>projectiles, artifacts, mesh effects (explosion ripples)</td></tr>
<tr><th>World</th><td>scenery, weather (rain/snow), lighting, sprite art</td></tr>
<tr><th>Text</th><td>level names, captions, subtitles</td></tr>
</table>

<h2>What we learned along the way</h2>
<ul>
<li><strong>Why units were invisible at first.</strong> In TFL a monster's size, health and damage resistances live on the monster. Myth II moved them into a separate &ldquo;object&rdquo; tag, which TFL shares between every monster. Read by Myth II, TFL's object says &ldquo;size 0&rdquo;, so every unit and tree was there &mdash; you could hear them fight and see their shadows &mdash; but drawn at zero size. Each monster now gets its own object, which is what Project Magma did by hand.</li>
<li><strong>Myth II halved the world unit</strong>, as the Fear manual warns. It shows up in places &mdash; a ground ripple's height doubles &mdash; but not everywhere: unit speeds and ranges did not need doubling.</li>
<li><strong>Your point about models was right.</strong> TFL stores each building's footprint in terrain cells, and Myth II's cells are half the size, so footprints have to be split 2&times;2. That's measured against your tags; converting it is next on the list.</li>
<li><strong>Some stock TFL tags must not replace Myth II's.</strong> The end-of-level statistics screen crashed until we stopped TFL's versions of Myth II's internal text, dialogs and fonts from overriding the originals.</li>
</ul>

<h2>What's still rough</h2>
<ul>
<li><strong>Lighting</strong> converts, but every map currently gets the same standard lighting. A dark cave would come out as bright as a meadow.</li>
<li><strong>Sounds, collection references, projectile groups and a few other types</strong> are still copied across unchanged. Both test levels play fine with them, but they haven't been checked one by one.</li>
<li><strong>Building models</strong> are measured but not converted yet.</li>
<li><strong>Terrain is upsampled by copying</strong>, not smoothing &mdash; see <a href="../q/2.html">Q2</a>.</li>
<li>Only two levels have been tested so far, both single-player.</li>
</ul>

<h2>How to try it yourself</h2>
<p>You need Python 3.12 or later and Myth II 1.8.5. From the repository:</p>
<pre><code># 1. Once: turn your TFL tags folder into a Myth II tagset.
python -m src tagset --in "TFL/tags/TAGS.GOR" --in "TFL/tags/ARTSOUND.GOR" --out "Myth II/plugins/ZZ TFL stock"

# 2. Convert a TFL plugin.
python -m src convert --in "Sir Mauriac's Tale.gor" --out "Myth II/plugins/ZZ Mauriac"</code></pre>
<p>In Myth II: New Game &rarr; pick the converted campaign &rarr; <strong>Tagsets</strong> &rarr; activate <code>ZZ TFL stock</code> &rarr; pick a level. Choosing a campaign clears the tagset, so pick the tagset <em>after</em> the campaign.</p>
""",
    },
]

QUESTIONS = [
    {
        "n": 1,
        "term": "Q1: Which TFL content matters most?",
        "title": "Which TFL content matters most to you?",
        "body": "<p>The original campaign? Specific community plugins? Multiplayer maps or single-player? Whatever you name, we'll test next.</p>",
    },
    {
        "n": 2,
        "term": "Q2: Terrain - faithful or smooth?",
        "title": "Terrain: faithful or smooth?",
        "body": """<p>TFL's terrain is a quarter of Myth II's resolution. We copy each TFL cell into a 2&times;2 block, which invents nothing but looks blockier than Myth II maps. Smoothing it would look closer to a native map, but means inventing detail.</p>
<p>Which would players rather have?</p>""",
    },
    {
        "n": 3,
        "term": "Q3: A coop map with known scoring to test against",
        "title": "Is there a coop map with known scoring we could test against?",
        "body": "<p>You mentioned coop scoring and map actions. We've converted the map-action format, but we don't yet know whether TFL and Myth II scripts <em>mean</em> the same thing in play. A map whose correct behaviour you know would tell us.</p>",
    },
    {
        "n": 4,
        "term": "Q4: TFL gameplay or Myth II gameplay?",
        "title": "TFL gameplay or Myth II gameplay?",
        "body": "<p>Myth II has a built-in &ldquo;TFL Gameplay&rdquo; option that changes the rules to behave more like TFL. We've been testing with normal Myth II rules. Should converted levels be meant for TFL rules?</p>",
    },
    {
        "n": 5,
        "term": "Q5: Would you play-test?",
        "title": "Would you play-test?",
        "body": "<p>A converted level played by someone who knows TFL well would find the subtle problems &mdash; wrong unit sizes, sounds, balance &mdash; that logs can't.</p>",
    },
    {
        "n": 6,
        "term": "Q6: What does done look like?",
        "title": "What does &ldquo;done&rdquo; look like for you?",
        "body": "<p>A tool anyone can run? A finished pack of converted maps to share? Both?</p>",
    },
]

STYLE = """
:root{--bg:#f7f5f0;--fg:#1d1b18;--muted:#6b665d;--line:#ddd7cc;--card:#fffdf8;--accent:#8a3b12;--code:#efeadf}
@media (prefers-color-scheme:dark){:root{--bg:#16140f;--fg:#ece6da;--muted:#a59e90;--line:#38332a;--card:#1f1c16;--accent:#e08a4f;--code:#2a261e}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.6 Georgia,"Iowan Old Style","Palatino Linotype",serif}
.wrap{max-width:46rem;margin:0 auto;padding:2rem 1.25rem 4rem}
a{color:var(--accent)}
header.site{border-bottom:1px solid var(--line);margin-bottom:2rem;padding-bottom:1rem}
header.site a.home{font-variant:small-caps;letter-spacing:.06em;text-decoration:none;color:var(--muted)}
h1{font-size:1.9rem;line-height:1.2;margin:.3rem 0 .5rem}
h2{font-size:1.25rem;margin:2rem 0 .5rem}
.meta{color:var(--muted);font-size:.95rem}
code,pre{font:.85rem/1.5 ui-monospace,Consolas,monospace;background:var(--code);border-radius:4px}
code{padding:.1rem .3rem}
pre{padding:.9rem 1rem;overflow-x:auto}
pre code{background:none;padding:0}
table{border-collapse:collapse;width:100%;margin:.5rem 0}
th,td{text-align:left;vertical-align:top;padding:.45rem .6rem;border-bottom:1px solid var(--line)}
th{white-space:nowrap;color:var(--muted);font-weight:normal}
.list{list-style:none;padding:0;margin:0}
.list li{background:var(--card);border:1px solid var(--line);border-radius:6px;margin:.6rem 0}
.list a{display:block;padding:.8rem 1rem;text-decoration:none;color:var(--fg)}
.list a:hover{border-color:var(--accent)}
.list .tag{color:var(--accent);font-weight:bold;margin-right:.4rem}
.list .sub{display:block;color:var(--muted);font-size:.92rem;margin-top:.15rem}
.how{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:.9rem 1.1rem;font-size:.95rem}
.comments{margin-top:3rem;border-top:1px solid var(--line);padding-top:1.5rem}
.nav{display:flex;justify-content:space-between;gap:1rem;margin-top:2rem;font-size:.95rem}
"""


def page(title, body, depth, term=None):
    up = "../" * depth
    comments = ""
    if term:
        attrs = " ".join(f'{k}="{html.escape(v)}"' for k, v in {**GISCUS, "data-term": term}.items())
        comments = f"""
<section class="comments">
<h2>Comments</h2>
<p class="meta">Sign in with GitHub in the box below to comment or reply.</p>
<script src="https://giscus.app/client.js" {attrs} crossorigin="anonymous" async></script>
</section>"""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} &middot; Myth TFL to Myth II</title>
<link rel="stylesheet" href="{up}style.css">
</head>
<body>
<div class="wrap">
<header class="site"><a class="home" href="{up}index.html">Myth: The Fallen Lords &rarr; Myth II converter &middot; progress for KEEP</a></header>
{body}
{comments}
</div>
</body>
</html>
"""


def build():
    OUT.mkdir(exist_ok=True)
    (OUT / "updates").mkdir(exist_ok=True)
    (OUT / "q").mkdir(exist_ok=True)
    (OUT / ".nojekyll").write_text("")
    (OUT / "style.css").write_text(STYLE.strip() + "\n", encoding="utf-8")

    updates = "\n".join(
        f'<li><a href="updates/{u["slug"]}.html"><span class="tag">{u["date"]}</span>{u["title"]}'
        f'<span class="sub">{html.escape(u["summary"])}</span></a></li>'
        for u in UPDATES
    )
    questions = "\n".join(
        f'<li><a href="q/{q["n"]}.html"><span class="tag">Q{q["n"]}</span>{q["title"]}</a></li>'
        for q in QUESTIONS
    )
    index = f"""<h1>Progress, and questions for KEEP</h1>
<p>The converter you proposed, turning <em>Myth: The Fallen Lords</em> plugins into <em>Myth II</em> plugins. Each update and each question below has its own page with a comment thread, so you can answer or reply to any of them separately.</p>
<div class="how"><strong>To comment:</strong> open a page, scroll to <em>Comments</em>, and sign in with a free GitHub account. Replies are threaded, and everything is kept in the repository's <a href="{REPO_URL}/discussions">Discussions</a>.</div>
<h2>Updates</h2>
<ul class="list">
{updates}
</ul>
<h2>Questions for you</h2>
<ul class="list">
{questions}
</ul>
<p class="meta">Source code and technical notes: <a href="{REPO_URL}">{REPO}</a></p>"""
    (OUT / "index.html").write_text(page("Progress for KEEP", index, 0), encoding="utf-8")

    for u in UPDATES:
        body = f"""<p class="meta">Update &middot; {u["date"]}</p>
<h1>{u["title"]}</h1>
{u["body"]}
<div class="nav"><a href="../index.html">&larr; All updates and questions</a><a href="../q/1.html">Questions for you &rarr;</a></div>"""
        (OUT / "updates" / f'{u["slug"]}.html').write_text(page(u["title"], body, 1, u["term"]), encoding="utf-8")

    for i, q in enumerate(QUESTIONS):
        prev = f'<a href="{QUESTIONS[i - 1]["n"]}.html">&larr; Q{QUESTIONS[i - 1]["n"]}</a>' if i else '<a href="../index.html">&larr; All updates and questions</a>'
        nxt = f'<a href="{QUESTIONS[i + 1]["n"]}.html">Q{QUESTIONS[i + 1]["n"]} &rarr;</a>' if i + 1 < len(QUESTIONS) else '<a href="../index.html">All updates and questions &rarr;</a>'
        body = f"""<p class="meta">Question {q["n"]} of {len(QUESTIONS)}</p>
<h1>Q{q["n"]}. {q["title"]}</h1>
{q["body"]}
<div class="nav">{prev}{nxt}</div>"""
        (OUT / "q" / f'{q["n"]}.html').write_text(page(f'Q{q["n"]}', body, 1, q["term"]), encoding="utf-8")

    print(f"built {len(UPDATES)} update(s) and {len(QUESTIONS)} question(s) into {OUT}")


if __name__ == "__main__":
    build()
