"""Build the public project site into docs/ (served by GitHub Pages).

    python scripts/keep_site.py

Each update and each question gets a page of its own with a comment box that
needs no account -- a visitor types a name, a message and a one-word Myth answer.
The box talks to comments-worker/ (a Cloudflare Worker), which stores each
page's thread as a GitHub Discussion in the repo's Announcements category, so
Visitors can answer and reply section by section.

The site's words live in site/content/ (TOML files, read below); this script is
the generator. To add an update or a question, add a file there and rerun:
site/content/updates/<date>.toml, site/content/questions/<n>.toml. The home
page's work list is site/content/docket.toml. See documentation/site-and-releases.md.

A thread is tied to its entry's ``term``, not its URL: keep terms stable once
published, or the comments already on them will no longer show.
"""

import hashlib
import html
import io
import json
import pathlib
import tomllib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
REPO = "Edulus/Myth-1-to-2-plugin-converter"
REPO_URL = f"https://github.com/{REPO}"

# Public project identity. Keep published discussion terms stable.
SITE_NAME = "Myth Plugin Converter"
SITE_TAGLINE = "The Fallen Lords &rarr; Soulblighter"

# The deployed comments-worker (see comments-worker/).
COMMENTS_API = "https://keep-comments.edyersh.workers.dev"

# A converted plugin offered as a GitHub Release asset (the zip is too big for Pages).
DOWNLOAD_ZIP = "Sir-Mauriac-Tale-for-Myth-II.zip"
DOWNLOAD_URL = f"{REPO_URL}/releases/download/sir-mauriac-sb-1/{DOWNLOAD_ZIP}"
DOWNLOAD_SHA256 = "ec9ea64469f70fe38aec620bf9534df36fe273c45adad392f941d1a8b37f4171"
DOWNLOAD_MB = 222
DOWNLOAD_VERSION = "0.19"

# ---------------------------------------------------------------------------
# Content: site/content/*.toml. Read as UTF-8 with Unix line endings, so a CRLF
# checkout builds the same site as a LF one. A missing or malformed file stops
# the build with a message naming the file and the problem.

CONTENT = ROOT / "site" / "content"


class ContentError(SystemExit):
    """A content file is missing or wrong; the message names it."""


def _content(rel):
    path = CONTENT / rel
    try:
        text = path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise ContentError(f"site content {rel}: cannot read: {err}") from None
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        raise ContentError(f"site content {rel}: not valid TOML: {err}") from None


def _check(rel, data, shape):
    """shape maps each required key to its type.
    Other keys are left alone."""
    for key, kind in shape.items():
        if key not in data:
            raise ContentError(f"site content {rel}: missing key '{key}'")
        if not isinstance(data[key], kind) or isinstance(data[key], bool) and kind is int:
            raise ContentError(f"site content {rel}: '{key}' must be {kind.__name__}")
    return data


def _files(folder):
    found = sorted((CONTENT / folder).glob("*.toml"))
    if not found:
        raise ContentError(f"site content {folder}/: no .toml files found in {CONTENT / folder}")
    return [f"{folder}/{f.name}" for f in found]


def _load_updates():
    """Newest first (sorted by slug, an ISO date)."""
    out = []
    for rel in _files("updates"):
        u = _check(rel, _content(rel), dict.fromkeys(("slug", "term", "date", "title", "summary", "body"), str))
        if rel != f"updates/{u['slug']}.toml":
            raise ContentError(f"site content {rel}: file name must match slug '{u['slug']}'")
        out.append(u)
    return sorted(out, key=lambda u: u["slug"], reverse=True)


def _load_questions():
    """In question order (the file name is the number); each carries its plain-words
    gist, an optional `closed` note once resolved (it stays readable), and an
    optional `unanswered = true` (nobody has replied as of the gists' date)."""
    out = []
    for rel in _files("questions"):
        q = _check(rel, _content(rel), {"n": int, "term": str, "title": str, "gist": str, "body": str})
        if "closed" in q and not isinstance(q["closed"], str):
            raise ContentError(f"site content {rel}: 'closed' must be str")
        if "unanswered" in q and not isinstance(q["unanswered"], bool):
            raise ContentError(f"site content {rel}: 'unanswered' must be true or false")
        if rel != f"questions/{q['n']}.toml":
            raise ContentError(f"site content {rel}: file name must match n = {q['n']}")
        out.append(q)
    return sorted(out, key=lambda q: q["n"])


_SITE = _check("site.toml", _content("site.toml"), {"gists_updated": str})
GISTS_UPDATED = _SITE["gists_updated"]
_KEEP = _check("keep.toml", _content("keep.toml"), {"term": str, "question": str, "hash": str, "body": str})


def _load_poem(name):
    """(title, stanzas); a stanza is (image or None, alt text, [lines])."""
    rel = f"poems/{name}.toml"
    data = _check(rel, _content(rel), {"title": str, "stanza": list})
    stanzas = []
    for s in data["stanza"]:
        if not (isinstance(s, dict) and isinstance(s.get("lines"), list) and s["lines"]
                and all(isinstance(line, str) for line in s["lines"])):
            raise ContentError(f"site content {rel}: each [[stanza]] needs a 'lines' list of strings")
        if ("image" in s) != ("alt" in s):
            raise ContentError(f"site content {rel}: a stanza has both 'image' and 'alt', or neither")
        stanzas.append((s.get("image"), s.get("alt", ""), s["lines"]))
    return data["title"], stanzas


def _load_units():
    rel = "units.toml"
    data = _check(rel, _content(rel), {"title": str, "rows": list})
    for row in data["rows"]:
        if not (isinstance(row, list) and len(row) == 4 and isinstance(row[0], str)
                and isinstance(row[1], str) and isinstance(row[2], int) and isinstance(row[3], int)):
            raise ContentError(f"site content {rel}: each row is [TFL unit, Magma unit, radius, hack flags], got {row!r}")
    return data["title"], [tuple(row) for row in data["rows"]]


def _load_docket():
    rel = "docket.toml"
    data = _check(rel, _content(rel), {"updated": str, "group": list})
    docket = {}
    for g in data["group"]:
        if not (isinstance(g, dict) and isinstance(g.get("title"), str) and isinstance(g.get("items"), list)
                and all(isinstance(i, str) for i in g["items"])):
            raise ContentError(f"site content {rel}: each [[group]] needs a 'title' and an 'items' list of strings")
        docket[g["title"]] = g["items"]
    return data["updated"], docket


UPDATES = _load_updates()
QUESTIONS = _load_questions()
QUESTION_GISTS = {q["n"]: q["gist"] for q in QUESTIONS}



STYLE = """
:root{--bg:#f3eee3;--panel:#fbf8f1;--panel2:#fffdf8;--fg:#1f1b15;--muted:#6c6457;--line:#d6ccb9;--blood:#9b2a17;--blood-hi:#b5351f;--code:#e9e1d1;--tint:rgba(155,42,23,.08);color-scheme:light}
:root[data-theme=dark]{--bg:#0d0c0b;--panel:#171513;--panel2:#1f1c19;--fg:#e9e2d6;--muted:#a39b8e;--line:#3a352f;--blood:#a8321f;--blood-hi:#d0452c;--code:#24211d;--tint:rgba(168,50,31,.18);color-scheme:dark}
*{box-sizing:border-box}
html{background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--fg);font:18px/1.65 "IM Fell English",Georgia,"Times New Roman",serif}
img{max-width:100%;height:auto;display:block}
a{color:var(--blood-hi)}
h1,h2,.brand,.tag,.btn,.step b{font-family:Cinzel,"Trajan Pro",Georgia,serif;letter-spacing:.04em}
h1{font-size:clamp(1.6rem,4.5vw,2.4rem);line-height:1.15;margin:.2rem 0 .6rem;font-weight:700}
h2{font-size:1.2rem;margin:2.2rem 0 .7rem;color:var(--fg);border-bottom:1px solid var(--line);padding-bottom:.3rem}
.hero{position:relative;background:#0b0a09;border-bottom:1px solid #2a2622}
.panes{display:grid;grid-template-columns:1fr auto 1fr;height:clamp(9rem,28vw,17rem)}
.hero.compact .panes{height:clamp(5.5rem,14vw,8.5rem)}
.pane{position:relative;display:flex;align-items:center;justify-content:center;overflow:hidden;background:#000 center/cover no-repeat}
.pane.one{background-image:url(img/hero-i.jpg)}
.pane.two{background-image:url(img/hero-ii.jpg)}
.pane::after{content:"";position:absolute;inset:0;background:radial-gradient(ellipse at center,rgba(0,0,0,.12) 0%,rgba(0,0,0,.5) 100%)}
.num{position:relative;z-index:1;font-family:Cinzel,Georgia,serif;font-weight:700;line-height:1;font-size:clamp(3.5rem,13vw,8.5rem);color:#f7f2e8;text-shadow:0 0 22px rgba(0,0,0,.95),0 4px 0 rgba(0,0,0,.55)}
.hero.compact .num{font-size:clamp(2.2rem,7vw,3.8rem)}
.cap{position:absolute;z-index:1;left:0;right:0;bottom:.7rem;text-align:center;font-family:Cinzel,Georgia,serif;font-size:clamp(.62rem,1.6vw,.85rem);letter-spacing:.22em;text-transform:uppercase;color:#ece5d8;text-shadow:0 1px 8px #000}
.hero.compact .cap{display:none}
.arrow{display:flex;align-items:center;padding:0 clamp(.5rem,2.2vw,1.4rem);background:#0b0a09;color:#d0452c;font-family:Cinzel,Georgia,serif;font-size:clamp(1.6rem,5vw,3rem)}
.band .inner{max-width:50rem;margin:0 auto;padding:1rem 1.25rem 1.3rem}
.brand{display:inline-block;color:#c9c0b1;text-decoration:none;font-size:.82rem;text-transform:uppercase;letter-spacing:.18em}
.hero h1{color:#f3ede2;text-shadow:0 2px 12px #000}
.subtitle{margin:-.2rem 0 .4rem;color:#e0d7c8;font-family:Cinzel,Georgia,serif;font-size:clamp(1rem,2.6vw,1.3rem);letter-spacing:.06em;text-shadow:0 2px 10px #000}
.intro{font-size:1.1rem;margin:.6rem 0 0}
.hero .meta{color:#c9c0b1}
.wrap{max-width:50rem;margin:0 auto;padding:1rem 1.25rem 4rem}
.meta{color:var(--muted);font-size:.95rem}
.lede{display:grid;grid-template-columns:1fr 11rem;gap:1.5rem;align-items:start}
.lede img{border:1px solid var(--line)}
@media (max-width:640px){.lede{grid-template-columns:1fr 7rem;gap:1rem}}
.steps{list-style:none;padding:0;margin:1rem 0;display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));gap:.6rem}
.step{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:.8rem .9rem;font-size:.95rem}
.step b{display:block;color:var(--blood-hi);font-size:.8rem;text-transform:uppercase;letter-spacing:.14em;margin-bottom:.2rem}
.cards{list-style:none;padding:0;margin:0;display:grid;gap:.8rem}
.card a{display:flex;align-items:center;gap:1rem;padding:1rem 1.1rem;background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--blood);border-radius:6px;color:var(--fg);text-decoration:none;transition:transform .12s ease,border-color .12s ease,background .12s ease}
.card a:hover,.card a:focus-visible{transform:translateY(-2px);background:var(--panel2);border-color:var(--blood-hi);outline:none}
.card .body{flex:1;min-width:0}
.card .title{display:block;font-size:1.08rem}
.card .sub{display:block;color:var(--muted);font-size:.92rem;margin-top:.15rem}
.tag{color:var(--blood-hi);font-weight:700;margin-right:.45rem}
hr.news-rule{border:0;border-top:1px solid var(--rule,currentColor);opacity:.5;margin:1.6rem 0}
.btn{display:inline-block;flex:none;padding:.45rem .8rem;border:1px solid var(--blood);border-radius:4px;color:var(--fg);background:var(--tint);font-size:.75rem;text-transform:uppercase;letter-spacing:.12em;text-decoration:none;white-space:nowrap}
.card a:hover .btn,.btn:hover{background:var(--blood);border-color:var(--blood-hi)}
@media (max-width:520px){.card a{flex-direction:column;align-items:flex-start}}
code,pre{font:.82rem/1.5 ui-monospace,Consolas,monospace;background:var(--code);border-radius:4px}
code{padding:.1rem .3rem}
pre{padding:.9rem 1rem;overflow-x:auto;border:1px solid var(--line)}
pre code{background:none;padding:0}
table{border-collapse:collapse;width:100%;margin:.5rem 0}
.scroll{overflow-x:auto}
th,td{text-align:left;vertical-align:top;padding:.5rem .6rem;border-bottom:1px solid var(--line)}
th{white-space:nowrap;color:var(--muted);font-weight:normal}
figure{margin:.3rem 0 1rem 1.5rem;float:right;width:min(45%,22rem)}
@media (max-width:640px){figure{float:none;width:auto;margin:1.5rem 0}}
h2{clear:both}
figure img{border:1px solid var(--line)}
figcaption{color:var(--muted);font-size:.9rem;margin-top:.4rem;font-style:italic}
.answer-top{margin:1rem 0 0}
.reply{margin-top:3rem;background:var(--panel);border:1px solid var(--blood);border-radius:8px;padding:1.2rem 1.2rem .6rem}
.reply h2{margin-top:0;border:none;color:var(--blood-hi)}
.reply ol{margin:.2rem 0 1rem 1.2rem;padding:0}
.reply li{margin:.15rem 0}
.nav{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap;margin-top:2rem;font-size:.95rem}
.theme{position:absolute;top:.8rem;right:.9rem;z-index:2;font:1rem/1 Georgia,serif;color:#f3ede2;background:rgba(0,0,0,.45);border:1px solid rgba(255,255,255,.35);border-radius:999px;padding:.4rem .75rem;cursor:pointer}
.theme:hover,.theme:focus-visible{background:rgba(0,0,0,.7);outline:none}
.say label{display:block;margin:.7rem 0;font-size:.95rem;color:var(--muted)}
.say .hint{font-size:.85rem;font-style:italic}
.say input,.say textarea{display:block;width:100%;margin-top:.25rem;padding:.6rem .7rem;font:inherit;font-size:1rem;color:var(--fg);background:var(--panel2);border:1px solid var(--line);border-radius:5px}
.say input:focus,.say textarea:focus{outline:2px solid var(--blood-hi);outline-offset:1px;border-color:var(--blood)}
.say .trap{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}
.send{font-size:.85rem;padding:.6rem 1.1rem;cursor:pointer}
.send:disabled{opacity:.6;cursor:wait}
.status{margin-left:.6rem;color:var(--muted);font-size:.95rem}
.replying{background:var(--tint);border-left:3px solid var(--blood);padding:.4rem .7rem;margin:.4rem 0}
.link{background:none;border:none;padding:0;font:inherit;font-size:.92rem;color:var(--blood-hi);cursor:pointer;text-decoration:underline}
.convo{margin-top:2rem}
.comment{border-top:1px solid var(--line);padding:.8rem 0}
.comment .who{margin:0;color:var(--muted);font-size:.9rem}
.comment .who strong{color:var(--fg)}
.comment .state{margin-left:.6rem;font-size:.85rem;padding:.05rem .45rem;border-radius:4px;border:1px solid var(--line)}
.comment .state.done{color:var(--fg);background:var(--tint)}
.comment .state.open{color:var(--muted)}
.comment .votes{margin:.1rem 0 .4rem}
.comment .vote{font:inherit;font-size:.85rem;background:none;border:1px solid var(--line);border-radius:4px;padding:.1rem .5rem;margin-right:.4rem;cursor:pointer;color:var(--fg)}
.comment .vote.on{background:var(--tint);border-color:var(--blood)}
.comment .text{margin:.3rem 0 .4rem;white-space:pre-wrap}
.comment .text a{color:var(--blood-hi);overflow-wrap:anywhere}
.comment .pic{display:block;margin:.2rem 0 .6rem}
.comment .pic img{display:block;max-width:100%;height:auto;border:1px solid var(--line);border-radius:5px}
.say .pick{margin:-.4rem 0 .7rem;font-size:.9rem}
.comment.sub{margin-left:1.4rem;padding:.6rem 0 .2rem;border-top:1px dashed var(--line)}
.drop{display:block;margin:1.2rem 0;padding:2rem 1rem;text-align:center;background:var(--panel);border:2px dashed var(--blood);border-radius:8px;cursor:pointer}
.drop:hover,.drop.over,.drop:focus-within{background:var(--tint);border-color:var(--blood-hi)}
.drop input{position:absolute;opacity:0;width:1px;height:1px}
.drop-big{display:block;font-size:1.15rem;margin-bottom:.3rem}
.share{display:block;margin:-.4rem 0 1rem;font-size:.95rem}
.share input{margin-right:.4rem}
#log table{width:100%;border-collapse:collapse;font-size:.92rem}
#log th,#log td{text-align:left;padding:.3rem .5rem;border-bottom:1px solid var(--line)}.btn.save{text-transform:none;font-size:.9rem;letter-spacing:.04em}
#progress progress{width:100%;height:.8rem;accent-color:var(--blood)}
.problem{background:var(--tint);border-left:4px solid var(--blood);padding:.6rem .9rem;margin:1rem 0}
.gist{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:.8rem 1rem;margin:1rem 0 1.4rem}
.cards.closed .card{opacity:.75}
details{margin:1rem 0}
details.fold{background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:0 .9rem;margin:.8rem 0}
details.fold>summary{padding:.55rem 0;color:var(--fg);font-family:Cinzel,"Trajan Pro",Georgia,serif;letter-spacing:.04em;font-size:.95rem}
details.fold>summary:hover{color:var(--blood-hi)}
details.fold>summary:focus-visible{outline:2px solid var(--blood-hi);outline-offset:2px;border-radius:3px}
details.fold[open]>summary{border-bottom:1px solid var(--line);margin-bottom:.6rem}
.quiet{display:inline-block;margin-left:.5rem;padding:0 .45rem;border:1px solid var(--line);border-radius:4px;font-size:.82rem;color:var(--muted)}
.release{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--blood);border-radius:8px;padding:.9rem 1.2rem;margin:0 0 1.5rem}
.release h2{margin:0 0 .4rem}
.release h3{margin:.9rem 0 .3rem}
.release ul{margin:.2rem 0}
summary{cursor:pointer;color:var(--muted)}
details pre{white-space:pre-wrap;max-height:24rem;overflow:auto}
footer{max-width:50rem;margin:0 auto;padding:1.5rem 1.25rem 3rem;color:var(--muted);font-size:.82rem;border-top:1px solid var(--line)}
.honour{margin:1.6rem 0;padding:1rem 1.25rem;border:1px solid var(--line);border-left:4px solid var(--blood);border-radius:6px;background:var(--panel)}
.honour h2{margin-top:0}
.stanza-one{margin:1rem 0 .2rem;padding:0 0 0 1rem;border-left:2px solid var(--line);font-style:italic}
.stanza-one p{margin:0;line-height:1.8}
.stanza-one footer{margin-top:.5rem;font-size:.9rem;font-style:normal;color:var(--muted);border:0;padding:0;text-align:left;max-width:none}
.pickers{display:grid;gap:.9rem;margin:1rem 0}
.pick{display:block;padding:.8rem 1rem;background:var(--panel);border:1px dashed var(--blood);border-radius:6px}
.pick span{display:block;margin-bottom:.4rem}
.pick em{display:block;margin-top:.3rem;font-size:.9rem;color:var(--muted)}
.bulkbox{margin:1rem 0;padding:.8rem 1rem;background:var(--panel);border:1px solid var(--line);border-radius:6px}
.bulkbox h3{margin:0 0 .5rem}
.bulk{display:flex;flex-wrap:wrap;gap:.6rem 1rem;align-items:center}
.onlysides{display:block;margin:.8rem 0;font-size:.95rem}
.tablewrap{max-height:60vh;overflow:auto;border:1px solid var(--line);border-radius:6px}
.swaptable{margin:0}
.swaptable thead th{position:sticky;top:0;background:var(--panel);z-index:1}
.swaptable td select{max-width:100%;min-width:14rem}
.swaptable tr.set td{background:var(--tint)}
#swapper select,#swapper input[type=text]{font:inherit;font-size:.95rem;padding:.3rem .4rem;color:var(--fg);background:var(--panel2);border:1px solid var(--line);border-radius:4px}
footer{text-align:center}
body.white{background:#fff;color:#1a1a1a}
body.white main,body.white footer,body.white .meta,body.white footer .made,body.white .sitemap a,body.white .sitemap .label{color:#1a1a1a}
body.white a{color:#1a1a1a}
.poem{margin:1.5rem 0}
.poem .stanza{display:flow-root;margin:0 0 1.6rem}
.poem .stanza p{font-size:1.15rem;line-height:1.7;margin:.4rem 0}
.poem img{width:min(45%,300px);height:auto;border:0;mix-blend-mode:multiply}
.poem img.right{float:right;margin:0 0 .8rem 1.4rem}
.poem img.left{float:left;margin:0 1.4rem .8rem 0}
.poem .sign{font-style:italic;text-align:right;clear:both}
@media (max-width:560px){.poem img.right,.poem img.left{float:none;width:100%;margin:0 0 .6rem}}
.sitemap ul{list-style:none;margin:0 0 .5rem;padding:0;display:flex;flex-wrap:wrap;justify-content:center;gap:.3rem 1.1rem;font-size:.9rem}
.sitemap .label{color:var(--muted)}
.sitemap a,footer .made a{color:var(--fg)}
footer .made{margin-top:1.1rem;font-size:.9rem;color:var(--fg)}
"""


THEME_JS = """
(function(){
  var root=document.documentElement, btn=document.querySelector(".theme");
  function paint(){btn.textContent=root.dataset.theme==="dark"?"☀ Light":"☾ Dark";}
  btn.addEventListener("click",function(){
    if(root.dataset.theme==="dark"){delete root.dataset.theme;}else{root.dataset.theme="dark";}
    try{localStorage.setItem("theme",root.dataset.theme||"light")}catch(e){}
    paint();
  });
  paint();
})();
"""

GIVE_ANSWER = """
<section class="reply" id="{id}" data-term="{term}" data-api="{api}">
<h2>&#9998; {label}</h2>
<p class="meta">No sign-up, no account &mdash; just type and press <strong>Send</strong>.</p>
<form class="say" novalidate>
<p class="replying" hidden></p>
<label>Your name <span class="hint">(any name you like; we never ask for an email or password)</span><input name="name" autocomplete="nickname" maxlength="40" required></label>
<label>Your message<textarea name="message" rows="6" maxlength="4000" required placeholder="Type here..."></textarea></label>
<label>Add a picture (screenshot), if you like<input name="picture" type="file" accept="image/png,image/jpeg,image/gif,image/webp"></label>
<p class="meta pick">PNG, JPEG, GIF or WebP, up to 8 MB. <button class="link unpick" type="button" hidden>Remove the picture</button></p>
<label><span class="q">A quick Myth question, so we know you're not a robot:</span><input name="answer" autocomplete="off" required></label>
<label class="trap" aria-hidden="true">Leave this empty<input name="website" tabindex="-1" autocomplete="off"></label>
<p><button class="btn send" type="submit">Send &rarr;</button> <span class="status" role="status"></span></p>
</form>
<h2 class="convo">The conversation so far</h2>
<div class="thread"><p class="meta">Loading&hellip;</p></div>
</section>"""

COMMENTS_JS = """
(function(){
  // Every comment box on the page (a page may carry more than one thread).
  var boxes=document.querySelectorAll("section.reply[data-term]");
  for(var n=0;n<boxes.length;n++) start(boxes[n]);
  function start(box){
  var api=box.dataset.api, term=box.dataset.term, form=box.querySelector("form");
  var list=box.querySelector(".thread"), status=form.querySelector(".status");
  var replying=form.querySelector(".replying"), replyTo=null, send=form.querySelector(".send");
  try{var saved=localStorage.getItem("name"); if(saved) form.name.value=saved;}catch(e){}
  var IMAGES=api+"/images/", LIMIT=8*1024*1024, KINDS=["image/png","image/jpeg","image/gif","image/webp"];
  var pick=form.picture, unpick=form.querySelector(".unpick");
  function unpicked(){pick.value=""; unpick.hidden=true;}
  pick.addEventListener("change",function(){unpick.hidden=!(pick.files&&pick.files.length); status.textContent="";});
  unpick.addEventListener("click",unpicked);
  function el(tag,cls,text){var e=document.createElement(tag); if(cls)e.className=cls; if(text!=null)e.textContent=text; return e;}
  // Web addresses in a message become links; everything else stays plain text.
  function linked(cls,text){var p=el("p",cls), re=/https?:[/][/][^\\s<>"]+/g, at=0, m; text=String(text||"");
    while((m=re.exec(text))){var u=m[0].replace(/[.,;:!?)'"\\]]+$/,""), href=null;
      try{var x=new URL(u); if(x.protocol==="http:"||x.protocol==="https:") href=x.href;}catch(e){}
      if(!href) continue;
      p.append(text.slice(at,m.index)); var a=el("a",null,u); a.href=href; a.rel="nofollow ugc noopener"; a.target="_blank"; p.append(a);
      at=m.index+u.length;}
    p.append(text.slice(at)); return p;}
  // Only pictures the comment box itself stored are shown.
  function picture(c){if(typeof c.image!=="string"||c.image.indexOf(IMAGES)!==0
      ||!/^[A-Za-z0-9_-]{22}[.](png|jpg|gif|webp)$/.test(c.image.slice(IMAGES.length))) return null;
    var a=el("a","pic"); a.href=c.image; a.target="_blank"; a.rel="noopener";
    var i=el("img"); i.src=c.image; i.alt="Picture from "+c.name; i.setAttribute("loading","lazy"); a.append(i); return a;}
  function asBase64(blob){return new Promise(function(ok,no){var r=new FileReader();
    r.onload=function(){var s=String(r.result); ok(s.slice(s.indexOf(",")+1));};
    r.onerror=function(){no(r.error);}; r.readAsDataURL(blob);});}
  // A picture too big (or of another kind) is redrawn as a JPEG, smaller on
  // each try until it fits; null if the browser can't read it.
  function asJpeg(file){return new Promise(function(ok){var img=new Image(), u=URL.createObjectURL(file);
    img.onerror=function(){URL.revokeObjectURL(u); ok(null);};
    img.onload=function(){URL.revokeObjectURL(u);
      var w=img.naturalWidth, h=img.naturalHeight, s=Math.min(1,4096/Math.max(w,h,1));
      (function draw(){try{var c=document.createElement("canvas"), g=c.getContext("2d");
        c.width=Math.max(1,Math.round(w*s)); c.height=Math.max(1,Math.round(h*s));
        g.fillStyle="#fff"; g.fillRect(0,0,c.width,c.height); g.drawImage(img,0,0,c.width,c.height);
        c.toBlob(function(b){if(b&&b.size<=LIMIT) ok(b); else if(s>0.1){s*=0.75; draw();} else ok(null);},"image/jpeg",0.85);
      }catch(e){ok(null);}})();};
    img.src=u;});}
  // The chosen picture, ready to send, or null when there is none.
  function chosen(){var f=pick.files&&pick.files[0]; if(!f) return Promise.resolve(null);
    var fits=KINDS.indexOf(f.type)>=0&&f.size<=LIMIT;
    return (fits?Promise.resolve(f):asJpeg(f)).then(function(b){
      if(!b) throw {say:"That picture is too big or can't be read — please choose a PNG, JPEG, GIF or WebP under 8 MB."};
      return asBase64(b).then(function(data){return {name:f.name,type:b.type,data:data};});});}
  function when(at){try{return new Date(at).toLocaleDateString(undefined,{day:"numeric",month:"short",year:"numeric"});}catch(e){return "";}}
  function reply(c){replyTo=c.id; replying.hidden=false; replying.textContent="";
    replying.append("Replying to "+c.name+" ");
    var x=el("button","link","(cancel)"); x.type="button";
    x.onclick=function(){replyTo=null; replying.hidden=true;}; replying.append(x);
    form.message.focus(); form.scrollIntoView({behavior:"smooth",block:"start"});}
  function votes(c){var row=el("p","votes"), mine=null, buttons={};
    try{mine=localStorage.getItem("vote:"+c.id);}catch(e){}
    function paint(){["up","down"].forEach(function(k){
      buttons[k].textContent=(k==="up"?"👍 ":"👎 ")+c.votes[k];
      buttons[k].className="vote"+(mine===k?" on":"");
      buttons[k].setAttribute("aria-pressed",mine===k?"true":"false");});}
    ["up","down"].forEach(function(k){var b=el("button"); b.type="button";
      b.title=k==="up"?"This answer helped":"This answer didn't help";
      b.onclick=function(){var next=mine===k?null:k;
        fetch(api+"/vote",{method:"POST",headers:{"Content-Type":"application/json"},
          body:JSON.stringify({term:term,id:c.id,vote:next,previous:mine})})
        .then(function(r){return r.json();})
        .then(function(d){if(!d.votes)return; mine=next; c.votes=d.votes;
          try{if(next)localStorage.setItem("vote:"+c.id,next);else localStorage.removeItem("vote:"+c.id);}catch(e){}
          paint();}).catch(function(){});};
      buttons[k]=b; row.append(b);});
    paint(); return row;}
  function item(c,top){var a=el("article","comment"+(top?"":" sub"));
    var h=el("p","who"); h.append(el("strong",null,c.name)); h.append(" \u00b7 "+when(c.at));
    if(c.status==="addressed") h.append(el("span","state done","\u2611 Addressed"));
    else if(c.status==="waiting") h.append(el("span","state open","\u2610 Waiting for a reply"));
    a.append(h);
    a.append(linked("text",c.text));
    var pic=picture(c); if(pic) a.append(pic);
    if(c.votes) a.append(votes(c));
    if(top){var b=el("button","link","Reply to "+c.name); b.type="button"; b.onclick=function(){reply(c);}; a.append(b);}
    return a;}
  function render(cs){list.textContent="";
    if(!cs.length){list.append(el("p","meta","Nothing here yet \u2014 yours will be the first."));return;}
    cs.forEach(function(c){var a=item(c,true); (c.replies||[]).forEach(function(r){a.append(item(r,false));}); list.append(a);});}
  fetch(api+"/config").then(function(r){return r.json();}).then(function(d){
    if(d.question) form.querySelector(".q").textContent=d.question;}).catch(function(){});
  fetch(api+"/comments?term="+encodeURIComponent(term)).then(function(r){return r.json();})
    .then(function(d){render(d.comments||[]);})
    .catch(function(){list.textContent=""; list.append(el("p","meta","The conversation couldn't be loaded just now \u2014 try reloading the page."));});
  form.addEventListener("submit",function(ev){ev.preventDefault();
    status.textContent="Sending\u2026"; send.disabled=true;
    try{localStorage.setItem("name",form.name.value.trim());}catch(e){}
    chosen().then(function(image){
      return fetch(api+"/comments",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({term:term,page:location.href.split("#")[0],name:form.name.value,message:form.message.value,
          answer:form.answer.value,website:form.website.value,replyTo:replyTo,image:image})});})
    .then(function(r){return r.json().then(function(d){return {ok:r.ok,d:d};});})
    .then(function(x){if(!x.ok){status.textContent=x.d.error||"That didn't go through \u2014 please try again.";return;}
      render(x.d.comments||[]); form.message.value=""; unpicked(); replyTo=null; replying.hidden=true;
      status.textContent="Sent \u2014 thank you!";})
    .catch(function(e){status.textContent=(e&&e.say)||"That didn't go through \u2014 please try again.";})
    .then(function(){send.disabled=false;});
  });
  }
})();
"""

# A riddle in front of a page. Only the SHA-256 of the answer (lowercased,
# letters only) is in the page, so it is not readable from the source -- a
# courtesy lock, not security: the thread behind it is a public Discussion.
LOCK_HTML = """<section class="wrap lock" id="lock">
<form class="say" novalidate>
<label><span>{question}</span><input name="riddle" autocomplete="off" required></label>
<p><button class="btn" type="submit">Enter &rarr;</button> <span class="status" role="status"></span></p>
</form>
</section>"""

LOCK_JS = """
(function(){
  var gate=document.getElementById("lock"), main=document.querySelector("main"), form=gate.querySelector("form");
  function open(){gate.hidden=true; main.hidden=false;}
  try{if(localStorage.getItem("unlocked:"+location.pathname)==="{hash}"){open();return;}}catch(e){}
  form.addEventListener("submit",function(ev){ev.preventDefault();
    var said=form.riddle.value.toLowerCase().replace(/[^a-z]/g,"");
    crypto.subtle.digest("SHA-256",new TextEncoder().encode(said)).then(function(d){
      var hex=Array.from(new Uint8Array(d)).map(function(b){return b.toString(16).padStart(2,"0");}).join("");
      if(hex!=="{hash}"){form.querySelector(".status").textContent="That isn't it.";return;}
      try{localStorage.setItem("unlocked:"+location.pathname,hex);}catch(e){}
      open();});
  });
})();
"""

# Keep's own page: an open-ended conversation with Claude about the project.
KEEP_PAGE = {key: _KEEP[key] for key in ("term", "question", "hash")}


POEM_TITLE, POEM = _load_poem("keep")


def stanzas_html(poem):
    """Each stanza as a block; a stanza with a picture has it beside the
    verse, alternating right and left between pictured stanzas."""
    out, pictured = [], 0
    for image, alt, lines in poem:
        verse = "<br>".join(html.escape(line) for line in lines)
        picture = ""
        if image:
            side = "right" if pictured % 2 == 0 else "left"
            pictured += 1
            picture = f'<img class="{side}" src="../img/poem/{image}" alt="{html.escape(alt)}" loading="lazy">'
        out.append(f'<div class="stanza">{picture}<p>{verse}</p></div>')
    return "".join(out)


WALTER_TITLE, WALTER_POEM = _load_poem("walter")
FABLE_TITLE, FABLE_POEM = _load_poem("fable")


def _poem_section(anchor, title, poem, sign, notes=""):
    return (
        f'<section id="{anchor}"><h2>{html.escape(title)}</h2>'
        '<div class="poem">' + stanzas_html(poem) + f'<p class="sign">{sign}</p></div>{notes}</section>'
    )


POEM_ANCHORS = {"keep": POEM_TITLE, "walter": WALTER_TITLE, "fable": FABLE_TITLE}


def poems_html():
    """All three poems on one page, each a titled section with an anchor
    (keep/poems.html#keep, #walter, #fable)."""
    contents = "".join(
        f'<li><a href="#{anchor}">{html.escape(title)}</a></li>' for anchor, title in POEM_ANCHORS.items()
    )
    keep = _poem_section(
        "keep", POEM_TITLE, POEM, "With thanks from Edward and Claude",
        '<p class="meta">Drawings &copy; Bungie: concept art for <em>Myth: The Fallen Lords</em> and '
        '<em>Myth II: Soulblighter</em> by Juan Ramirez, from Bungie&rsquo;s old Myth gallery, and Soulblighter '
        'from the <em>Myth II</em> manual, via <a href="http://myth.bungie.org/legends/journal/">Myth.Bungie.Org</a>. '
        'The thrall&rsquo;s and the cloaked figure&rsquo;s artists are unknown to us.</p>',
    )
    walter = _poem_section(
        "walter", WALTER_TITLE, WALTER_POEM, "From Edward and Claude",
        '<p class="meta">Myth&rsquo;s wight &copy; Bungie: concept art for <em>Myth: The Fallen Lords</em> by '
        'Juan Ramirez, from Bungie&rsquo;s old Myth gallery. Grendel, whom <em>Beowulf</em> calls a <em>wiht</em>: '
        'painting by J. R. Skelton for <em>Stories of Beowulf</em> (1908). The other two wights are signed by their '
        'artists, whom we have not yet identified. &ldquo;Sweete wight&rdquo; is Chaucer&rsquo;s, from '
        '<em>The Reeve&rsquo;s Tale</em>. Walter, tell us how Sir Mauriac&rsquo;s Tale plays in '
        '<a href="../q/7.html">Q7</a>, or how a plugin of your own converts in <a href="../q/9.html">Q9</a>.</p>',
    )
    fable = _poem_section("fable", FABLE_TITLE, FABLE_POEM, "Claude Fable 5.2, 16 November 2026")
    return (
        f'<ul>{contents}</ul>' + keep + walter + fable
        + '<div class="nav"><a href="index.html">&larr; Keep &amp; Claude Conversation</a></div>'
    )


UNITS_TITLE, UNIT_FIELDS = _load_units()


def units_html():
    rows = "".join(
        f"<tr><td>{html.escape(tfl)}</td><td>{html.escape(magma)}</td><td>77</td><td><strong>{path}</strong></td>"
        f"<td>0</td><td><strong>{hack}</strong></td></tr>"
        for tfl, magma, path, hack in UNIT_FIELDS
    )
    return (
        f'<p class="gist"><strong>Updated {_long_date(GISTS_UPDATED)}</strong> <span class="meta">Checked against '
        "converter 0.19.</span> The table and the settings are unchanged; the paragraph on why the Forest Giant and the "
        "trow would not attack is corrected.</p>"
        "<p>An answer to Keep's question in Bagrada chat: <em>which</em> settings, and what does "
        "&ldquo;Magma's own version of each unit&rdquo; mean?</p>"
        "<h2>Which settings</h2>"
        "<p>Only one tag: the <strong>mons</strong> (monster) tag. Myth II's mons tag has 17 fields that "
        "The Fallen Lords' does not have at all. Every other field is copied from the unit's own TFL value. "
        "For these 17 the converter has nothing to copy, so it has to choose a value. It chose one value for "
        "every unit: the most common one in Project Magma's port of The Fallen Lords.</p>"
        "<p>Checked against Magma's port, unit by unit: <strong>15 of the 17 are the same for every unit</strong> "
        "(mana, berserk, artifacts carried, experience, propulsion, map action, hack flags and so on), and our "
        "value already matches Magma's for all 39 units it ported. Only two differ from unit to unit:</p>"
        "<ul><li><strong>pathfinding radius</strong>: how much room the unit needs when finding its way "
        "around others. We gave every unit 77; Magma's values run from 51 to 220.</li>"
        "<li><strong>more hack flags</strong>: not documented anywhere we have found. 0, 50, 90 or 100 in Magma.</li></ul>"
        "<h2>Magma's own version of each unit</h2>"
        "<p>For a thrall, copy what Magma gave its thrall; for a trow, Magma's trow; and so on, instead of one "
        "value for all. Since version 0.15 the converter does that, choosing by the sprites the unit is drawn "
        "with, so a plugin's own unit built on thrall sprites gets the thrall's values.</p>"
        "<p>Two units stand out: the <strong>Forest Giant</strong> (220 in Magma, 77 from us before) and the "
        "<strong>trow</strong> (154 and 90, against 77 and 0). They are the two Keep found would not attack. "
        "The room was not the cause: they began to attack in version 0.17, which fixed two other bugs (every unit "
        "had been marked giant-sized, and each attack's giant flags were scrambled), and Keep confirmed it in the game.</p>"
        '<div class="scroll"><table><thead><tr><th>TFL unit</th><th>Magma&rsquo;s unit</th>'
        "<th>Pathfinding radius, before</th><th>Magma and 0.15</th><th>More hack flags, before</th>"
        "<th>Magma and 0.15</th></tr></thead><tbody>" + rows + "</tbody></table></div>"
        '<p class="meta">Measured from <em>Magma - The Fallen Lords v1.9</em> against the stock Fallen Lords '
        "monsters it carries. Where several units share sprites, the converter uses the value most of them "
        "share: the falling dwarf (159), the spider queen (169), the telltale (77) and the berserk hero (77) get their group's value "
        "instead of their own.</p>"
        '<div class="nav"><a href="index.html">&larr; Keep &amp; Claude Conversation</a></div>'
    )


KEEP_BODY = _KEEP["body"]


MADE_BY = (
    f'Made by Edulus, with Keep and Claude Code. '
    f'The code is on <a href="https://github.com/{REPO}">GitHub</a>.'
)
# Said plainly on every page, for visitors and for anyone checking the site.
HONEST = (
    "An unofficial, non-commercial fan project for the 1990s games <em>Myth: The Fallen Lords</em> and "
    "<em>Myth II</em>, not affiliated with Bungie. It never asks for an email address, a password or a payment. "
    "Its downloads are Myth plugin data files for the game to read, not programs to install or run."
)
CREDIT = (
    "Artwork: <em>Myth II: Soulblighter</em> desktop picture and <em>Myth: The Fallen Lords</em> "
    "box art, &copy; Bungie / Take-Two, shown in black and white. Screenshot from our own testing. "
    "Conversion rules learned by comparison with Project Magma&rsquo;s hand-made ports, above all "
    "<em>The Fallen Levels v2</em> by IronDuke, Haravikk, Infininight and Grasshopper. "
    "An unofficial, non-commercial fan project."
)


# Browsers keep style.css for 10 minutes (GitHub Pages' max-age); a version
# tag tied to its contents makes a changed stylesheet load at once.
STYLE_VERSION = __import__("hashlib").sha1(STYLE.encode()).hexdigest()[:8]


# A row of links at the foot of every page, so every page can be found from
# any other -- Keep's conversation page included.
def sitemap(up):
    rows = [
        ("", [("Home", "index.html"), ("Convert a plugin", "convert/index.html"),
              ("Swap Civil War units", "swap/index.html"), ("Keep &amp; Claude Conversation", "keep/index.html"), ("Poems", "keep/poems.html"),
              ("Monster settings", "keep/units.html")]),
        ("Updates", [(u["date"], f"updates/{u['slug']}.html") for u in reversed(UPDATES)]),
        ("Questions", [(f"Q{q['n']}", f"q/{q['n']}.html") for q in QUESTIONS if "closed" not in q]
         + [("Closed: " + ", ".join(f"Q{q['n']}" for q in QUESTIONS if "closed" in q), "q/closed.html")]),
    ]
    html_rows = "".join(
        f'<ul>{f"<li class=label>{label}</li>" if label else ""}'
        + "".join(f'<li><a href="{up}{href}">{text}</a></li>' for text, href in links)
        + "</ul>"
        for label, links in rows
    )
    return f'<nav class="sitemap" aria-label="Site map">{html_rows}</nav>'


def answer_box(term, box_id="answer", label="Your answer"):
    """A comment box for one thread; a page may carry several (distinct ids)."""
    return GIVE_ANSWER.format(term=html.escape(term), api=html.escape(COMMENTS_API), id=box_id, label=label)


def redirect_page(path, target, title, label):
    """A small page in the site's chrome that sends visitors on to `target`
    (relative to the page); the old address keeps working."""
    body = f'<p>This page has moved: <a href="{target}">{html.escape(label)}</a>.</p>'
    path.write_text(
        page(title, title, body, 1, kicker="Moved", head=f'<meta http-equiv="refresh" content="0; url={target}">\n'),
        encoding="utf-8",
    )


def page(title, heading, body, depth, term=None, kicker="", subtitle="", lock=None, body_class="", head="",
         comments_js=False):
    up = "../" * depth
    answer = scripts = gate = ""
    if term:
        answer = answer_box(term)
    if term or comments_js:
        scripts = f"<script>{COMMENTS_JS}</script>"
    if lock:
        gate = LOCK_HTML.format(question=html.escape(lock["question"]))
        scripts += f"<script>{LOCK_JS.replace('{hash}', lock['hash'])}</script>"
    kicker_html = f'<p class="meta">{kicker}</p>' if kicker else ""
    subtitle_html = f'<p class="subtitle">{subtitle}</p>' if subtitle else ""
    brand = "" if depth == 0 else f'<a class="brand" href="{up}index.html">{SITE_NAME} &middot; {SITE_TAGLINE}</a>'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
{head}<title>{html.escape(title)} &middot; {SITE_NAME}</title>
<script>try{{if(localStorage.getItem("theme")==="dark")document.documentElement.dataset.theme="dark"}}catch(e){{}}</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700&family=IM+Fell+English:ital@0;1&display=swap">
<link rel="stylesheet" href="{up}style.css?v={STYLE_VERSION}">
</head>
<body{f' class="{body_class}"' if body_class else ''}>
<header class="hero{' compact' if depth else ''}">
<button class="theme" type="button" aria-label="Switch between light and dark" title="Light / dark"></button>
<div class="panes" aria-hidden="true">
<div class="pane one"><span class="num">I</span><span class="cap">The Fallen Lords</span></div>
<div class="arrow">&rarr;</div>
<div class="pane two"><span class="num">II</span><span class="cap">Soulblighter</span></div>
</div>
<div class="band"><div class="inner">
{brand}
{kicker_html}
<h1>{heading}</h1>
{subtitle_html}
</div></div>
</header>
{gate}
<main class="wrap"{' hidden' if lock else ''}>
{body}
{answer}
</main>
<footer>{sitemap(up)}<p class="made">{MADE_BY}</p><p class="made">{HONEST}</p><p>{CREDIT}</p></footer>
<script>{THEME_JS}</script>
{scripts}
</body>
</html>
"""


DOCKET_UPDATED, DOCKET = _load_docket()


# Groups folded away by default on the home page (the summary shows the count).
FOLDED_GROUPS = ("Up next", "Later")


def docket_html():
    def group(title, items):
        lis = "\n".join(f"<li>{html.escape(item)}</li>" for item in items)
        if title in FOLDED_GROUPS:
            return (f'<details class="fold"><summary>{html.escape(title)} ({len(items)} items)</summary>\n'
                    f"<ul>\n{lis}\n</ul>\n</details>")
        return f"<h3>{html.escape(title)}</h3>\n<ul>\n{lis}\n</ul>"

    # "Please test now" first, whatever its place in the file; the rest in file order.
    ordered = sorted(DOCKET.items(), key=lambda kv: not kv[0].startswith("Please test now"))
    groups = "\n".join(group(title, items) for title, items in ordered)
    return f"""<section class="release docket" aria-labelledby="docket">
<h2 id="docket">What we're working on</h2>
<p class="meta">Updated {_long_date(DOCKET_UPDATED)}. What's already done is listed on the <a href="convert/index.html">converter page</a>. Found something else? Tell us in <a href="q/7.html">Q7</a>.</p>
{groups}
</section>"""


def q_href(q, base=""):
    """Where a question lives, relative to `base` (the q/ folder): its own page,
    or its section on the Closed questions page."""
    return f'{base}closed.html#q{q["n"]}' if "closed" in q else f'{base}{q["n"]}.html'


def build(stock_dir=None):
    OUT.mkdir(exist_ok=True)
    (OUT / "updates").mkdir(exist_ok=True)
    (OUT / "q").mkdir(exist_ok=True)
    (OUT / ".nojekyll").write_text("")
    (OUT / "style.css").write_text(STYLE.strip() + "\n", encoding="utf-8")

    def card(href, tag, title, sub=""):
        sub = f'<span class="sub">{sub}</span>' if sub else ""
        return (
            f'<li class="card"><a href="{href}"><span class="body"><span class="title">'
            f'<span class="tag">{tag}</span>{title}</span>{sub}</span>'
            f'<span class="btn">Read &amp; reply &rarr;</span></a></li>'
        )

    updates = "\n".join(
        card(f'updates/{u["slug"]}.html', u["date"], u["title"], html.escape(u["summary"]))
        for u in UPDATES
    )
    def question_card(q):
        sub = f'Summary of {_long_date(GISTS_UPDATED)}'
        if q.get("unanswered"):
            sub += f'<span class="quiet" title="as of {_long_date(GISTS_UPDATED)}">no replies yet</span>'
        return card(f'q/{q["n"]}.html', f'Q{q["n"]}', q["title"], sub)

    questions = "\n".join(question_card(q) for q in QUESTIONS if "closed" not in q)
    closed = "\n".join(
        card(q_href(q, "q/"), f'Q{q["n"]}', q["title"], "Closed: " + html.escape(q["closed"]))
        for q in QUESTIONS if "closed" in q
    )
    index = f"""{docket_html()}
<section aria-labelledby="news">
<h2 id="news" style="margin-top:0">News</h2>
<h3>New: convert a plugin in your browser (beta)</h3>
<p>No Python, no command line, no setup. Drop a <em>Fallen Lords</em> plugin on the new page and it converts right there in your browser tab. Your file is not uploaded anywhere. You get back a Myth II plugin with the original game files it needs already inside, ready to put in your <code>plugins</code> folder.</p>
<p><a class="btn" href="convert/index.html">Convert a plugin &rarr;</a></p>
<ul>
<li><strong>Tested so far:</strong> <em>Sir Mauriac's Tale</em>, in Chrome on Windows. The result played <em>Tandem</em> on a plain Myth II 1.8.5 install.</li>
<li>Use a computer, not a phone: it needs about 1 GB of memory. The first time, it fetches about 320 MB of original game files from this site.</li>
</ul>
<hr class="news-rule">
<h3>New: swap the Civil War soldiers for regular units (beta)</h3>
<p>A companion tool for the Civil War plugins, built because Obelix asked for it. Pick which regular units, such as warriors or ghols, appear in place of the Civil War soldiers on its maps. It writes a new plugin and leaves the original alone. <strong>It now runs in your browser, with nothing uploaded</strong>; it is also part of this project's app (<code>python -m src studio</code>, then <strong>Swap units (Civil War)</strong>) and works from the command line.</p>
<p><a class="btn" href="swap/index.html">Swap Civil War units &rarr;</a></p>
<ul>
<li><strong>Tested so far:</strong> <em>Civil War Reloaded 1.8.4</em> and the <em>Fields of Battle</em> map pack (with its 1.7 tagset), on a clean Myth II 1.8.5 install. Real warriors and ghols appeared on <em>Fort Sumter</em> and <em>Little Flat Top</em>. Other maps, other units and other Civil War packs are untested.</li>
<li><strong>You supply the Civil War files</strong> (its maps and its tagset) and your own Myth II folder. None of it is included here.</li>
<li><strong>To play:</strong> choose the new campaign first, then activate the tagset under Tagsets.</li>
<li>Steps and limits are in the <a href="{REPO_URL}#swapping-units-civil-war-maps">README</a>.</li>
</ul>
<hr class="news-rule">
<h3>Ready-made download: <em>Sir Mauriac's Tale</em></h3>
<p>Skip the setup and play a plugin that is already converted. <em>Sir Mauriac's Tale</em> is a Fallen Lords campaign by CbC (the Crow's Bridge Cartographers), converted for Myth II 1.8.5 by Edulus, the co-creator of this plugin (with Keep and Claude). Nothing else to install: the Fallen Lords tags it relies on are inside the plugin.</p>
<p><a class="btn" href="{DOWNLOAD_URL}">&darr; Download Sir Mauriac&rsquo;s Tale ({DOWNLOAD_MB} MB zip of Myth II plugin files; no program to run)</a></p>
<ul>
<li><strong>Beta, converter {DOWNLOAD_VERSION}</strong> (updated 19 November 2026; the first download was 0.12). <em>Tandem</em> and <em>In the Name of Glory</em> have been played to the end-game screen with earlier versions; the other levels are untested. This {DOWNLOAD_VERSION} download has not been played in the game yet.</li>
<li>Quit Myth II and extract the zip <strong>straight into</strong> Myth II's <code>plugins</code> folder, not a subfolder (Myth II only finds plugins sitting directly in it). You get the plugin <code>ZZ Mauriac TFL2SB</code> plus a read-me and CbC's credits. Then choose <strong>New Game</strong> &rarr; the campaign <em>ZZ Mauriac TFL2SB</em> &rarr; a level. Leave Tagsets empty.</li>
</ul>
</section>
<section aria-labelledby="get-started">
<h2 id="get-started">Get started &mdash; public beta</h2>
<p>Convert a <em>Myth: The Fallen Lords</em> plugin for <em>Myth II: Soulblighter</em>. The easiest way is the <a href="convert/index.html">in-browser converter</a>. If you only want to play, the <a href="{DOWNLOAD_URL}">ready-made <em>Sir Mauriac's Tale</em> download</a> above needs none of this. The command-line steps below are for those who want more control; no Python packages need installing.</p>
<p><strong>You need:</strong> Myth II 1.8.5, Python 3.12 or later, a TFL plugin (<code>.gor</code>), and your own TFL game's <code>tags</code> folder containing <code>TAGS.GOR</code> and <code>ARTSOUND.GOR</code>. Game files are not included.</p>
<p>Bought the discs but lost or damaged them? The game's files can be found at <a href="https://www.myabandonware.com/game/myth-the-fallen-lords-3no">My Abandonware</a> or on the <a href="https://archive.org/details/MythTheFallenLordsUSA">Internet Archive</a>. (The in-browser converter doesn't need them: it brings its own.)</p>
<details class="fold"><summary>The command-line steps (five steps, for more control)</summary>
<ol>
<li><strong>Download and unzip.</strong> Open <a href="{REPO_URL}">the repository</a> and choose <strong>Code &rarr; Download ZIP</strong>, then extract it. This ZIP holds the converter's code and is only for the command-line route; the ready-made download and the in-browser converter need no download of the code. With Git, you can instead run:
<pre><code>git clone {REPO_URL}.git
cd Myth-1-to-2-plugin-converter</code></pre></li>
<li><strong>Set up Python.</strong> On Windows, double-click <code>launch.bat</code> in the extracted folder. It looks for Python 3.12+ and attempts to install it with winget if missing; follow its instructions and run it again after installation. If winget is unavailable, it opens the Python download page. On other systems, install Python 3.12+ first.
<p>The launcher opens the guided browser app. <strong>That app cannot build the stock tagset yet.</strong> Use a terminal for the next two steps. On Windows, open the extracted folder in File Explorer, type <code>powershell</code> into its address bar and press Enter. Commands must run in the folder containing <code>launch.bat</code> and <code>src</code>. Close Myth II before writing plugins.</p></li>
<li><strong>Build the stock tagset once.</strong> Replace every example path with your own, keeping the quotes. Use <code>python3</code> instead of <code>python</code> if that is your Python 3.12+ command; on Windows, <code>py -3.12</code> is another option.
<pre><code>python -m src tagset --in "TFL/tags/TAGS.GOR" --in "TFL/tags/ARTSOUND.GOR" --out "Myth II/plugins/ZZ TFL stock"</code></pre>
<p>This supplies the original game's tags that community plugins depend on. The output is a file with no extension, inside your Myth II <code>plugins</code> folder.</p></li>
<li><strong>Convert a plugin.</strong> Extract the plugin's ZIP first, then point at its <code>.gor</code> file:
<pre><code>python -m src convert --in "Sir Mauriac's Tale.gor" --out "Myth II/plugins/ZZ Mauriac"</code></pre>
<p><strong>Shortcut:</strong> add <code>--stock "TFL/tags/TAGS.GOR" --stock "TFL/tags/ARTSOUND.GOR"</code> to this command and the stock tags are built into the converted plugin. You can then skip step 3 and the tagset choice in step 5. The file is much larger, and it is the form to share. Only share a plugin whose author agrees.</p>
<p>No decisions file is required for this baseline workflow. Conversion warnings identify unsupported content; producing a file does not guarantee that every level will play.</p></li>
<li><strong>Play in Myth II.</strong> Start the game &rarr; <strong>New Game</strong> &rarr; choose the converted campaign &rarr; <strong>Tagsets</strong> &rarr; activate <strong>ZZ TFL stock</strong> &rarr; pick a level &rarr; <strong>OK</strong>. Choose the tagset <em>after</em> the campaign, because changing campaigns can clear the selection.</li>
</ol>
<p><strong>Optional guided app:</strong> run <code>python -m src studio</code> or double-click <code>launch.bat</code>. It can preview and convert an individual plugin and read the game log. Build the stock tagset with the command above first. Its missing-reference suggestions are not a check against the complete stock tagset; the command-line route above is the tested starting point.</p>
</details>
<details class="fold"><summary>Before you test (five points)</summary>
<ul>
<li>Quit Myth II before converting or replacing plugin files; the game holds them open. Restart after adding files.</li>
<li>Keep output filenames at most 32 characters. The internal plugin name defaults to that filename; use distinct names so plugins do not hide each other.</li>
<li>The stock tagset replaces same-ID Myth II tags while active. Activate it only for converted TFL levels.</li>
<li>Only one campaign can load at a time. The stock tagset contains no selectable levels, so it can load alongside your converted campaign.</li>
<li>If writing to the install folder fails, write to a folder you can access and copy the finished files into Myth II's <code>plugins</code> folder while the game is closed.</li>
</ul>
</details>
</section>
<h2>What works &mdash; and what needs testing</h2>
<p><strong>Two levels have reached the end-game screen in Myth II 1.8.5:</strong> <em>Tandem</em> and <em>In the Name of Glory</em> from <em>Sir Mauriac's Tale</em>. This is a beta, not a claim that every TFL plugin works.</p>
<ul>
<li>Converted: terrain, markers, map actions, monsters and units, objects, projectiles, artifacts, scenery, particle effects, mesh effects, lighting, ambient sounds, sprite collections, 3D models and text.</li>
<li>Buildings and other 3D models are converted and placed. Lighting uses standard values for every map. Terrain is redrawn on Myth II's finer grid, with heights blended between the original points.</li>
<li>Copied unchanged and reported as not converted: the water settings, which are known to differ from Myth II's own and still need a converter (water behaved correctly where Keep checked it), and a few minor kinds of data we have too few examples to judge. Sounds, collection references, projectile groups and physics settings are also copied unchanged, because comparing them with Myth II's own files and Project Magma's showed no systematic difference. Some death and explosion effects are still missing.</li>
<li>Confirmed in the game by Keep: water, riverbanks and heights; Crow's Bridge's bridge; buildings; hosted multiplayer games with units, scenery, flags and balls; no black ground after explosions; units that stand still when they stop; Forest Giants, Old Growth Forest Giants and Trow that attack; healers that heal. Not yet checked: unit size (Keep is measuring it), Dwarf Heroes throwing uphill (a 0.19 fix), other levels, and multiplayer in general.</li>
</ul>
<h2>Help test or report a problem</h2>
<p>Every visitor can help. Try a level you know and report what differs from TFL. Open a question or progress update below and use its comment box: a name, message and one-word Myth check &mdash; <strong>no account or sign-in</strong>.</p>
<p>Include the plugin and level names, Myth II version, what you expected, what happened, and the final lines of <code>myth_log.txt</code> from the Myth II folder. For a crash, include relevant lines from the newest <code>myth_crashlog- &lt;date&gt;.txt</code>. Check that the log lists both your campaign and stock tagset after <code>Starting mesh</code>. Share logs and observations, not game files; remove private paths if needed.</p>
<p>Code contributions are welcome through <a href="{REPO_URL}">GitHub</a>; the <a href="{REPO_URL}/blob/main/README.md">README</a> and <a href="{REPO_URL}/tree/main/documentation">documentation</a> describe current support and research.</p>
<h2>Open questions for testers</h2>
<ul class="cards">{questions}</ul>
<h3>Closed questions</h3>
<ul class="cards closed">{closed}</ul>
<h2>Progress log</h2>
<ul class="cards">{updates}</ul>
<h2>About, credits and licence</h2>
<p>Built on <a href="https://github.com/jwheare/mythextract">mythextract</a>, MIT licence, &copy; 2025 James Wheare. The converter's code is <a href="{REPO_URL}/blob/main/LICENSE">MIT-licensed</a>; see <a href="{REPO_URL}/blob/main/NOTICE">NOTICE</a> for prior art.</p>
<p>Myth: The Fallen Lords and Myth II: Soulblighter are trademarks of their respective rights holders. This is an unofficial, non-commercial interoperability tool, not affiliated with or endorsed by any rights holder. The in-browser converter serves the original <em>Fallen Lords</em> game files (&copy; Bungie) so that converted plugins need nothing else installed; otherwise users supply their own copies.</p>"""
    (OUT / "index.html").write_text(
        page(html.unescape(SITE_TAGLINE), SITE_NAME, index, 0, subtitle=SITE_TAGLINE), encoding="utf-8"
    )

    for u in UPDATES:
        body = f"""{u["body"]}
<div class="nav"><a href="../index.html">&larr; All updates and questions</a><a href="../q/1.html">Questions for testers &rarr;</a></div>"""
        (OUT / "updates" / f'{u["slug"]}.html').write_text(
            page(u["title"], u["title"], body, 1, u["term"], kicker=f'Update &middot; {u["date"]}'),
            encoding="utf-8",
        )

    def neighbours(i):
        prev = (
            f'<a href="{q_href(QUESTIONS[i - 1])}">&larr; Q{QUESTIONS[i - 1]["n"]}</a>'
            if i else '<a href="../index.html">&larr; All updates and questions</a>'
        )
        nxt = (
            f'<a href="{q_href(QUESTIONS[i + 1])}">Q{QUESTIONS[i + 1]["n"]} &rarr;</a>'
            if i + 1 < len(QUESTIONS) else '<a href="../index.html">All updates and questions &rarr;</a>'
        )
        return f'<div class="nav">{prev}{nxt}</div>'

    def question_body(q, i, box_id):
        closed_note = (
            f'<p class="problem"><strong>Closed.</strong> {html.escape(q["closed"])}</p>\n' if "closed" in q else ""
        )
        gist = (
            f'<p class="gist"><strong>In short</strong> <span class="meta">(as of {_long_date(GISTS_UPDATED)})</span> '
            f'{html.escape(QUESTION_GISTS[q["n"]])}</p>\n'
        )
        return f"""{gist}{closed_note}{q["body"]}
<p class="answer-top"><a class="btn" href="#{box_id}">&#9998; Answer this &darr;</a></p>
{neighbours(i)}"""

    for i, q in enumerate(QUESTIONS):
        if "closed" in q:
            continue
        (OUT / "q" / f'{q["n"]}.html').write_text(
            page(f'Q{q["n"]}', f'Q{q["n"]}. {q["title"]}', question_body(q, i, "answer"), 1, q["term"],
                 kicker=f'Question {q["n"]} of {len(QUESTIONS)}'),
            encoding="utf-8",
        )

    # Closed questions share one page, each with its own comment thread (its
    # original term, so the comments already there are kept); the old
    # q/<n>.html addresses redirect to its section.
    closed_qs = [(i, q) for i, q in enumerate(QUESTIONS) if "closed" in q]
    sections = "".join(
        f'<section id="q{q["n"]}"><h2>Q{q["n"]}. {q["title"]}</h2>\n{question_body(q, i, "answer-%d" % q["n"])}\n'
        + answer_box(q["term"], "answer-%d" % q["n"], "Your answer to Q%d" % q["n"]) + "</section>"
        for i, q in closed_qs
    )
    (OUT / "q" / "closed.html").write_text(
        page("Closed questions", "Closed questions",
             '<p class="meta">Questions that have been answered. They stay readable, and you can still add to their threads.</p>'
             + sections + '<div class="nav"><a href="../index.html">&larr; All updates and questions</a></div>',
             1, kicker="Questions", comments_js=True),
        encoding="utf-8",
    )
    for i, q in closed_qs:
        redirect_page(OUT / "q" / f'{q["n"]}.html', f'closed.html#q{q["n"]}', f'Q{q["n"]}',
                      f'Q{q["n"]}. {q["title"]} (on the Closed questions page)')

    (OUT / "keep").mkdir(exist_ok=True)
    (OUT / "keep" / "poems.html").write_text(
        page("Poems", "Poems", poems_html(), 1, kicker="For Keep and Walter", body_class="white"), encoding="utf-8"
    )
    redirect_page(OUT / "keep" / "poem.html", "poems.html#keep", "Poem for Keep",
                  f"{POEM_TITLE} (on the Poems page)")
    redirect_page(OUT / "keep" / "walter.html", "poems.html#walter", "Poem for Walter",
                  f"{WALTER_TITLE} (on the Poems page)")
    (OUT / "keep" / "units.html").write_text(
        page(UNITS_TITLE, UNITS_TITLE, units_html(), 1, kicker="For Keep"), encoding="utf-8"
    )
    (OUT / "keep" / "index.html").write_text(
        page("Keep & Claude Conversation", "Keep &amp; Claude Conversation", KEEP_BODY, 1, KEEP_PAGE["term"])
        .replace("&#9998; Your answer", "&#9998; Your message"),
        encoding="utf-8",
    )

    build_converter_page(stock_dir)
    build_swap_page()
    print(f"built {len(UPDATES)} update(s) and {len(QUESTIONS)} question(s) into {OUT}")


# --- The in-browser converter (docs/convert/) --------------------------------
# The page's scripts live in web/convert/; the converter itself is src/, zipped
# for Pyodide. The stock TFL tags it bundles are served from docs/convert/stock/,
# split into pieces because GitHub refuses files over 100 MB. They are copied in
# only when --stock-dir is given; otherwise the pieces already there are kept.

WEB = ROOT / "web" / "convert"
STOCK_FILES = ("TAGS.GOR", "ARTSOUND.GOR")  # most authoritative first
STOCK_PIECE = 80 * 1024 * 1024
# Not needed to convert in the browser, and the studio pulls in a web server.
CODE_SKIP = ("studio",)


def _short_hash(data):
    return hashlib.sha256(data).hexdigest()[:12]


def _source_bytes(path):
    """A text source's bytes with Unix line endings, so the site builds the
    same on Windows (whose checkouts have CRLF) as on Linux (CI)."""
    return pathlib.Path(path).read_bytes().replace(b"\r\n", b"\n")


def converter_zip():
    """src/ as a zip, byte-for-byte the same for the same sources, so an
    unchanged converter does not show up as a changed file. Stored, not
    compressed: zlib versions compress the same bytes differently, so a
    compressed zip built on Windows differed from CI's Linux build (and the
    pages' cache hashes with it). About 360 KB instead of 130 KB."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for path in sorted((ROOT / "src").rglob("*.py")):
            rel = path.relative_to(ROOT)
            if any(part in CODE_SKIP for part in rel.parts):
                continue
            info = zipfile.ZipInfo(rel.as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3  # zipfile stamps 0 on Windows, 3 elsewhere
            zf.writestr(info, _source_bytes(path))
    return buf.getvalue()


def split_stock(stock_dir, out_dir):
    """Copy the stock archives into out_dir in pieces, and describe them in
    manifest.json for worker.js. The names avoid ``.gor``, which .gitignore
    keeps out of the repository everywhere else."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.iterdir():
        old.unlink()
    files, digest = [], hashlib.sha256()
    for name in STOCK_FILES:
        data = (pathlib.Path(stock_dir) / name).read_bytes()
        digest.update(data)
        stem = name.split(".")[0].lower()
        parts = []
        for i in range(0, len(data), STOCK_PIECE):
            part = f"{stem}.{len(parts)}"
            (out_dir / part).write_bytes(data[i : i + STOCK_PIECE])
            parts.append(part)
        files.append({"name": name, "bytes": len(data), "parts": parts})
    manifest = {"version": digest.hexdigest()[:12], "files": files}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")


# What testers see change. Add an entry, and bump src/__init__.py's
# __version__ to match, whenever a push changes what the converter does.
CHANGES = json.loads((WEB / "changes.json").read_text(encoding="utf-8"))


def _long_date(iso):
    year, month, day = (int(p) for p in iso.split("-"))
    months = ("January February March April May June July August September "
              "October November December").split()
    return f"{day} {months[month - 1]} {year}"


def changes_html():
    """The release panel: version and build date, what to test next, and the
    list of changes, newest first."""
    newest = CHANGES[0]
    tests = "\n".join(f"<li>{html.escape(t)}</li>" for t in newest["test"])
    items = "\n".join(
        f'<li><strong>{html.escape(c["version"])}</strong> ({_long_date(c["date"])}): {html.escape(c["change"])}</li>'
        for c in CHANGES
    )
    return f"""<section class="release" aria-labelledby="release">
<h2 id="release">Version {html.escape(newest["version"])} &middot; built {_long_date(newest["date"])}</h2>
<h3>Please test next</h3>
<ul>
{tests}
</ul>
<p>Report what you find in <a href="../q/7.html">Q7: feature and bug reports</a>, with the version number.</p>
<h3>What changed</h3>
<ul class="changes">
{items}
</ul>
</section>"""


CONVERT_BODY = """
<p class="gist"><strong>Updated {updated}:</strong> this page offers converter {version}. The list below says what changed in each version; what Keep has confirmed in the game is on the <a href="../index.html">home page</a>.</p>
{changes}
<div id="converter" data-worker="worker.js?v={worker_v}" data-code="converter.zip?v={code_v}" data-manifest="stock/manifest.json?v={stock_v}" data-api="{api}" data-version="{version}">
<p class="intro">Turn a <em>Myth: The Fallen Lords</em> plugin into one that <em>Myth II: Soulblighter</em> 1.8.5 can play. It runs entirely in this browser tab: <strong>your file is not uploaded anywhere.</strong> Only the plugin's name, its number of levels, the converter version and the date are added to the public list further down, and only while the box below stays ticked. Untick it to keep your conversion off the list.</p>
<label class="share"><input type="checkbox" id="share" checked> Add this plugin's name to the public list of converted maps</label>
<label class="drop" id="drop"><input type="file" id="pick" accept=".gor,.GOR">
<span class="drop-big">Drop the plugin's <code>.gor</code> file here</span>
<span class="meta">or click to choose it. Unzip it first if it came as a zip.</span></label>
<div id="progress" hidden><p id="stage" role="status"></p><progress id="bar"></progress></div>
<div id="problem" class="problem" role="alert" hidden></div>
<div id="result" hidden></div>
</div>
<section aria-labelledby="log-heading">
<h2 id="log-heading">Maps converted so far</h2>
<p class="meta">Plugins visitors chose to list after converting them here, newest first.</p>
<div id="log"><p class="meta">Loading&hellip;</p></div>
</section>
<h2>Good to know</h2>
<ul>
<li><strong>Use a computer, not a phone.</strong> Converting needs a lot of memory; close other tabs if it fails.</li>
<li>The first time, the page fetches the original Fallen Lords game files ({stock_mb} MB) from this website. Your browser keeps them for next time.</li>
<li>The converted plugin carries the original game files it needs, so you don't need anything else installed.</li>
<li><strong>Beta.</strong> Tested with <em>Sir Mauriac's Tale</em> on Windows. Other plugins may convert with parts missing, and the report tells you what it could not convert.</li>
<li>Only share a converted plugin if its author agrees.</li>
<li>After you try a converted plugin, please tell us how it went in <a href="../q/9.html">Q9: Tried converting a map of your own?</a>, even if it worked.</li>
<li>Found a bug, or want a feature? Tell us in <a href="../q/7.html">Q7: feature and bug reports</a>.</li>
</ul>
<div class="nav"><a href="../index.html">&larr; Back to the home page</a></div>
<script src="page.js?v={page_v}"></script>"""


def build_converter_page(stock_dir=None):
    out = OUT / "convert"
    out.mkdir(exist_ok=True)
    code = converter_zip()
    (out / "converter.zip").write_bytes(code)
    versions = {"code_v": _short_hash(code)}
    for name in ("worker.js", "page.js"):
        data = _source_bytes(WEB / name)
        (out / name).write_bytes(data)
        versions[name.split(".")[0] + "_v"] = _short_hash(data)
    if stock_dir:
        split_stock(stock_dir, out / "stock")
    manifest_path = out / "stock" / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        versions["stock_v"] = manifest["version"]
        stock_mb = round(sum(f["bytes"] for f in manifest["files"]) / 1048576)
    else:
        print("warning: no stock files in docs/convert/stock; run with --stock-dir")
        versions["stock_v"], stock_mb = "none", "about 320"
    (out / "index.html").write_text(
        page("Convert a plugin", "Convert a plugin", CONVERT_BODY.format(
            stock_mb=stock_mb, changes=changes_html(), api=html.escape(COMMENTS_API), updated=_long_date(GISTS_UPDATED),
            version=html.escape(CHANGES[0]["version"]), **versions,
        ), 1,
             kicker="In your browser &middot; beta"),
        encoding="utf-8",
    )

# --- The in-browser unit swapper (docs/swap/) --------------------------------
# Built because Obelix asked for it. Its scripts live in web/swap/; it reuses the
# converter's Python bundle (docs/convert/converter.zip), which carries swap.py,
# swapstream.py and webswap.py.

WEB_SWAP = ROOT / "web" / "swap"
SWAP_TERM = "Civil War units swap: feedback"

OBELIX_POEM = (
    "Where Union blue met Rebel grey in war,",
    "Obelix asked for Legion steel once more,",
    "So warriors march where muskets used to sound,",
    "And ghols come snarling up the battleground;",
    "Let Alric's banner fly above the plain:",
    "For Obelix, the Legion fights again.",
)

SWAP_BODY = """
<p class="gist"><strong>Updated {updated}:</strong> checked again. The tool and what has been tried with it are unchanged.</p>
<p class="intro">Play the <em>Civil War</em> maps for <em>Myth II</em> with regular Myth II units. Choose which ordinary units, such as warriors or ghols, stand in place of the Civil War soldiers, and this page writes a new plugin. <strong>It runs entirely in this browser tab: your files are not uploaded anywhere</strong>, the new plugin is written on your own computer, and your original files are never changed.</p>

<section class="honour" aria-labelledby="obelix">
<h2 id="obelix">Thank you, Obelix</h2>
<p>This page exists because <strong>Obelix asked for it</strong>: a way to play the Civil War maps with regular Myth II units, with the player choosing which unit replaces which. A request like that is how this project grows, and we are grateful for it.</p>
<blockquote class="stanza-one"><p>{poem}</p><footer>For Obelix, who asked</footer></blockquote>
</section>

<div id="swapper" data-worker="worker.js?v={worker_v}" data-code="../convert/converter.zip?v={code_v}">
<h2>1. Choose your files</h2>
<p>You need three things, all from your own computer. The page reads them where they are; nothing is copied or sent anywhere.</p>
<div class="pickers">
<label class="pick"><span><strong>The maps</strong> &mdash; the plugin file that holds the Civil War maps, for example <code>CWR-Maps-184b</code> (no extension)</span>
<input type="file" id="maps"><em id="maps-note"></em></label>
<label class="pick"><span><strong>The tagset</strong> &mdash; the Civil War tagset those maps need, for example <code>CWR-Tagset-184b</code>. Use the one that matches your maps.</span>
<input type="file" id="tagset" multiple><em id="tagset-note"></em></label>
<label class="pick"><span><strong>Your Myth II folder</strong> &mdash; the one that holds the <code>tags</code> and <code>plugins</code> folders. Only Myth II&rsquo;s own game files are read from it, to bring the original units back. (Your browser will ask to let this page see the folder&rsquo;s files; it only reads the few it needs.)</span>
<input type="file" id="myth" webkitdirectory><em id="myth-note"></em></label>
</div>
<p><button type="button" class="btn" id="read" disabled>Read the maps</button></p>
<div id="progress" hidden><p id="stage" role="status"></p><progress id="bar"></progress></div>
<div id="problem" class="problem" role="alert" hidden></div>

<section id="choose" hidden>
<h2>2. Choose replacements</h2>
<p id="summary" class="meta"></p>
<div class="bulkbox">
<h3>Swap a whole side at once</h3>
<p class="bulk"><label>Yours &rarr; <select id="bulk-@"></select></label>
<label>Enemy &rarr; <select id="bulk-+"></select></label>
<button type="button" class="btn" id="apply-bulk">Apply to the table</button>
<button type="button" class="link" id="clear-all">Clear all</button></p>
<p class="meta">Sides are read from the unit names (starting <code>@</code> or <code>+</code>). You can still change any single row below.</p>
</div>
<label class="onlysides"><input type="checkbox" id="only-sides" checked> Show only side units (<code>@</code> and <code>+</code>); untick to see every unit the maps place</label>
<div class="tablewrap">
<table class="swaptable">
<thead><tr><th>Unit</th><th>Maps</th><th>Replace with</th></tr></thead>
<tbody id="rows"></tbody>
</table>
</div>
<p class="meta"><strong>Real Myth II units</strong> are the base game&rsquo;s own. The Civil War tagset redefines all of them, so when you choose one the original is restored inside your new plugin.</p>

<h2>3. Write the new plugin</h2>
<label class="field"><span>Name of the new plugin</span>
<input type="text" id="outname" value="ZZ Swapped units" maxlength="32" spellcheck="false">
<em>At most 32 characters, or Myth II will not list it.</em></label>
<p><button type="button" class="btn" id="build" disabled>Write the new plugin</button></p>
</section>
<div id="result" hidden></div>
</div>

<h2>Good to know</h2>
<ul>
<li><strong>Beta.</strong> The swapping itself was checked by hand on a clean Myth II 1.8.5 with <em>Civil War Reloaded 1.8.4</em> and the <em>Fields of Battle</em> map pack: real warriors and ghols appeared on <em>Fort Sumter</em> and <em>Little Flat Top</em>. Other maps, other units and other Civil War packs are untried, and this browser version is new. Tell us how it goes.</li>
<li><strong>Use a computer, not a phone,</strong> with a recent Chrome, Edge or Firefox. The files are read in place rather than loaded whole, but the new plugin is about as big as the maps plugin (around 520 MB for Civil War Reloaded 1.8.4), so keep some disk space and close other tabs.</li>
<li><strong>To play:</strong> in Myth II choose the new campaign first, then activate the tagset under <em>Tagsets</em>. The new plugin has to load after the tagset. The campaign list unlocks levels in order, so only the first ones are playable at first.</li>
<li><strong>You supply the Civil War files.</strong> None of them, and no Myth II game files, are included or copied to this site.</li>
<li>The swap was first checked against <em>Civil War Reloaded 1.8.4</em> by PoinT of ARMY Munitions Factory. That plugin builds on work by IronDuke (Project Magma), Cydonian, Thoran and others credited in its own readme. It is a third-party plugin.</li>
<li>How did it go? Tell us in <a href="../q/9.html">Q9: Tried converting a map of your own?</a>, report problems in <a href="../q/7.html">Q7</a>, or leave a comment below.</li>
</ul>
<div class="nav"><a href="../index.html">&larr; Back to the home page</a></div>
<script src="page.js?v={page_v}"></script>"""


def build_swap_page():
    out = OUT / "swap"
    out.mkdir(exist_ok=True)
    versions = {"code_v": _short_hash(converter_zip())}
    for name in ("worker.js", "page.js"):
        data = _source_bytes(WEB_SWAP / name)
        (out / name).write_bytes(data)
        versions[name.split(".")[0] + "_v"] = _short_hash(data)
    poem = "<br>".join(html.escape(line) for line in OBELIX_POEM)
    (out / "index.html").write_text(
        page("Swap the Civil War units", "Swap the Civil War soldiers for regular units",
             SWAP_BODY.format(poem=poem, updated=_long_date(GISTS_UPDATED), **versions), 1, term=SWAP_TERM,
             kicker="In your browser &middot; beta &middot; requested by Obelix"),
        encoding="utf-8",
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build the project site into docs/.")
    parser.add_argument(
        "--stock-dir", type=pathlib.Path,
        help="a TFL tags folder holding TAGS.GOR and ARTSOUND.GOR, to copy into the converter page",
    )
    build(parser.parse_args().stock_dir)
