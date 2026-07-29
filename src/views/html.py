"""Interactive page view of a conversion plan.

Shows what the converter would do, collects the decisions it cannot make, and
emits the `decisions.toml` that feeds back into ``convert --decisions``. That
closes the loop: the page is the view *and* the control surface, and its output
is an input to the model.

Self-contained by construction -- one file, no network, no build step, opens
from disk or publishes as a page.
"""

import html as html_escape
import json

from .. import codec


def _tag_rows(plan):
    return [
        {
            "type": codec.decode_string(o.tag_type),
            "id": codec.decode_string(o.tfl_id),
            "newId": codec.decode_string(o.sb_id),
            "name": o.name,
            "status": o.status,
            "before": o.size_before,
            "after": o.size_after,
            "warnings": o.warnings,
        }
        for o in plan.outcomes
    ]


def _plan_data(plan):
    return {
        "source": plan.source,
        "summary": plan.summary(),
        "ready": plan.is_ready(),
        # Total vs still-open matter differently: a reference mapped onto a tag
        # that lives in the Myth II install is settled even though it is still
        # listed here, so the UI must count `undecided`, not `unresolved`.
        "undecided": len(plan.undecided()),
        "needsReview": len(plan.needs_review()),
        "options": plan.options,
        "decisionsPath": plan.decisions_path,
        "unresolved": [
            {
                "type": codec.decode_string(u.tag_type),
                "id": codec.decode_string(u.tag_id),
                "refs": u.references,
                "decided": codec.decode_string(u.decided) if u.decided else "",
                "candidates": [
                    {"id": c[0], "name": str(c[1]), "archives": c[2]}
                    for c in u.candidates[:40]
                ],
            }
            for u in plan.unresolved
        ],
        "synthesised": [
            {
                "name": s.name,
                "value": s.value,
                "agreed": s.agreed,
                "confidence": s.confidence,
                "overridden": s.overridden,
            }
            for s in plan.synthesised
        ],
        "tags": _tag_rows(plan),
        "byType": {
            codec.decode_string(t): counts for t, counts in plan.by_tag_type().items()
        },
        "levels": [
            {
                "id": codec.decode_string(r.entry_id),
                "name": codec.decode_string(r.entry_long_name),
            }
            for r in plan.entrypoints
        ],
        "warnings": plan.warnings,
    }


def render(plan, title=None):
    """Return a complete, self-contained HTML page for ``plan``."""
    # Tag names come from someone else's plugin, so treat them as untrusted.
    # JSON escaping alone is not enough inside a <script> element: a name
    # containing "</script>" would close the element and the rest would be
    # parsed as markup. Escaping the three characters that can start a tag or an
    # entity is valid JSON, valid JS, and closes that hole.
    data = json.dumps(_plan_data(plan), indent=None, ensure_ascii=False)
    for char, escaped in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026")):
        data = data.replace(char, escaped)
    heading = html_escape.escape(title or "Conversion plan")
    source = html_escape.escape(plan.source.rsplit("\\", 1)[-1].rsplit("/", 1)[-1])
    return _TEMPLATE.replace("__PLAN_JSON__", data).replace(
        "__TITLE__", heading
    ).replace("__SOURCE__", source)


_TEMPLATE = r"""<title>__TITLE__ &mdash; myth-plugin-converter</title>
<style>
  :root {
    --ground:  #eff1ee;
    --surface: #ffffff;
    --raised:  #f7f8f6;
    --ink:     #19211e;
    --muted:   #5b6763;
    --faint:   #8a9591;
    --rule:    #d6dbd7;
    --patina:  #2c6c61;
    --patina-soft: #e2eeea;
    --ok:      #4c7b40;
    --ok-soft: #e6efe1;
    --warn:    #8f6412;
    --warn-soft: #f6eddb;
    --crit:    #9e4230;
    --crit-soft: #f7e6e1;
    --shadow: 0 1px 2px rgba(25,33,30,.06), 0 8px 24px -12px rgba(25,33,30,.18);

    --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --ground:  #121614;
      --surface: #1a201d;
      --raised:  #212825;
      --ink:     #e6eae7;
      --muted:   #9aa5a0;
      --faint:   #6d7975;
      --rule:    #2b3330;
      --patina:  #5fae9e;
      --patina-soft: #1d2f2b;
      --ok:      #82b76d;
      --ok-soft: #1c2a1d;
      --warn:    #d6a43e;
      --warn-soft: #2e2717;
      --crit:    #d97a5e;
      --crit-soft: #2f1d18;
      --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
    }
  }
  :root[data-theme="dark"] {
    --ground:#121614; --surface:#1a201d; --raised:#212825; --ink:#e6eae7;
    --muted:#9aa5a0; --faint:#6d7975; --rule:#2b3330; --patina:#5fae9e;
    --patina-soft:#1d2f2b; --ok:#82b76d; --ok-soft:#1c2a1d; --warn:#d6a43e;
    --warn-soft:#2e2717; --crit:#d97a5e; --crit-soft:#2f1d18;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
  }
  :root[data-theme="light"] {
    --ground:#eff1ee; --surface:#ffffff; --raised:#f7f8f6; --ink:#19211e;
    --muted:#5b6763; --faint:#8a9591; --rule:#d6dbd7; --patina:#2c6c61;
    --patina-soft:#e2eeea; --ok:#4c7b40; --ok-soft:#e6efe1; --warn:#8f6412;
    --warn-soft:#f6eddb; --crit:#9e4230; --crit-soft:#f7e6e1;
    --shadow: 0 1px 2px rgba(25,33,30,.06), 0 8px 24px -12px rgba(25,33,30,.18);
  }

  body { margin:0; background:var(--ground); color:var(--ink);
         font-family:var(--sans); font-size:15px; line-height:1.55;
         -webkit-font-smoothing:antialiased; }
  .wrap { max-width:1120px; margin:0 auto; padding:40px 24px 96px;
          display:flex; flex-direction:column; gap:36px; }

  h1 { font-size:26px; font-weight:640; letter-spacing:-.021em; margin:0;
       text-wrap:balance; }
  h2 { font-size:15px; font-weight:640; letter-spacing:.055em;
       text-transform:uppercase; color:var(--muted); margin:0 0 14px; }
  h3 { font-size:15px; font-weight:620; margin:0; letter-spacing:-.008em; }
  p  { margin:0; color:var(--muted); max-width:66ch; }
  a  { color:var(--patina); }

  .mono { font-family:var(--mono); font-variant-numeric:tabular-nums; }

  header .sub { margin-top:6px; font-size:13.5px; }
  header .sub .mono { color:var(--ink); }

  /* -- status strip -- */
  .status { display:flex; flex-wrap:wrap; align-items:center; gap:10px 18px;
            background:var(--surface); border:1px solid var(--rule);
            border-radius:10px; padding:14px 18px; box-shadow:var(--shadow); }
  .status .verdict { font-weight:640; font-size:13px; letter-spacing:.04em;
                     text-transform:uppercase; padding:4px 10px; border-radius:999px; }
  .verdict.ready { background:var(--ok-soft); color:var(--ok); }
  .verdict.blocked { background:var(--warn-soft); color:var(--warn); }
  .status .stat { display:flex; flex-direction:column; gap:1px; }
  .status .stat b { font-family:var(--mono); font-size:19px; font-weight:600;
                    font-variant-numeric:tabular-nums; letter-spacing:-.01em; }
  .status .stat span { font-size:11.5px; color:var(--faint); letter-spacing:.03em; }
  .status .spacer { flex:1 1 auto; }

  section { background:var(--surface); border:1px solid var(--rule);
            border-radius:10px; padding:22px; box-shadow:var(--shadow); }
  .sechead { display:flex; align-items:baseline; justify-content:space-between;
             gap:16px; margin-bottom:14px; flex-wrap:wrap; }
  .sechead h2 { margin:0; }
  .sechead .note { font-size:13px; color:var(--faint); }

  /* -- decision rows -- */
  .decision { display:grid; grid-template-columns:minmax(0,1fr) 260px;
              gap:12px 20px; align-items:center; padding:13px 0;
              border-top:1px solid var(--rule); }
  .decision:first-of-type { border-top:none; }
  .decision .what { display:flex; flex-direction:column; gap:3px; min-width:0; }
  .decision .id { font-family:var(--mono); font-size:14px; font-weight:600; }
  .decision .why { font-size:12.5px; color:var(--faint); }
  .stripe { border-left:3px solid var(--crit); padding-left:14px; }
  .stripe.resolved { border-left-color:var(--ok); }
  .stripe.warnstripe { border-left-color:var(--warn); }

  select, input[type="text"], input[type="number"] {
    width:100%; font-family:var(--mono); font-size:13px; color:var(--ink);
    background:var(--raised); border:1px solid var(--rule); border-radius:7px;
    padding:7px 9px; }
  select:focus-visible, input:focus-visible, button:focus-visible {
    outline:2px solid var(--patina); outline-offset:1px; }
  label.inline { display:flex; align-items:center; gap:9px; font-size:14px;
                 color:var(--ink); }
  input[type="checkbox"] { width:16px; height:16px; accent-color:var(--patina); }

  /* -- tables -- */
  .scroll { overflow-x:auto; }
  table { width:100%; border-collapse:collapse; font-size:13.5px; }
  th { text-align:left; font-weight:600; font-size:11.5px; letter-spacing:.055em;
       text-transform:uppercase; color:var(--faint); padding:0 12px 8px 0;
       border-bottom:1px solid var(--rule); white-space:nowrap; }
  td { padding:7px 12px 7px 0; border-bottom:1px solid var(--rule);
       vertical-align:top; }
  tr:last-child td { border-bottom:none; }
  td.num { font-family:var(--mono); font-variant-numeric:tabular-nums;
           text-align:right; padding-right:16px; white-space:nowrap; }
  td.id { font-family:var(--mono); white-space:nowrap; }

  .pill { display:inline-block; font-size:11px; font-weight:640; letter-spacing:.04em;
          text-transform:uppercase; padding:2px 8px; border-radius:999px;
          white-space:nowrap; }
  .pill.converted { background:var(--ok-soft); color:var(--ok); }
  .pill.passed { background:var(--warn-soft); color:var(--warn); }
  .pill.unanimous { background:var(--ok-soft); color:var(--ok); }
  .pill.check { background:var(--warn-soft); color:var(--warn); }

  .bars { display:flex; flex-direction:column; gap:7px; }
  .bar { display:grid; grid-template-columns:56px 1fr 118px; gap:12px;
         align-items:center; font-size:13px; }
  .bar .track { height:9px; border-radius:3px; background:var(--rule);
                overflow:hidden; display:flex; }
  .bar .fill-c { background:var(--ok); }
  .bar .fill-p { background:var(--warn); }
  .bar .val { font-family:var(--mono); font-size:12px; color:var(--muted);
              text-align:right; font-variant-numeric:tabular-nums; }

  ul.warn-list { margin:0; padding-left:20px; display:flex; flex-direction:column;
                 gap:7px; font-size:13.5px; color:var(--muted); }
  ul.warn-list li::marker { color:var(--warn); }

  .levels { columns:2; column-gap:28px; font-size:13.5px; }
  .levels div { break-inside:avoid; padding:2px 0; }
  .levels .mono { color:var(--faint); margin-right:9px; }
  @media (max-width:720px) { .levels { columns:1; } }

  /* -- output panel -- */
  .output { position:sticky; bottom:0; z-index:5; }
  .output pre { margin:0; background:var(--raised); border:1px solid var(--rule);
                border-radius:8px; padding:14px 16px; font-family:var(--mono);
                font-size:12.5px; line-height:1.5; max-height:280px;
                overflow:auto; white-space:pre; color:var(--ink); }
  .actions { display:flex; gap:10px; flex-wrap:wrap; margin-top:12px;
             align-items:center; }
  button { font-family:var(--sans); font-size:13.5px; font-weight:600;
           padding:8px 15px; border-radius:7px; cursor:pointer;
           border:1px solid var(--patina); background:var(--patina);
           color:var(--surface); }
  button.ghost { background:transparent; color:var(--patina); }
  button:hover { filter:brightness(1.06); }
  .hint { font-size:12.5px; color:var(--faint); }

  @media (max-width:760px) {
    .decision { grid-template-columns:1fr; }
    .wrap { padding:28px 16px 80px; }
  }
  @media (prefers-reduced-motion:reduce) { * { transition:none !important; } }
</style>

<div class="wrap">
  <header>
    <h1>__TITLE__</h1>
    <p class="sub">What the converter would do to <span class="mono">__SOURCE__</span>,
       before it writes anything. Choose what it cannot, then export the decisions file.</p>
  </header>

  <div class="status" id="status"></div>

  <section id="sec-decisions">
    <div class="sechead">
      <h2>Decisions needed</h2>
      <span class="note">Tags this plugin references but does not contain</span>
    </div>
    <p style="margin-bottom:14px">A TFL plugin is not self-contained &mdash; it references the stock
       TFL tag library the way a Myth II plugin references the base game. Pick a Myth II
       substitute, or leave it blank if you plan to supply the real tag from a converted
       TFL tagset.</p>
    <div id="decisions"></div>
  </section>

  <section id="sec-synth">
    <div class="sechead">
      <h2>Synthesised mesh fields</h2>
      <span class="note">No TFL source &mdash; measured from a reference port</span>
    </div>
    <p style="margin-bottom:14px">TFL meshes have no equivalent of these, so they are invented.
       Values were measured across the 40 meshes of <em>Magma&nbsp;&mdash; The Fallen Lords v1.9</em>.
       Anything short of unanimous is worth your judgement.</p>
    <div id="synth"></div>
  </section>

  <section id="sec-options">
    <div class="sechead"><h2>Options</h2></div>
    <div id="options"></div>
  </section>

  <section id="sec-types">
    <div class="sechead">
      <h2>What happens to each tag type</h2>
      <span class="note" id="types-note"></span>
    </div>
    <div class="bars" id="types"></div>
  </section>

  <section id="sec-levels">
    <div class="sechead">
      <h2>Levels the game will list</h2>
      <span class="note" id="levels-note"></span>
    </div>
    <div class="levels" id="levels"></div>
  </section>

  <section id="sec-tags">
    <div class="sechead">
      <h2>Every tag</h2>
      <span class="note" id="tags-note"></span>
    </div>
    <div class="scroll"><table id="tags"></table></div>
  </section>

  <section id="sec-warn">
    <div class="sechead"><h2>Warnings</h2></div>
    <ul class="warn-list" id="warnings"></ul>
  </section>

  <section class="output">
    <div class="sechead">
      <h2>decisions.toml</h2>
      <span class="note">Feeds back into <span class="mono">convert --decisions</span></span>
    </div>
    <pre id="toml"></pre>
    <div class="actions">
      <button id="download">Download decisions.toml</button>
      <button class="ghost" id="copy">Copy</button>
      <span class="hint" id="copied"></span>
    </div>
  </section>
</div>

<script>
const PLAN = __PLAN_JSON__;
const state = {
  choices: Object.fromEntries(PLAN.unresolved.map(u => [u.type + "." + u.id, u.decided || ""])),
  overrides: {},
  useVtfl: !!PLAN.options.use_vtfl,
  pluginName: PLAN.options.plugin_name || ""
};
PLAN.synthesised.forEach(s => { if (s.overridden) state.overrides[s.name] = s.value; });

const el = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function decidedCount() {
  return Object.values(state.choices).filter(v => v.trim()).length;
}

function renderStatus() {
  const total = PLAN.unresolved.length;
  const left = total - decidedCount();
  const review = PLAN.synthesised.filter(s => s.confidence === "check" && !(s.name in state.overrides)).length;
  const ready = left === 0 && review === 0;
  const s = PLAN.summary;
  el("status").innerHTML =
    `<span class="verdict ${ready ? "ready" : "blocked"}">${ready ? "Ready" : "Needs input"}</span>` +
    stat(s["source tags"], "source tags") +
    stat(s["converted"], "converted") +
    stat(s["passed through"], "passed through") +
    stat(s["entrypoints"], "levels") +
    stat(left, "undecided") +
    stat(review, "to review") +
    `<span class="spacer"></span>`;
}
const stat = (v, l) => `<span class="stat"><b>${v}</b><span>${l}</span></span>`;

function renderDecisions() {
  const host = el("decisions");
  if (!PLAN.unresolved.length) {
    host.innerHTML = `<p>Every referenced tag is present in the plugin. Nothing to decide.</p>`;
    return;
  }
  host.innerHTML = PLAN.unresolved.map(u => {
    const key = u.type + "." + u.id;
    const chosen = state.choices[key] || "";
    const opts = [`<option value="">&mdash; leave unresolved &mdash;</option>`].concat(
      u.candidates.map(c =>
        `<option value="${esc(c.id)}" ${c.id === chosen ? "selected" : ""}>${esc(c.id)} &mdash; ${esc(c.name || "(unnamed)")} (${c.archives})</option>`)
    );
    const custom = chosen && !u.candidates.some(c => c.id === chosen)
      ? `<option value="${esc(chosen)}" selected>${esc(chosen)} &mdash; (typed)</option>` : "";
    const cands = u.candidates.length
      ? `${u.candidates.length} candidate${u.candidates.length === 1 ? "" : "s"} of type ${esc(u.type)} in your install`
      : `no tags of type ${esc(u.type)} found in your install`;
    return `<div class="decision stripe ${chosen ? "resolved" : ""}" data-key="${esc(key)}">
      <div class="what">
        <span class="id">${esc(key)}</span>
        <span class="why">referenced by ${u.refs} mesh${u.refs === 1 ? "" : "es"} &middot; ${cands}</span>
      </div>
      <select data-key="${esc(key)}" aria-label="Substitute for ${esc(key)}">${custom}${opts.join("")}</select>
    </div>`;
  }).join("");
  host.querySelectorAll("select").forEach(sel => {
    sel.addEventListener("change", e => {
      state.choices[e.target.dataset.key] = e.target.value;
      e.target.closest(".decision").classList.toggle("resolved", !!e.target.value);
      renderStatus(); renderToml();
    });
  });
}

function renderSynth() {
  el("synth").innerHTML = PLAN.synthesised.map(s => {
    const overridden = s.name in state.overrides;
    const value = overridden ? state.overrides[s.name] : s.value;
    const pill = s.confidence === "unanimous"
      ? `<span class="pill unanimous">${s.agreed}/40 agreed</span>`
      : s.confidence === "check"
        ? `<span class="pill check">${s.agreed}/40 &mdash; check</span>` : "";
    return `<div class="decision stripe ${s.confidence === "check" && !overridden ? "warnstripe" : "resolved"}">
      <div class="what">
        <span class="id">${esc(s.name)} ${pill}</span>
        <span class="why">${overridden ? "overridden by you" : "measured default"}</span>
      </div>
      <input type="text" class="mono" data-field="${esc(s.name)}" value="${esc(value)}"
             aria-label="Value for ${esc(s.name)}">
    </div>`;
  }).join("");
  el("synth").querySelectorAll("input[data-field]").forEach(inp => {
    inp.addEventListener("input", e => {
      const name = e.target.dataset.field;
      const base = PLAN.synthesised.find(s => s.name === name);
      const raw = e.target.value.trim();
      if (raw === "" || String(base.value) === raw) delete state.overrides[name];
      else state.overrides[name] = raw;
      renderStatus(); renderToml();
    });
  });
}

function renderOptions() {
  el("options").innerHTML =
    `<div class="decision stripe resolved">
       <div class="what">
         <span class="id">use_vtfl</span>
         <span class="why">Puts Myth II into TFL gameplay emulation. Magma &mdash; The Fallen Lords v1.9
           sets this on all 40 of its meshes; DX 1.3 and TFL Multipack set it on none.
           It makes the plugin depend on a vTFL Unity tagset.</span>
       </div>
       <label class="inline"><input type="checkbox" id="vtfl" ${state.useVtfl ? "checked" : ""}> Enable vTFL</label>
     </div>
     <div class="decision stripe resolved">
       <div class="what">
         <span class="id">plugin_name</span>
         <span class="why">Written into the plugin header. Keep the filename under 32 characters
           too &mdash; Myth II silently ignores longer ones.</span>
       </div>
       <input type="text" id="pname" value="${esc(state.pluginName)}" aria-label="Plugin name">
     </div>`;
  el("vtfl").addEventListener("change", e => { state.useVtfl = e.target.checked; renderToml(); });
  el("pname").addEventListener("input", e => { state.pluginName = e.target.value; renderToml(); });
}

function renderTypes() {
  const rows = Object.entries(PLAN.byType);
  const max = Math.max(...rows.map(([, c]) => c.converted + c["passed-through"]), 1);
  el("types-note").textContent = `${rows.length} tag types`;
  el("types").innerHTML = rows.map(([t, c]) => {
    const total = c.converted + c["passed-through"];
    const w = (total / max) * 100;
    const cw = total ? (c.converted / total) * 100 : 0;
    return `<div class="bar">
      <span class="mono">${esc(t)}</span>
      <span class="track" style="width:${w}%">
        <span class="fill-c" style="width:${cw}%"></span>
        <span class="fill-p" style="width:${100 - cw}%"></span>
      </span>
      <span class="val">${c.converted} conv &middot; ${c["passed-through"]} pass</span>
    </div>`;
  }).join("");
}

function renderLevels() {
  el("levels-note").textContent = `${PLAN.levels.length} entrypoints, one per mesh`;
  el("levels").innerHTML = PLAN.levels.map(l =>
    `<div><span class="mono">${esc(l.id)}</span>${esc(l.name)}</div>`).join("");
}

function renderTags() {
  el("tags-note").textContent = `${PLAN.tags.length} tags`;
  const head = `<thead><tr><th>Type</th><th>ID</th><th>Name</th><th>Status</th>
    <th style="text-align:right">Before</th><th style="text-align:right">After</th></tr></thead>`;
  const body = PLAN.tags.map(t => {
    const renamed = t.id !== t.newId ? ` &rarr; <span class="mono">${esc(t.newId)}</span>` : "";
    return `<tr>
      <td class="id">${esc(t.type)}</td>
      <td class="id">${esc(t.id)}${renamed}</td>
      <td>${esc(t.name)}</td>
      <td><span class="pill ${t.status === "converted" ? "converted" : "passed"}">${t.status === "converted" ? "converted" : "pass-through"}</span></td>
      <td class="num">${t.before.toLocaleString()}</td>
      <td class="num">${t.after.toLocaleString()}</td>
    </tr>`;
  }).join("");
  el("tags").innerHTML = head + `<tbody>${body}</tbody>`;
}

function renderWarnings() {
  el("warnings").innerHTML = PLAN.warnings.length
    ? PLAN.warnings.map(w => `<li>${esc(w)}</li>`).join("")
    : `<li>None.</li>`;
}

function tomlString(s) {
  return '"' + String(s).replace(/\\/g, "\\\\").replace(/"/g, '\\"')
    .replace(/\n/g, "\\n").replace(/\r/g, "\\r").replace(/\t/g, "\\t") + '"';
}

function renderToml() {
  const lines = [
    "# myth-plugin-converter decisions",
    "# Exported from the plan view.",
    "#",
    "#   python -m src convert --in <plugin> --out <plugin> --decisions <this file>",
    "",
    "[options]",
    "use_vtfl = " + (state.useVtfl ? "true" : "false"),
    "plugin_name = " + tomlString(state.pluginName),
    ""
  ];

  const decided = PLAN.unresolved.filter(u => (state.choices[u.type + "." + u.id] || "").trim());
  lines.push("# " + "-".repeat(70));
  lines.push(`# Substitutes for tags this plugin references but does not contain`);
  lines.push(`# ${decided.length} of ${PLAN.unresolved.length} decided`);
  lines.push("# " + "-".repeat(70), "");
  PLAN.unresolved.forEach(u => {
    const key = u.type + "." + u.id;
    const chosen = (state.choices[key] || "").trim();
    const cand = u.candidates.find(c => c.id === chosen);
    lines.push(`# ${key} &mdash; referenced by ${u.refs} mesh(es)${cand ? " &rarr; " + cand.name : ""}`);
    lines.push("[[tag]]");
    lines.push("type = " + tomlString(u.type));
    lines.push("id = " + tomlString(u.id));
    lines.push("map_to = " + tomlString(chosen));
    lines.push("");
  });

  const over = Object.entries(state.overrides);
  lines.push("# " + "-".repeat(70));
  lines.push("# Overrides for synthesised mesh fields");
  lines.push("# " + "-".repeat(70), "");
  lines.push("[mesh_defaults]");
  if (over.length) {
    over.forEach(([k, v]) => {
      const num = Number(v);
      lines.push(`${k} = ${Number.isFinite(num) && String(num) === String(v).trim() ? num : tomlString(v)}`);
    });
  } else {
    lines.push("# (none &mdash; using the measured defaults)");
  }
  lines.push("");
  el("toml").textContent = lines.join("\n");
}

el("download").addEventListener("click", () => {
  const blob = new Blob([el("toml").textContent], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "decisions.toml";
  a.click();
  URL.revokeObjectURL(a.href);
});
el("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(el("toml").textContent);
    el("copied").textContent = "Copied.";
  } catch { el("copied").textContent = "Select the text above to copy."; }
  setTimeout(() => { el("copied").textContent = ""; }, 2400);
});

renderStatus(); renderDecisions(); renderSynth(); renderOptions();
renderTypes(); renderLevels(); renderTags(); renderWarnings(); renderToml();
</script>
"""
