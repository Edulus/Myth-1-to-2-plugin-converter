// Runs the unit swapper (the project's Python, under Pyodide) off the page's main
// thread. Everything happens in this browser: the visitor's files are mounted
// into Pyodide's filesystem *without being copied* (WORKERFS reads the bytes from
// the file on disk as Python asks for them), so a 500 MB Civil War maps plugin
// never has to fit in memory. The new plugin is handed back in chunks.
//
// Messages in:  {type: "scan", code, maps, tagsets, myth}
//               {type: "build", swaps, name}
// Messages out: {type: "stage", stage, done?}
//               {type: "scanned", result}
//               {type: "done", result, blob}
//               {type: "problem", message, details?}

importScripts("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js");

let py = null;
let mounted = false;
let inputs = null;  // paths in Pyodide's filesystem, kept between scan and build

const stage = (name, extra = {}) => postMessage({ type: "stage", stage: name, ...extra });

async function engine(codeUrl) {
  if (py) return py;
  stage("engine");
  py = await loadPyodide();
  const zip = await (await fetch(codeUrl)).arrayBuffer();
  py.unpackArchive(zip, "zip", { extractDir: "/app" });
  py.runPython("import sys; sys.path.insert(0, '/app')");
  return py;
}

// Put the visitor's files where Python can open them. Names may carry folders
// (a blob called "myth2/tags/small install" appears at that path).
function mountInputs(msg) {
  if (mounted) { py.FS.unmount("/in"); mounted = false; }
  else { py.FS.mkdirTree("/in"); }
  const wanted = new Set(py.runPython("from src import swap\nlist(swap.STOCK_ARCHIVES)").toJs());
  const blobs = [{ name: "maps/" + msg.maps.name, data: msg.maps }];
  msg.tagsets.forEach((f) => blobs.push({ name: "tagset/" + f.name, data: f }));
  for (const { path, file } of msg.myth) {
    if (wanted.has(path)) blobs.push({ name: "myth2/" + path, data: file });
  }
  py.FS.mount(py.FS.filesystems.WORKERFS, { blobs }, "/in");
  mounted = true;
  inputs = {
    maps: "/in/maps/" + msg.maps.name,
    tagsets: msg.tagsets.map((f) => "/in/tagset/" + f.name),
    myth2: "/in/myth2",
  };
}

const OOM = "Your browser ran out of memory. Close other tabs and try again, or use a computer with more memory.";

const SCAN = `
import json, traceback
from src import webswap
try:
    answer = webswap.scan(maps_path, list(tagset_paths), myth2_dir)
except webswap.Problem as exc:
    answer = {"problem": str(exc)}
except MemoryError:
    answer = {"problem": "${OOM}"}
except Exception:
    answer = {"problem": "Something went wrong inside the swapper.", "details": traceback.format_exc()}
json.dumps(answer)
`;

const BUILD = `
import json, traceback
from pyodide.ffi import to_js
from src import webswap
def emit(chunk):
    emit_js(to_js(chunk))
try:
    answer = webswap.build(maps_path, list(tagset_paths), myth2_dir, dict(swaps), out_name, emit)
except webswap.Problem as exc:
    answer = {"problem": str(exc)}
except MemoryError:
    answer = {"problem": "${OOM}"}
except Exception:
    answer = {"problem": "Something went wrong inside the swapper.", "details": traceback.format_exc()}
json.dumps(answer)
`;

function setInputs() {
  py.globals.set("maps_path", inputs.maps);
  py.globals.set("tagset_paths", py.toPy(inputs.tagsets));
  py.globals.set("myth2_dir", inputs.myth2);
}

onmessage = async ({ data: msg }) => {
  try {
    if (msg.type === "scan") {
      await engine(msg.code);
      stage("read");
      mountInputs(msg);
      setInputs();
      const answer = JSON.parse(await py.runPythonAsync(SCAN));
      if (answer.problem) { postMessage({ type: "problem", message: answer.problem, details: answer.details }); return; }
      postMessage({ type: "scanned", result: answer });
    } else if (msg.type === "build") {
      if (!py || !mounted) throw new Error("Choose the files first.");
      setInputs();
      const chunks = [];
      let done = 0;
      py.globals.set("emit_js", (bytes) => {
        chunks.push(bytes);
        done += bytes.length;
        stage("write", { done });
      });
      stage("write", { done: 0 });
      py.globals.set("swaps", py.toPy(msg.swaps));
      py.globals.set("out_name", msg.name);
      const answer = JSON.parse(await py.runPythonAsync(BUILD));
      if (answer.problem) { postMessage({ type: "problem", message: answer.problem, details: answer.details }); return; }
      postMessage({ type: "done", result: answer, blob: new Blob(chunks, { type: "application/octet-stream" }) });
    }
  } catch (e) {
    const text = String((e && e.stack) || e);
    // Running out of WebAssembly memory leaves Pyodide unusable; start afresh next time.
    const memory = /out of memory|Aborted|RangeError|Cannot allocate/i.test(text);
    if (memory) { py = null; mounted = false; inputs = null; }
    postMessage({
      type: "problem",
      message: memory ? OOM : "Something went wrong in the swapper.",
      details: text,
    });
  }
};
