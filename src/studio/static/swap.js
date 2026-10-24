/* Swap-units page. Holds no domain knowledge: every unit, name and count comes
   from src/studio/swapping.py. */

const TOKEN = new URLSearchParams(location.search).get("token") || "";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const bytes = (n) => n >= 1048576 ? (n / 1048576).toFixed(1) + " MB"
                   : n >= 1024 ? (n / 1024).toFixed(0) + " KB" : n + " B";

const state = { data: null, picks: {} };   // picks: unit id -> replacement id

async function api(path, body) {
  const url = path + (path.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(TOKEN);
  const res = await fetch(url, body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Studio-Token": TOKEN },
    body: JSON.stringify(body)
  });
  const data = await res.json().catch(() => ({ error: "The server sent something unreadable." }));
  if (!res.ok) throw new Error(data.error || "Request failed.");
  return data;
}
function toast(message, isError) {
  const t = $("toast");
  t.textContent = message;
  t.className = "toast" + (isError ? " err" : "");
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.hidden = true; }, 4200);
}

$("back").href = "/?token=" + encodeURIComponent(TOKEN);

/* ---------- replacement menu ---------- */
function choiceOptions(selected) {
  const c = state.data.choices;
  const opt = (u, tail) =>
    `<option value="${esc(u.id)}"${u.id === selected ? " selected" : ""}>${esc(u.name || u.id)} (${esc(u.id)})${tail}</option>`;
  return `<option value="">Keep as it is</option>`
    + `<optgroup label="Real Myth II units">${c.stock.map((u) => opt(u, u.restored ? " - restored" : "")).join("")}</optgroup>`
    + `<optgroup label="Other units in the tagset">${c.tagset.map((u) => opt(u, "")).join("")}</optgroup>`;
}

/* ---------- table ---------- */
function visibleUnits() {
  const onlySides = $("only-sides").checked;
  return state.data.units.filter((u) => !onlySides || u.side === "@" || u.side === "+");
}
function renderRows() {
  $("rows").innerHTML = visibleUnits().map((u) =>
    `<tr data-id="${esc(u.id)}" class="${state.picks[u.id] ? "set" : ""}">
       <td><b>${esc(u.name || "(unnamed)")}</b> <code>${esc(u.id)}</code></td>
       <td class="mono">${u.maps}</td>
       <td><select data-id="${esc(u.id)}">${choiceOptions(state.picks[u.id] || "")}</select></td>
     </tr>`).join("") || `<tr><td colspan="3" class="hint">No units to show.</td></tr>`;
  document.querySelectorAll("#rows select").forEach((sel) => {
    sel.addEventListener("change", () => setPick(sel.dataset.id, sel.value));
  });
  refresh();
}
function setPick(id, value) {
  if (value) state.picks[id] = value; else delete state.picks[id];
  const row = document.querySelector(`#rows tr[data-id="${CSS.escape(id)}"]`);
  if (row) row.classList.toggle("set", !!value);
  refresh();
}
function refresh() {
  const n = Object.keys(state.picks).length;
  $("build").disabled = n === 0;
  $("build").textContent = n ? `Write the new plugin (${n} unit${n === 1 ? "" : "s"} swapped)` : "Write the new plugin";
}

/* ---------- opening ---------- */
async function loadSuggestions() {
  try {
    const { paths } = await api("/api/suggest-install");
    $("suggest").innerHTML = paths.length
      ? `<span class="hint">Found:</span> ` + paths.map((p) => `<button class="ghost" data-p="${esc(p)}">${esc(p)}</button>`).join("")
      : "";
    $("suggest").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      $("myth2").value = b.dataset.p;
    }));
  } catch (e) { /* suggestions are a convenience */ }
}

$("open").addEventListener("click", async () => {
  const result = $("open-result");
  result.className = "result"; result.textContent = "Reading... large files take a few seconds.";
  $("open").disabled = true;
  try {
    const data = await api("/api/swap/open", {
      mapsPath: $("maps").value.trim(),
      tagsetPaths: $("tagsets").value.split("\n").map((s) => s.trim()).filter(Boolean),
      myth2Dir: $("myth2").value.trim()
    });
    state.data = data; state.picks = {};
    const sides = data.units.filter((u) => u.side === "@" || u.side === "+").length;
    result.className = "result"; result.innerHTML = `<span class="ok">Read ${esc(data.name)}.</span>`;
    $("summary").textContent =
      `${data.maps} maps place ${data.units.length} kinds of unit; ${sides} are side units.`;
    for (const side of ["@", "+"]) $("bulk-" + side).innerHTML = choiceOptions("");
    $("s-choose").hidden = false;
    renderRows();
    $("s-choose").scrollIntoView({ behavior: "smooth" });
  } catch (e) {
    result.className = "result err"; result.textContent = e.message;
  } finally { $("open").disabled = false; }
});

$("only-sides").addEventListener("change", renderRows);
$("clear-all").addEventListener("click", () => { state.picks = {}; renderRows(); });
$("apply-bulk").addEventListener("click", () => {
  for (const side of ["@", "+"]) {
    const value = $("bulk-" + side).value;
    if (!value) continue;
    for (const u of state.data.units) if (u.side === side) state.picks[u.id] = value;
  }
  renderRows();
});

/* ---------- writing ---------- */
$("build").addEventListener("click", async () => {
  const result = $("build-result");
  const name = $("outname").value.trim();
  if (!name) { toast("Give the new plugin a name.", true); return; }
  const maps = $("maps").value.trim();
  const sep = maps.includes("\\") ? "\\" : "/";
  const out = maps.slice(0, maps.lastIndexOf(sep) + 1) + name;
  result.className = "result"; result.textContent = "Writing...";
  $("build").disabled = true;
  try {
    const r = await api("/api/swap/build", { swaps: state.picks, outPath: out, pluginName: name });
    result.className = "result";
    result.innerHTML = `<span class="ok">Wrote ${esc(r.path)}</span> (${bytes(r.bytes)}). `
      + `${r.swapped} unit${r.swapped === 1 ? "" : "s"} swapped across ${r.maps} maps`
      + (r.restored ? `; ${r.restored} original unit${r.restored === 1 ? "" : "s"} restored` : "")
      + `. In Myth II choose the campaign first, then activate the tagset.`
      + (r.filenameTooLong ? ` <b>The name is ${r.filenameLength} characters; Myth II ignores plugins over 32.</b>` : "");
  } catch (e) {
    result.className = "result err"; result.textContent = e.message;
  } finally { refresh(); }
});

loadSuggestions();
