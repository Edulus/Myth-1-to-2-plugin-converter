// The "Swap Civil War units" page: takes the visitor's own files (Civil War maps,
// its tagset, their Myth II folder), hands them to the worker (worker.js), shows
// what the maps place, lets them choose replacements, and offers the new plugin
// to save. Nothing is uploaded; the files are read in place by this browser tab.
(function () {
  var box = document.getElementById("swapper");
  var $ = function (id) { return document.getElementById(id); };
  var worker = null, busy = false, lastUrl = null;
  var state = { data: null, picks: {} };   // picks: unit id -> replacement id

  function el(tag, text, cls) {
    var e = document.createElement(tag);
    if (text != null) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  }
  function mb(n) { return (n / 1048576).toFixed(n >= 104857600 ? 0 : 1) + " MB"; }
  function show(node, children) {
    node.textContent = "";
    children.forEach(function (c) { node.append(c); });
    node.hidden = false;
  }

  // ---- the three file pickers ----
  function names(list) { return Array.prototype.map.call(list, function (f) { return f.name; }).join(", "); }
  function note(id, text) { $(id).textContent = text; }
  $("maps").addEventListener("change", function () {
    var f = $("maps").files[0];
    note("maps-note", f ? f.name + " (" + mb(f.size) + ")" : "");
    ready();
  });
  $("tagset").addEventListener("change", function () {
    note("tagset-note", $("tagset").files.length ? names($("tagset").files) : "");
    ready();
  });
  $("myth").addEventListener("change", function () {
    var n = $("myth").files.length;
    note("myth-note", n ? "folder chosen (" + n + " files inside)" : "");
    ready();
  });
  function ready() {
    $("read").disabled = busy || !($("maps").files.length && $("tagset").files.length && $("myth").files.length);
  }

  // ---- talking to the worker ----
  var STAGES = {
    engine: "Starting the swapper. The first time takes a little while.",
    read: "Reading your files. Large plugins take a few seconds.",
  };
  function setStage(msg) {
    $("progress").hidden = false;
    if (msg.stage === "write") {
      $("stage").textContent = "Writing the new plugin: " + mb(msg.done) + " so far.";
    } else {
      $("stage").textContent = STAGES[msg.stage] || "Working.";
    }
    $("bar").removeAttribute("value");
  }
  function problemBox(message, details) {
    var parts = [el("p", message)];
    if (details) {
      var d = el("details");
      d.append(el("summary", "Technical details (for bug reports)"), el("pre", details));
      parts.push(d);
    }
    show($("problem"), parts);
  }
  function startWorker() {
    if (worker) return;
    worker = new Worker(box.dataset.worker);
    worker.onmessage = function (ev) {
      var msg = ev.data;
      if (msg.type === "stage") { setStage(msg); return; }
      busy = false;
      $("progress").hidden = true;
      ready();
      refresh();
      if (msg.type === "scanned") scanned(msg.result);
      else if (msg.type === "done") finished(msg.result, msg.blob);
      else problemBox(msg.message, msg.details);
    };
    worker.onerror = function () {
      busy = false; worker.terminate(); worker = null;
      $("progress").hidden = true; ready(); refresh();
      problemBox("The swapper stopped unexpectedly, perhaps for lack of memory. Close other tabs and try again.");
    };
  }

  if (!window.Worker || !window.WebAssembly) {
    show($("problem"), [el("p", "This browser can't run the swapper. Try a recent Chrome, Edge or Firefox on a computer.")]);
    $("read").disabled = true;
    return;
  }

  // ---- step 1: read the maps ----
  $("read").addEventListener("click", function () {
    if (busy) return;
    busy = true; $("read").disabled = true;
    $("problem").hidden = true; $("result").hidden = true; $("choose").hidden = true;
    var myth = [];
    Array.prototype.forEach.call($("myth").files, function (f) {
      var rel = f.webkitRelativePath || f.name;
      var path = rel.split("/").slice(1).join("/");
      // Only the base game's archives matter; the worker keeps the exact ones.
      if (/^tags\//.test(path) || /^plugins\/Patch /.test(path)) myth.push({ path: path, file: f });
    });
    startWorker();
    setStage({ stage: "engine" });
    worker.postMessage({
      type: "scan", code: box.dataset.code,
      maps: $("maps").files[0], tagsets: Array.prototype.slice.call($("tagset").files), myth: myth,
    });
  });

  // ---- step 2: choose replacements ----
  function option(value, text, selected) {
    var o = el("option", text); o.value = value; if (selected) o.selected = true; return o;
  }
  function fillChoices(select, selected) {
    var c = state.data.choices;
    select.textContent = "";
    select.append(option("", "Keep as it is", !selected));
    var stock = el("optgroup"); stock.label = "Real Myth II units";
    c.stock.forEach(function (u) {
      stock.append(option(u.id, (u.name || u.id) + " (" + u.id + ")" + (u.restored ? " - restored" : ""), u.id === selected));
    });
    select.append(stock);
    if (c.tagset.length) {
      var own = el("optgroup"); own.label = "Other units in the tagset";
      c.tagset.forEach(function (u) { own.append(option(u.id, (u.name || u.id) + " (" + u.id + ")", u.id === selected)); });
      select.append(own);
    }
  }
  function scanned(data) {
    state.data = data; state.picks = {};
    var sides = data.units.filter(function (u) { return u.side === "@" || u.side === "+"; }).length;
    $("summary").textContent = "Read " + data.name + ": " + data.maps + " maps place " + data.units.length +
      " kinds of unit; " + sides + " are side units.";
    ["@", "+"].forEach(function (s) { fillChoices($("bulk-" + s), ""); });
    $("choose").hidden = false;
    renderRows();
    $("choose").scrollIntoView({ behavior: "smooth" });
  }
  function renderRows() {
    var only = $("only-sides").checked;
    var rows = $("rows"); rows.textContent = "";
    var units = state.data.units.filter(function (u) { return !only || u.side === "@" || u.side === "+"; });
    if (!units.length) {
      var empty = el("tr"), cell0 = el("td", "No units to show."); cell0.colSpan = 3; empty.append(cell0); rows.append(empty);
    }
    units.forEach(function (u) {
      var tr = el("tr", null, state.picks[u.id] ? "set" : ""); tr.dataset.id = u.id;
      var name = el("td"); name.append(el("b", u.name || "(unnamed)"), document.createTextNode(" "), el("code", u.id));
      var count = el("td", String(u.maps));
      var cell = el("td"), sel = el("select"); sel.setAttribute("aria-label", "Replace " + (u.name || u.id) + " with");
      fillChoices(sel, state.picks[u.id] || "");
      sel.addEventListener("change", function () { setPick(u.id, sel.value, tr); });
      cell.append(sel); tr.append(name, count, cell); rows.append(tr);
    });
    refresh();
  }
  function setPick(id, value, tr) {
    if (value) state.picks[id] = value; else delete state.picks[id];
    tr.className = value ? "set" : "";
    refresh();
  }
  function refresh() {
    var n = Object.keys(state.picks).length;
    var b = $("build");
    b.disabled = busy || n === 0;
    b.textContent = n ? "Write the new plugin (" + n + " unit" + (n === 1 ? "" : "s") + " swapped)" : "Write the new plugin";
  }
  $("only-sides").addEventListener("change", function () { if (state.data) renderRows(); });
  $("clear-all").addEventListener("click", function () { state.picks = {}; renderRows(); });
  $("apply-bulk").addEventListener("click", function () {
    ["@", "+"].forEach(function (side) {
      var value = $("bulk-" + side).value;
      if (!value) return;
      state.data.units.forEach(function (u) { if (u.side === side) state.picks[u.id] = value; });
    });
    renderRows();
  });

  // ---- step 3: write the plugin ----
  $("build").addEventListener("click", function () {
    if (busy) return;
    var name = $("outname").value.trim();
    if (!name) { problemBox("Give the new plugin a name."); return; }
    busy = true; refresh(); $("read").disabled = true;
    $("problem").hidden = true; $("result").hidden = true;
    setStage({ stage: "write", done: 0 });
    worker.postMessage({ type: "build", swaps: state.picks, name: name });
  });

  function finished(res, blob) {
    if (lastUrl) URL.revokeObjectURL(lastUrl);
    lastUrl = URL.createObjectURL(blob);
    var save = el("a", "↓ Save " + res.filename + " (" + mb(res.bytes) + ")", "btn save");
    save.href = lastUrl; save.download = res.filename;
    var p = el("p"); p.append(save);
    var s = res.swapped === 1 ? "1 unit" : res.swapped + " units";
    var summary = el("p", s + " swapped across " + res.maps + " maps (" + res.slots + " places)" +
      (res.restored ? "; " + res.restored + " original Myth II tag" + (res.restored === 1 ? "" : "s") + " restored inside it" : "") + ".");
    var steps = el("ol");
    [
      "Quit Myth II if it is running.",
      "Move the saved file straight into Myth II's plugins folder, next to your Civil War files. Not into a folder inside it.",
      "Keep the name as it is, with no ending such as .gor. If your browser added one (for example .bin), remove it.",
      "Start Myth II, choose New Game, pick the campaign “" + res.filename + "” first, then click Tagsets and activate the Civil War tagset. The new plugin has to load after the tagset.",
    ].forEach(function (t) { steps.append(el("li", t)); });
    var tell = el("p", "How did it go? Tell us in ", "meta");
    var a9 = el("a", "Q9: Tried converting a map of your own?"); a9.href = "../q/9.html";
    var a7 = el("a", "Q7: feature and bug reports"); a7.href = "../q/7.html";
    tell.append(a9, ", or report a problem in ", a7, ".");
    show($("result"), [el("h3", "Done"), p, summary, el("h3", "Put it in Myth II"), steps, tell]);
    $("result").scrollIntoView({ behavior: "smooth" });
  }

  ready();
})();
