"""Build the public project site into docs/ (served by GitHub Pages).

    python scripts/keep_site.py

Each update and each question gets a page of its own with a comment box that
needs no account -- a visitor types a name, a message and a one-word Myth answer.
The box talks to comments-worker/ (a Cloudflare Worker), which stores each
page's thread as a GitHub Discussion in the repo's Announcements category, so
Visitors can answer and reply section by section. To add to the site, add an entry
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

# Public project identity. Keep published discussion terms stable.
SITE_NAME = "Myth Plugin Converter"
SITE_TAGLINE = "The Fallen Lords &rarr; Soulblighter"

# The deployed comments-worker (see comments-worker/).
COMMENTS_API = "https://keep-comments.edyersh.workers.dev"

# A converted plugin offered as a GitHub Release asset (the zip is too big for Pages).
DOWNLOAD_ZIP = "Sir-Mauriac-Tale-for-Myth-II.zip"
DOWNLOAD_URL = f"{REPO_URL}/releases/download/sir-mauriac-sb-1/{DOWNLOAD_ZIP}"
DOWNLOAD_SHA256 = "92ff08aed5aa0ca612d77ecd0ab393efd240a86477fc12735e635c4b5d921f4f"
DOWNLOAD_MB = 220

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
<figure><img src="../img/tandem.jpg" alt="Tandem running in Myth II: warriors in formation, two archers and a villager on a stone path" width="1200" height="621"><figcaption>Tandem, converted from TFL, running in Myth II 1.8.5 &mdash; the first screenshot with units drawn.</figcaption></figure>
<p>Converting the original TFL tags made this possible. A TFL plugin leans on the stock TFL tags the way a Myth II plugin leans on the base game, and Magma's port doesn't carry them all under their original names &mdash; <em>Tandem</em> alone needed 76 it lacked. Converting the original <code>TAGS.GOR</code> and <code>ARTSOUND.GOR</code> into a Myth II tagset solved all of them at once. (Visitors supply their own files locally; no game data is distributed.)</p>

<h2>What converts now</h2>
<table>
<tr><th>Maps</th><td>terrain (upsampled to Myth II's finer grid), markers and map actions</td></tr>
<tr><th>Units</th><td>monsters, units, and each monster's own &ldquo;object&rdquo; (its size, health and damage resistances)</td></tr>
<tr><th>Combat</th><td>projectiles, artifacts, mesh effects (explosion ripples)</td></tr>
<tr><th>World</th><td>scenery, weather (rain/snow), lighting, sprite art</td></tr>
<tr><th>Text</th><td>level names, captions, subtitles</td></tr>
</table>

<h2>What we learned along the way</h2>
<ul>
<li><strong>Why units were invisible at first.</strong> In TFL a monster's size, health and damage resistances live on the monster. Myth II moved them into a separate &ldquo;object&rdquo; tag, which TFL shares between every monster. Read by Myth II, TFL's object says &ldquo;size 0&rdquo;, so every unit and tree was there &mdash; you could hear them fight and see their shadows &mdash; but drawn at zero size. Each monster now gets its own object, which is what Project Magma did by hand.</li>
<li><strong>Myth II halved the world unit</strong>, as the Fear manual warns. It shows up in places &mdash; a ground ripple's height doubles &mdash; but not everywhere: unit speeds and ranges did not need doubling.</li>
<li><strong>Building footprints need conversion.</strong> TFL stores each building's footprint in terrain cells, and Myth II's cells are half the size, so footprints have to be split 2&times;2. That's measured against the original TFL tags; converting it is next on the list.</li>
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

<h2>Try it and report what happens</h2>
<p>Follow the <a href="../index.html#get-started">download, setup and play instructions</a> on the front page. Report the plugin, level, Myth II version and relevant log lines in the comment box below. No account is needed.</p>
""",
    },
]

QUESTIONS = [
    {
        "n": 1,
        "term": "Q1: Which TFL content matters most?",
        "title": "Which TFL content matters most to you?",
        "body": "<p>The original campaign? Specific community plugins? Multiplayer maps or single-player? Suggest a plugin and level, and explain what makes it a useful test.</p>",
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
        "body": "<p>Coop scoring and map actions need play-testing. We've converted the map-action format, but we don't yet know whether TFL and Myth II scripts <em>mean</em> the same thing in play. A map whose correct behaviour you know would tell us.</p>",
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
        "title": "Help test converted levels",
        "body": "<p>A converted level played by someone who knows TFL well would find the subtle problems &mdash; wrong unit sizes, sounds, balance &mdash; that logs can't.</p>",
    },
    {
        "n": 6,
        "term": "Q6: What does done look like?",
        "title": "What should a successful conversion preserve?",
        "body": "<p>Which behaviours must match TFL before a conversion feels complete: movement, combat balance, scenery, scripted objectives or something else? Describe a specific level and a way to check it.</p>",
    },
]

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
.btn{display:inline-block;flex:none;padding:.45rem .8rem;border:1px solid var(--blood);border-radius:4px;color:var(--fg);background:var(--tint);font-size:.75rem;text-transform:uppercase;letter-spacing:.12em;text-decoration:none;white-space:nowrap}
.card a:hover .btn,.btn:hover{background:var(--blood);border-color:var(--blood-hi)}
@media (max-width:520px){.card a{flex-direction:column;align-items:flex-start}}
code,pre{font:.82rem/1.5 ui-monospace,Consolas,monospace;background:var(--code);border-radius:4px}
code{padding:.1rem .3rem}
pre{padding:.9rem 1rem;overflow-x:auto;border:1px solid var(--line)}
pre code{background:none;padding:0}
table{border-collapse:collapse;width:100%;margin:.5rem 0}
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
.comment .text{margin:.3rem 0 .4rem;white-space:pre-wrap}
.comment.sub{margin-left:1.4rem;padding:.6rem 0 .2rem;border-top:1px dashed var(--line)}
footer{max-width:50rem;margin:0 auto;padding:1.5rem 1.25rem 3rem;color:var(--muted);font-size:.82rem;border-top:1px solid var(--line)}
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
<section class="reply" id="answer" data-term="{term}" data-api="{api}">
<h2>&#9998; Your answer</h2>
<p class="meta">No sign-up, no account &mdash; just type and press <strong>Send</strong>.</p>
<form class="say" novalidate>
<p class="replying" hidden></p>
<label>Your name<input name="name" autocomplete="nickname" maxlength="40" required></label>
<label>Your message<textarea name="message" rows="6" maxlength="4000" required placeholder="Type here..."></textarea></label>
<label><span class="q">A quick Myth question, so we know you're not a robot:</span><input name="answer" autocomplete="off" required></label>
<label class="trap" aria-hidden="true">Leave this empty<input name="website" tabindex="-1" autocomplete="off"></label>
<p><button class="btn send" type="submit">Send &rarr;</button> <span class="status" role="status"></span></p>
</form>
<h2 class="convo">The conversation so far</h2>
<div class="thread"><p class="meta">Loading&hellip;</p></div>
</section>"""

COMMENTS_JS = """
(function(){
  var box=document.getElementById("answer"); if(!box) return;
  var api=box.dataset.api, term=box.dataset.term, form=box.querySelector("form");
  var list=box.querySelector(".thread"), status=form.querySelector(".status");
  var replying=form.querySelector(".replying"), replyTo=null, send=form.querySelector(".send");
  try{var saved=localStorage.getItem("name"); if(saved) form.name.value=saved;}catch(e){}
  function el(tag,cls,text){var e=document.createElement(tag); if(cls)e.className=cls; if(text!=null)e.textContent=text; return e;}
  function when(at){try{return new Date(at).toLocaleDateString(undefined,{day:"numeric",month:"short",year:"numeric"});}catch(e){return "";}}
  function reply(c){replyTo=c.id; replying.hidden=false; replying.textContent="";
    replying.append("Replying to "+c.name+" ");
    var x=el("button","link","(cancel)"); x.type="button";
    x.onclick=function(){replyTo=null; replying.hidden=true;}; replying.append(x);
    form.message.focus(); form.scrollIntoView({behavior:"smooth",block:"start"});}
  function item(c,top){var a=el("article","comment"+(top?"":" sub"));
    var h=el("p","who"); h.append(el("strong",null,c.name)); h.append(" \u00b7 "+when(c.at)); a.append(h);
    a.append(el("p","text",c.text));
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
    fetch(api+"/comments",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({term:term,page:location.href.split("#")[0],name:form.name.value,message:form.message.value,
        answer:form.answer.value,website:form.website.value,replyTo:replyTo})})
    .then(function(r){return r.json().then(function(d){return {ok:r.ok,d:d};});})
    .then(function(x){if(!x.ok){status.textContent=x.d.error||"That didn't go through \u2014 please try again.";return;}
      render(x.d.comments||[]); form.message.value=""; replyTo=null; replying.hidden=true;
      status.textContent="Sent \u2014 thank you!";})
    .catch(function(){status.textContent="That didn't go through \u2014 please try again.";})
    .then(function(){send.disabled=false;});
  });
})();
"""

CREDIT = (
    "Artwork: <em>Myth II: Soulblighter</em> desktop picture and <em>Myth: The Fallen Lords</em> "
    "box art, &copy; Bungie / Take-Two, shown in black and white. Screenshot from our own testing. "
    "An unofficial, non-commercial fan project."
)


# Browsers keep style.css for 10 minutes (GitHub Pages' max-age); a version
# tag tied to its contents makes a changed stylesheet load at once.
STYLE_VERSION = __import__("hashlib").sha1(STYLE.encode()).hexdigest()[:8]


def page(title, heading, body, depth, term=None, kicker="", subtitle=""):
    up = "../" * depth
    answer = scripts = ""
    if term:
        answer = GIVE_ANSWER.format(term=html.escape(term), api=html.escape(COMMENTS_API))
        scripts = f"<script>{COMMENTS_JS}</script>"
    kicker_html = f'<p class="meta">{kicker}</p>' if kicker else ""
    subtitle_html = f'<p class="subtitle">{subtitle}</p>' if subtitle else ""
    brand = "" if depth == 0 else f'<a class="brand" href="{up}index.html">{SITE_NAME} &middot; {SITE_TAGLINE}</a>'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{html.escape(title)} &middot; {SITE_NAME}</title>
<script>try{{if(localStorage.getItem("theme")==="dark")document.documentElement.dataset.theme="dark"}}catch(e){{}}</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700&family=IM+Fell+English:ital@0;1&display=swap">
<link rel="stylesheet" href="{up}style.css?v={STYLE_VERSION}">
</head>
<body>
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
<main class="wrap">
{body}
{answer}
</main>
<footer>{CREDIT}</footer>
<script>{THEME_JS}</script>
{scripts}
</body>
</html>
"""


def build():
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
    questions = "\n".join(card(f'q/{q["n"]}.html', f'Q{q["n"]}', q["title"]) for q in QUESTIONS)
    index = f"""<section aria-labelledby="news">
<h2 id="news" style="margin-top:0">News</h2>
<h3>Ready-made download: <em>Sir Mauriac's Tale</em></h3>
<p>Skip the setup and play a plugin that is already converted. <em>Sir Mauriac's Tale</em> is a Fallen Lords campaign by CbC (the Crow's Bridge Cartographers), converted for Myth II 1.8.5 by Edulus, the co-creator of this plugin (with Keep and Claude). Nothing else to install: the Fallen Lords tags it relies on are inside the plugin.</p>
<p><a class="btn" href="{DOWNLOAD_URL}">&darr; Download ({DOWNLOAD_MB} MB)</a></p>
<ul>
<li><strong>Beta.</strong> <em>Tandem</em> and <em>In the Name of Glory</em> have been played to the end-game screen; the other levels are untested. This exact download has been checked on a plain Myth II 1.8.5 install, with no other plugins, loading and playing <em>Tandem</em>.</li>
<li>Quit Myth II and extract the zip <strong>straight into</strong> Myth II's <code>plugins</code> folder, not a subfolder (Myth II only finds plugins sitting directly in it). You get the plugin <code>ZZ Mauriac TFL2SB</code> plus a read-me and CbC's credits. Then choose <strong>New Game</strong> &rarr; the campaign <em>ZZ Mauriac TFL2SB</em> &rarr; a level. Leave Tagsets empty.</li>
</ul>
</section>
<section aria-labelledby="get-started">
<h2 id="get-started">Get started &mdash; public beta</h2>
<p>Convert a <em>Myth: The Fallen Lords</em> plugin for <em>Myth II: Soulblighter</em>. Start with the command-line steps below; no Python packages need installing.</p>
<p><strong>You need:</strong> Myth II 1.8.5, Python 3.12 or later, a TFL plugin (<code>.gor</code>), and your own TFL game's <code>tags</code> folder containing <code>TAGS.GOR</code> and <code>ARTSOUND.GOR</code>. Game files are not included.</p>
<ol>
<li><strong>Download and unzip.</strong> Open <a href="{REPO_URL}">the repository</a> and choose <strong>Code &rarr; Download ZIP</strong>, then extract it. There is no packaged release yet. With Git, you can instead run:
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
<h3>Before you test</h3>
<ul>
<li>Quit Myth II before converting or replacing plugin files; the game holds them open. Restart after adding files.</li>
<li>Keep output filenames at most 32 characters. The internal plugin name defaults to that filename; use distinct names so plugins do not hide each other.</li>
<li>The stock tagset replaces same-ID Myth II tags while active. Activate it only for converted TFL levels.</li>
<li>Only one campaign can load at a time. The stock tagset contains no selectable levels, so it can load alongside your converted campaign.</li>
<li>If writing to the install folder fails, write to a folder you can access and copy the finished files into Myth II's <code>plugins</code> folder while the game is closed.</li>
</ul>
<p><strong>Optional guided app:</strong> run <code>python -m src studio</code> or double-click <code>launch.bat</code>. It can preview and convert an individual plugin and read the game log. Build the stock tagset with the command above first. Its missing-reference suggestions are not a check against the complete stock tagset; the command-line route above is the tested starting point.</p>
</section>
<h2>What works &mdash; and what needs testing</h2>
<p><strong>Two levels have reached the end-game screen in Myth II 1.8.5:</strong> <em>Tandem</em> and <em>In the Name of Glory</em> from <em>Sir Mauriac's Tale</em>. This is a beta, not a claim that every TFL plugin works.</p>
<ul>
<li>Converts terrain, markers, map actions, monsters and units, objects, projectiles, artifacts, scenery, weather, mesh effects, lighting, sprite collections and text.</li>
<li>Building models (<code>mode</code>/<code>geom</code>) are measured but not converted. Lighting uses standard values for every map. Terrain cells are duplicated into a finer grid, which can look blocky.</li>
<li>Sounds, collection references, projectile groups and other unsupported bodies are copied unchanged and reported. Other levels and multiplayer remain unverified.</li>
</ul>
<h2>Help test or report a problem</h2>
<p>Every visitor can help. Try a level you know and report what differs from TFL. Open a question or progress update below and use its comment box: a name, message and one-word Myth check &mdash; <strong>no account or sign-in</strong>.</p>
<p>Include the plugin and level names, Myth II version, what you expected, what happened, and the final lines of <code>myth_log.txt</code> from the Myth II folder. For a crash, include relevant lines from the newest <code>myth_crashlog- &lt;date&gt;.txt</code>. Check that the log lists both your campaign and stock tagset after <code>Starting mesh</code>. Share logs and observations, not game files; remove private paths if needed.</p>
<p>Code contributions are welcome through <a href="{REPO_URL}">GitHub</a>; the <a href="{REPO_URL}/blob/main/README.md">README</a> and <a href="{REPO_URL}/blob/main/NOTES.md">format notes</a> describe current support and research.</p>
<h2>Open questions for testers</h2>
<ul class="cards">{questions}</ul>
<h2>Progress log</h2>
<ul class="cards">{updates}</ul>
<h2>About, credits and licence</h2>
<p>Built on <a href="https://github.com/jwheare/mythextract">mythextract</a>, MIT licence, &copy; 2025 James Wheare. The converter's code is <a href="{REPO_URL}/blob/main/LICENSE">MIT-licensed</a>; see <a href="{REPO_URL}/blob/main/NOTICE">NOTICE</a> for prior art.</p>
<p>Myth: The Fallen Lords and Myth II: Soulblighter are trademarks of their respective rights holders. This is an unofficial, non-commercial interoperability tool, not affiliated with or endorsed by any rights holder. No game data is distributed; users supply their own copies.</p>"""
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

    for i, q in enumerate(QUESTIONS):
        prev = (
            f'<a href="{QUESTIONS[i - 1]["n"]}.html">&larr; Q{QUESTIONS[i - 1]["n"]}</a>'
            if i else '<a href="../index.html">&larr; All updates and questions</a>'
        )
        nxt = (
            f'<a href="{QUESTIONS[i + 1]["n"]}.html">Q{QUESTIONS[i + 1]["n"]} &rarr;</a>'
            if i + 1 < len(QUESTIONS) else '<a href="../index.html">All updates and questions &rarr;</a>'
        )
        body = f"""{q["body"]}
<p class="answer-top"><a class="btn" href="#answer">&#9998; Answer this &darr;</a></p>
<div class="nav">{prev}{nxt}</div>"""
        (OUT / "q" / f'{q["n"]}.html').write_text(
            page(f'Q{q["n"]}', f'Q{q["n"]}. {q["title"]}', body, 1, q["term"],
                 kicker=f'Question {q["n"]} of {len(QUESTIONS)}'),
            encoding="utf-8",
        )

    print(f"built {len(UPDATES)} update(s) and {len(QUESTIONS)} question(s) into {OUT}")


if __name__ == "__main__":
    build()
