// The "Convert a plugin" page: takes the visitor's file, hands it to the worker
// (worker.js), shows progress in plain words, and offers the result to save.
// Nothing is uploaded anywhere.
(function () {
  var box = document.getElementById("converter");
  var pick = document.getElementById("pick");
  var drop = document.getElementById("drop");
  var progress = document.getElementById("progress");
  var stageText = document.getElementById("stage");
  var bar = document.getElementById("bar");
  var problem = document.getElementById("problem");
  var result = document.getElementById("result");
  var worker = null, busy = false, lastUrl = null;

  function el(tag, text, cls) {
    var e = document.createElement(tag);
    if (text != null) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  }
  function mb(n) { return Math.round(n / 1048576) + " MB"; }

  if (!window.Worker || !window.WebAssembly) {
    show(problem, [el("p", "This browser can't run the converter. Try a recent Chrome, Edge or Firefox on a computer.")]);
    pick.disabled = true;
    return;
  }

  var STAGES = {
    engine: "Starting the converter. The first time takes a little while.",
    plugin: "Reading your plugin.",
    convert: "Converting. This can take a minute, and the page may pause.",
  };

  function show(node, children) {
    node.textContent = "";
    children.forEach(function (c) { node.append(c); });
    node.hidden = false;
  }

  function setStage(msg) {
    progress.hidden = false;
    if (msg.stage === "stock") {
      stageText.textContent = "Fetching the original Fallen Lords files from this website: "
        + mb(msg.done) + " of " + mb(msg.total) + ". Next time this comes from your browser's storage.";
      bar.max = msg.total; bar.value = msg.done;
    } else {
      stageText.textContent = STAGES[msg.stage] || "Working.";
      bar.removeAttribute("value");
    }
  }

  function details(text) {
    var d = el("details");
    d.append(el("summary", "Technical details (for bug reports)"));
    d.append(el("pre", text));
    return d;
  }

  function finished(res, data) {
    if (lastUrl) URL.revokeObjectURL(lastUrl);
    lastUrl = URL.createObjectURL(new Blob([data], { type: "application/octet-stream" }));
    var save = el("a", "\u2193 Save " + res.filename + " (" + mb(res.bytes) + ")", "btn save");
    save.href = lastUrl;
    save.download = res.filename;

    var parts = [el("h2", "Done"), el("p"), ];
    parts[1].append(save);

    if (res.levels.length) {
      var count = "Myth II will list " + res.levels.length + " level" + (res.levels.length === 1 ? "" : "s");
      var ul = el("ul");
      res.levels.forEach(function (l) { ul.append(el("li", l)); });
      if (res.levels.length > 10) {
        var fold = el("details");
        fold.append(el("summary", count + " (show them)"));
        fold.append(ul);
        parts.push(fold);
      } else {
        parts.push(el("p", count + ":"));
        parts.push(ul);
      }
    }
    if (res.notes.length) {
      parts.push(el("h3", "Worth knowing"));
      var notes = el("ul");
      res.notes.forEach(function (n) { notes.append(el("li", n)); });
      parts.push(notes);
    }

    parts.push(el("h3", "Put it in Myth II (tested on Windows)"));
    var steps = el("ol");
    [
      "Quit Myth II if it is running.",
      "Move the saved file straight into Myth II's plugins folder, for example C:\\Program Files (x86)\\Myth II\\plugins. Not into a folder inside it: Myth II only looks at files sitting directly in plugins.",
      "Keep the name as it is, with no ending such as .gor. If your browser added one (for example .bin), remove it.",
      "Start Myth II, choose New Game, pick the campaign \u201c" + res.filename + "\u201d, then a level, then OK. Leave Tagsets empty: the original game files it needs are already inside.",
    ].forEach(function (s) { steps.append(el("li", s)); });
    parts.push(steps);
    var tell = el("p", "This is a beta. If a level doesn't load or looks wrong, please tell us in ", "meta");
    var q7 = el("a", "Q7: feature and bug reports");
    q7.href = "../q/7.html";
    tell.append(q7, " and include the technical details below.");
    parts.push(tell);
    parts.push(details(res.details));
    show(result, parts);
  }

  function start(file) {
    if (busy || !file) return;
    busy = true;
    pick.disabled = true;
    problem.hidden = true;
    result.hidden = true;
    if (!worker) {
      worker = new Worker(box.dataset.worker);
      worker.onmessage = function (ev) {
        var msg = ev.data;
        if (msg.type === "stage") { setStage(msg); return; }
        busy = false;
        pick.disabled = false;
        pick.value = "";
        progress.hidden = true;
        if (msg.type === "done") finished(msg.result, msg.data);
        else {
          var parts = [el("p", msg.message)];
          if (msg.details) parts.push(details(msg.details));
          show(problem, parts);
        }
      };
      worker.onerror = function () {
        busy = false; pick.disabled = false; progress.hidden = true;
        worker.terminate(); worker = null;
        show(problem, [el("p", "The converter stopped unexpectedly, perhaps for lack of memory. Close other tabs and try again.")]);
      };
    }
    setStage({ stage: "engine" });
    worker.postMessage({
      type: "convert",
      file: file,
      code: new URL(box.dataset.code, location.href).href,
      manifest: new URL(box.dataset.manifest, location.href).href,
    });
  }

  pick.addEventListener("change", function () { start(pick.files[0]); });
  ["dragenter", "dragover"].forEach(function (t) {
    drop.addEventListener(t, function (e) { e.preventDefault(); drop.classList.add("over"); });
  });
  ["dragleave", "drop"].forEach(function (t) {
    drop.addEventListener(t, function () { drop.classList.remove("over"); });
  });
  drop.addEventListener("drop", function (e) {
    e.preventDefault();
    start(e.dataTransfer.files[0]);
  });
})();
