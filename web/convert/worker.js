// Runs the converter (the project's Python, under Pyodide) off the page's main
// thread, so the page stays responsive. Everything happens in this browser:
// the visitor's plugin is read from their disk, the stock TFL tags come from
// this website, and the result goes back to the page as bytes to download.
//
// Messages in:  {type: "convert", file, code, manifest}
// Messages out: {type: "stage", stage, done?, total?}
//               {type: "done", result, data}  (data: the plugin's bytes)
//               {type: "problem", message, details?}

importScripts("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js");

let py = null;
let stockReady = null;  // the manifest version whose files are already in /work

const stage = (name, extra = {}) => postMessage({ type: "stage", stage: name, ...extra });

async function engine(codeUrl) {
  if (py) return py;
  stage("engine");
  py = await loadPyodide();
  const zip = await (await fetch(codeUrl)).arrayBuffer();
  py.unpackArchive(zip, "zip", { extractDir: "/app" });
  py.runPython("import sys; sys.path.insert(0, '/app')");
  py.FS.mkdirTree("/work");
  return py;
}

// The stock files are big and never change for a given manifest version, so
// keep a copy in the browser's cache storage. Any failure there just means
// fetching from the site again.
async function cachedFetch(url, version) {
  try {
    const name = "myth-stock-" + version;
    for (const old of await caches.keys()) {
      if (old.startsWith("myth-stock-") && old !== name) await caches.delete(old);
    }
    const cache = await caches.open(name);
    const hit = await cache.match(url);
    if (hit) return hit;
    const res = await fetch(url);
    if (res.ok) cache.put(url, res.clone()).catch(() => {});
    return res;
  } catch (e) {
    return fetch(url);
  }
}

// Stream a sequence of byte sources into one file in Pyodide's filesystem,
// without first joining them in memory.
async function streamInto(path, streams, onBytes) {
  const out = py.FS.open(path, "w");
  try {
    for (const getStream of streams) {
      const reader = (await getStream()).getReader();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        py.FS.write(out, value, 0, value.length);
        onBytes(value.length);
      }
    }
  } finally {
    py.FS.close(out);
  }
}

async function stock(manifestUrl) {
  const manifest = await (await fetch(manifestUrl)).json();
  if (stockReady === manifest.version) return manifest;
  const base = new URL(".", new URL(manifestUrl, self.location.href));
  const total = manifest.files.reduce((n, f) => n + f.bytes, 0);
  let done = 0;
  stage("stock", { done, total });
  for (const file of manifest.files) {
    const parts = file.parts.map((part) => async () => {
      const res = await cachedFetch(new URL(part, base).href, manifest.version);
      if (!res.ok) throw new Problem("The original game files couldn't be fetched from the website. Check your connection and try again.");
      return res.body;
    });
    await streamInto("/work/" + file.name, parts, (n) => {
      done += n;
      stage("stock", { done, total });
    });
  }
  stockReady = manifest.version;
  return manifest;
}

class Problem extends Error {}

const RUN = `
import gc, json, traceback
from src import web
try:
    answer = web.convert("/work/upload", upload_name, "/work/out", stock_paths)
except web.Problem as exc:
    answer = {"problem": str(exc)}
except MemoryError:
    answer = {"problem": "Your browser ran out of memory. Close other tabs and try again, or use a computer with more memory."}
except Exception:
    answer = {"problem": "Something went wrong inside the converter.", "details": traceback.format_exc()}
gc.collect()
json.dumps(answer)
`;

onmessage = async ({ data: msg }) => {
  if (msg.type !== "convert") return;
  try {
    await engine(msg.code);
    const manifest = await stock(msg.manifest);
    stage("plugin");
    await streamInto("/work/upload", [async () => msg.file.stream()], () => {});
    py.FS.mkdirTree("/work/out");
    stage("convert");
    py.globals.set("upload_name", msg.file.name);
    py.globals.set("stock_paths", py.toPy(manifest.files.map((f) => "/work/" + f.name)));
    const answer = JSON.parse(await py.runPythonAsync(RUN));
    if (answer.problem) {
      postMessage({ type: "problem", message: answer.problem, details: answer.details });
      return;
    }
    const bytes = py.FS.readFile(answer.path);
    py.FS.unlink(answer.path);
    postMessage({ type: "done", result: answer, data: bytes }, [bytes.buffer]);
  } catch (e) {
    const plain = e instanceof Problem;
    const text = String((e && e.stack) || e);
    // Running out of WebAssembly memory leaves Pyodide unusable; start afresh next time.
    const memory = !plain && /out of memory|Aborted|RangeError|Cannot allocate/i.test(text);
    if (memory) { py = null; stockReady = null; }
    postMessage({
      type: "problem",
      message: plain ? e.message
        : memory ? "Your browser ran out of memory. Close other tabs and try again, or use a computer with more memory."
        : "Something went wrong while converting.",
      details: plain ? undefined : text,
    });
  } finally {
    try { py && py.FS.unlink("/work/upload"); } catch (e) {}
  }
};
