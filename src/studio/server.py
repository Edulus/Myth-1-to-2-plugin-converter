"""A small local web app for converting a TFL plugin, aimed at first-timers.

    python -m src studio

Starts a server on 127.0.0.1 and opens a browser. Unlike the static page that
``plan --html`` writes, this one can act: browse for files, find your Myth II
install, run the conversion, and install the result into your plugins folder.

**Local only, and deliberately so.** This tool reads and writes real files on
your machine, so the server binds to the loopback address, refuses any ``Host``
but its own loopback name (DNS rebinding) and any ``Origin`` but its own (a page
on another site), and requires a token minted at startup and given to the page
in its URL. Without
the token, a page you happen to have open on another site could otherwise script
this server into writing files. None of this makes it safe to expose publicly and
it is not meant to be.

The API is deliberately thin. Everything it does is a call into `src.plan`,
`src.decisions` and `src.convert` -- the studio is a view and a control surface,
not a second implementation.
"""

import http.server
import json
import mimetypes
import pathlib
import secrets
import threading
import urllib.parse
import webbrowser

from .. import codec, decisions as decisions_module, plan as plan_module, reader
from ..convert import plugin as convert_plugin

STATIC = pathlib.Path(__file__).parent / "static"

# Names of the Myth II tag archives, used to recognise an install directory.
INSTALL_MARKERS = ("tags", "plugins")


class Studio:
    """Everything the server knows. One conversion session."""

    def __init__(self):
        self.token = secrets.token_urlsafe(24)
        self.plugin_path = None
        self.myth2_dir = None
        self.candidates = {}
        self.plan = None

    # -- actions ------------------------------------------------------------

    def open_plugin(self, path):
        path = pathlib.Path(path).expanduser()
        mono = reader.read(path)  # raises FormatError if it is not a container
        if not mono.is_tfl:
            raise ValueError(
                f"{path.name} is already a Myth II container. This tool converts "
                f"Myth: The Fallen Lords plugins (.gor files) into Myth II ones."
            )
        self.plugin_path = path
        self.plan = None
        return {
            "path": str(path),
            "name": path.name,
            "bytes": path.stat().st_size,
            "tags": len(mono.tags),
            "meshes": len(mono.by_type(b"mesh")),
            "types": {
                codec.decode_string(t): n for t, n in mono.tag_types().items()
            },
        }

    def set_myth2_dir(self, path):
        path = pathlib.Path(path).expanduser()
        if not path.is_dir():
            raise ValueError(f"{path} is not a folder.")
        found = [m for m in INSTALL_MARKERS if (path / m).is_dir()]
        if not found:
            raise ValueError(
                f"{path} does not look like a Myth II install -- expected a "
                f"'tags' or 'plugins' folder inside it."
            )
        self.myth2_dir = path
        self.candidates = _scan_candidates(path)
        self.plan = None
        return {
            "path": str(path),
            "folders": found,
            "plugins": len(list((path / "plugins").glob("*")))
            if (path / "plugins").is_dir()
            else 0,
            "candidateTypes": len(self.candidates),
            "candidateTags": sum(len(v) for v in self.candidates.values()),
        }

    def build_plan(self, chosen=None, name=None):
        if not self.plugin_path:
            raise ValueError("Open a TFL plugin first.")
        self.plan = plan_module.build(
            self.plugin_path,
            decisions=chosen,
            candidates=self.candidates,
            name=name,
        )
        return _plan_payload(self.plan)

    def convert(self, chosen, name, out_path):
        self.build_plan(chosen, name)
        out_path = pathlib.Path(out_path).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        written = plan_module.execute(self.plan, out_path)
        return {
            "path": str(out_path),
            "bytes": written,
            "filenameTooLong": len(out_path.name) > convert_plugin.MAX_PLUGIN_FILENAME,
            "filenameLength": len(out_path.name),
        }

    def read_log(self):
        """The engine's own log -- the best oracle when a level fails to start."""
        if not self.myth2_dir:
            raise ValueError("Point at your Myth II install first.")
        log = self.myth2_dir / "myth_log.txt"
        if not log.is_file():
            return {"found": False, "text": ""}
        text = log.read_text(encoding="utf-8", errors="replace")
        return {"found": True, "path": str(log), "text": text[-20000:]}


def _scan_candidates(myth2_dir):
    """Tag ids and names by type, from every container in a Myth II install."""
    found = {}
    counts = {}
    for sub in ("tags", "plugins"):
        source = myth2_dir / sub
        if not source.is_dir():
            continue
        for path in sorted(source.iterdir()):
            if not path.is_file():
                continue
            try:
                data = path.read_bytes()
                reader.detect_game_version(data)
                mono = reader.read_bytes(data, path.name)
            except (OSError, reader.FormatError, ValueError):
                continue
            if not mono.is_sb:
                continue
            for tag in mono.tags:
                key = (tag.tag_type, tag.tag_id)
                counts[key] = counts.get(key, 0) + 1
                found.setdefault(tag.tag_type, {}).setdefault(tag.tag_id, tag.name)
    return {
        tag_type: sorted(
            (
                (codec.decode_string(tid), name, counts[(tag_type, tid)])
                for tid, name in by_id.items()
            ),
            key=lambda row: -row[2],
        )
        for tag_type, by_id in found.items()
    }


def _plan_payload(plan):
    from ..views.html import _plan_data

    payload = _plan_data(plan)
    payload["outputBytes"] = plan.output_size()
    return payload


def _decisions_from(body):
    """Build a `Decisions` from the JSON the page posts."""
    return decisions_module.Decisions(
        options={
            "use_vtfl": bool(body.get("useVtfl")),
            "plugin_name": body.get("pluginName") or "",
        },
        tag_map=[
            {"type": t, "id": i, "map_to": v}
            for (t, i, v) in (
                (e["type"], e["id"], e.get("mapTo", "")) for e in body.get("tags", [])
            )
            if v
        ],
        mesh_defaults=_coerce(body.get("meshDefaults") or {}),
    )


def _coerce(overrides):
    """Numbers arrive from a form as strings; the codec needs real numbers."""
    out = {}
    for key, value in overrides.items():
        if isinstance(value, str):
            text = value.strip()
            try:
                out[key] = int(text)
                continue
            except ValueError:
                pass
            try:
                out[key] = float(text)
                continue
            except ValueError:
                out[key] = text
        else:
            out[key] = value
    return out


class Handler(http.server.BaseHTTPRequestHandler):
    studio = None
    server_version = "myth-plugin-converter-studio"

    def log_message(self, fmt, *args):  # quieter than the default
        pass

    # -- guards -------------------------------------------------------------

    def _own_hosts(self):
        port = self.server.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _authorised(self):
        # DNS rebinding: a hostile name that resolves to 127.0.0.1 arrives with
        # that name in Host. Only loopback names on our own port are us.
        if self.headers.get("Host", "") not in self._own_hosts():
            return False
        # Browsers attach Origin to every POST, same-origin ones included
        # (Fetch spec), and to cross-site requests generally. Our own page's
        # origin is allowed; any other is a page elsewhere trying to drive us.
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {
            f"http://{host}" for host in self._own_hosts()
        }:
            return False
        query = urllib.parse.urlparse(self.path).query
        token = urllib.parse.parse_qs(query).get("token", [""])[0]
        header = self.headers.get("X-Studio-Token", "")
        return secrets.compare_digest(token or header, self.studio.token)

    # -- plumbing -----------------------------------------------------------

    def _send(self, status, body, content_type="application/json"):
        payload = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path

        if route in ("/", "/index.html"):
            if not self._authorised():
                return self._send(
                    403,
                    b"<h1>Not authorised</h1><p>Open the link printed in the terminal.</p>",
                    "text/html; charset=utf-8",
                )
            return self._serve_static("index.html")

        if route.startswith("/static/"):
            return self._serve_static(route[len("/static/") :])

        if not self._authorised():
            return self._send(403, {"error": "not authorised"})

        if route == "/api/state":
            return self._send(200, self._state())
        if route == "/api/log":
            return self._guard(self.studio.read_log)
        if route == "/api/suggest-install":
            return self._send(200, {"paths": _likely_installs()})
        if route == "/api/browse":
            args = urllib.parse.parse_qs(parsed.query)
            return self._guard(lambda: _browse(args.get("path", [""])[0]))

        return self._send(404, {"error": "no such endpoint"})

    def do_POST(self):
        if not self._authorised():
            return self._send(403, {"error": "not authorised"})
        route = urllib.parse.urlparse(self.path).path
        body = self._read_json()

        if route == "/api/open-plugin":
            return self._guard(lambda: self.studio.open_plugin(body["path"]))
        if route == "/api/myth2-dir":
            return self._guard(lambda: self.studio.set_myth2_dir(body["path"]))
        if route == "/api/plan":
            return self._guard(
                lambda: self.studio.build_plan(
                    _decisions_from(body), body.get("pluginName") or None
                )
            )
        if route == "/api/convert":
            return self._guard(
                lambda: self.studio.convert(
                    _decisions_from(body),
                    body.get("pluginName") or None,
                    body["outPath"],
                )
            )
        return self._send(404, {"error": "no such endpoint"})

    def _guard(self, action):
        """Run an action, turning expected failures into a readable message."""
        try:
            return self._send(200, action())
        except (reader.FormatError, convert_plugin.ConversionError, ValueError) as exc:
            return self._send(400, {"error": str(exc)})
        except FileNotFoundError as exc:
            return self._send(400, {"error": f"Not found: {exc.filename}"})
        except PermissionError as exc:
            return self._send(400, {"error": f"No permission to read {exc.filename}"})
        except OSError as exc:
            return self._send(400, {"error": str(exc)})

    def _state(self):
        studio = self.studio
        return {
            "plugin": str(studio.plugin_path) if studio.plugin_path else None,
            "myth2Dir": str(studio.myth2_dir) if studio.myth2_dir else None,
            "candidateTypes": len(studio.candidates),
            "hasPlan": studio.plan is not None,
        }

    def _serve_static(self, name):
        path = (STATIC / name).resolve()
        if not path.is_file() or STATIC.resolve() not in path.parents:
            return self._send(404, b"not found", "text/plain")
        kind, _ = mimetypes.guess_type(path.name)
        body = path.read_bytes()
        self._send(200, body, f"{kind or 'application/octet-stream'}; charset=utf-8")


def _likely_installs():
    """Places a Myth II install usually lives, so the user rarely types a path."""
    seeds = []
    for drive in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        seeds += [
            pathlib.Path(f"{drive}:/Program Files (x86)/Myth II"),
            pathlib.Path(f"{drive}:/Program Files/Myth II"),
            pathlib.Path(f"{drive}:/Myth II"),
            pathlib.Path(f"{drive}:/Games/Myth II"),
        ]
    home = pathlib.Path.home()
    seeds += [
        home / "Applications/Myth II",
        pathlib.Path("/Applications/Myth II"),
        home / "Library/Application Support/Myth II",
    ]
    return [
        str(p)
        for p in seeds
        if p.is_dir() and any((p / m).is_dir() for m in INSTALL_MARKERS)
    ]


def _browse(path):
    """List a folder so the page can offer a file picker over real paths."""
    target = pathlib.Path(path).expanduser() if path else pathlib.Path.home()
    if not target.is_dir():
        target = target.parent if target.parent.is_dir() else pathlib.Path.home()
    entries = []
    try:
        for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if entry.name.startswith("."):
                continue
            try:
                size = entry.stat().st_size if entry.is_file() else 0
            except OSError:
                continue
            entries.append({"name": entry.name, "dir": entry.is_dir(), "bytes": size})
    except PermissionError:
        raise ValueError(f"No permission to list {target}")
    return {
        "path": str(target),
        "parent": str(target.parent) if target.parent != target else None,
        "entries": entries[:800],
    }


def serve(port=0, open_browser=True):
    """Run the studio until interrupted. Returns nothing; blocks."""
    studio = Studio()
    handler = type("BoundHandler", (Handler,), {"studio": studio})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    actual = httpd.server_address[1]
    url = f"http://127.0.0.1:{actual}/?token={studio.token}"

    print("myth-plugin-converter studio")
    print(f"  {url}")
    print("  Local only. Press Ctrl+C to stop.")

    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
