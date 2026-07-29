"""Tests for the local studio server.

The studio reads and writes real files, so the access guards get as much
attention as the happy path.
"""

import http.server
import json
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import reader  # noqa: E402
from src.studio import server as studio_server  # noqa: E402

from . import fixtures  # noqa: E402


class StudioTestCase(unittest.TestCase):
    """Spins up a real server on an ephemeral loopback port."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

        self.plugin = self.root / "test.gor"
        self.plugin.write_bytes(fixtures.build_tfl_mono(fixtures.MESH_TAGS))

        # A convincing-enough Myth II install.
        self.install = self.root / "Myth II"
        (self.install / "tags").mkdir(parents=True)
        (self.install / "plugins").mkdir()
        (self.install / "tags" / "small install").write_bytes(
            fixtures.build_sb_mono(
                [(b"grassland", b"meli", b"gras", b"\0" * 64)], name=b"small install"
            )
        )

        self.studio = studio_server.Studio()
        handler = type("Bound", (studio_server.Handler,), {"studio": self.studio})
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def call(self, path, body=None, token=None, headers=None):
        token = self.studio.token if token is None else token
        sep = "&" if "?" in path else "?"
        url = f"http://127.0.0.1:{self.port}{path}{sep}token={token}"
        request = urllib.request.Request(
            url,
            method="POST" if body is not None else "GET",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, {"raw": raw.decode(errors="replace")}


class TestAccessGuards(StudioTestCase):
    def test_api_requires_the_token(self):
        status, _ = self.call("/api/state", token="")
        self.assertEqual(403, status)
        status, _ = self.call("/api/state", token="not-the-token")
        self.assertEqual(403, status)

    def test_a_cross_site_page_cannot_drive_the_server(self):
        """Browsers attach Origin to cross-site requests. Even with the right
        token in the URL, one of those must be refused."""
        status, _ = self.call(
            "/api/state", headers={"Origin": "https://example.invalid"}
        )
        self.assertEqual(403, status)

    def test_the_token_is_not_guessable(self):
        self.assertGreaterEqual(len(self.studio.token), 24)

    def test_static_assets_do_not_leak_the_filesystem(self):
        status, body = self.call("/static/../../../pyproject.toml")
        self.assertNotEqual(200, status)


class TestEndpoints(StudioTestCase):
    def test_opens_a_tfl_plugin_and_describes_it(self):
        status, out = self.call("/api/open-plugin", {"path": str(self.plugin)})
        self.assertEqual(200, status)
        self.assertEqual(len(fixtures.MESH_TAGS), out["tags"])
        self.assertEqual(1, out["meshes"])

    def test_refuses_a_myth_ii_container_with_a_useful_message(self):
        sb = self.root / "already.plugin"
        sb.write_bytes(fixtures.build_sb_mono(fixtures.SAMPLE_TAGS))
        status, out = self.call("/api/open-plugin", {"path": str(sb)})

        self.assertEqual(400, status)
        self.assertIn("already a Myth II container", out["error"])

    def test_refuses_something_that_is_not_a_container(self):
        junk = self.root / "readme.txt"
        junk.write_text("not a myth file at all, just some words")
        status, out = self.call("/api/open-plugin", {"path": str(junk)})

        self.assertEqual(400, status)
        self.assertIn("Not a Myth monolith", out["error"])

    def test_missing_file_says_so_rather_than_crashing(self):
        status, out = self.call("/api/open-plugin", {"path": str(self.root / "nope")})
        self.assertEqual(400, status)
        self.assertTrue(out["error"])

    def test_accepts_an_install_and_indexes_its_tags(self):
        status, out = self.call("/api/myth2-dir", {"path": str(self.install)})
        self.assertEqual(200, status)
        self.assertIn("tags", out["folders"])
        self.assertEqual(1, out["candidateTags"])

    def test_rejects_a_folder_that_is_not_an_install(self):
        status, out = self.call("/api/myth2-dir", {"path": str(self.root)})
        self.assertEqual(400, status)
        self.assertIn("does not look like a Myth II install", out["error"])

    def test_plan_needs_a_plugin_first(self):
        status, out = self.call("/api/plan", {})
        self.assertEqual(400, status)
        self.assertIn("Open a TFL plugin first", out["error"])

    def test_plan_returns_the_model(self):
        self.call("/api/open-plugin", {"path": str(self.plugin)})
        status, out = self.call("/api/plan", {"pluginName": "Test"})

        self.assertEqual(200, status)
        self.assertEqual(len(fixtures.MESH_TAGS), len(out["tags"]))
        self.assertEqual(1, len(out["levels"]))
        self.assertIn("undecided", out)
        self.assertGreater(out["outputBytes"], 0)

    def test_form_values_arrive_as_strings_and_are_coerced(self):
        """Every field in a form is a string; the codec needs real numbers."""
        self.call("/api/open-plugin", {"path": str(self.plugin)})
        status, out = self.call(
            "/api/plan", {"meshDefaults": {"ceiling_height": "1500"}}
        )
        self.assertEqual(200, status)
        field = [f for f in out["synthesised"] if f["name"] == "ceiling_height"][0]
        self.assertEqual(1500, field["value"])
        self.assertTrue(field["overridden"])

    def test_convert_writes_a_readable_plugin(self):
        self.call("/api/open-plugin", {"path": str(self.plugin)})
        out_path = self.install / "plugins" / "Converted"
        status, out = self.call(
            "/api/convert", {"pluginName": "Converted", "outPath": str(out_path)}
        )

        self.assertEqual(200, status)
        self.assertTrue(out_path.is_file())
        self.assertEqual(out["bytes"], out_path.stat().st_size)
        self.assertFalse(out["filenameTooLong"])

        result = reader.read(out_path)
        self.assertTrue(result.is_sb)
        self.assertEqual(1, len(result.entrypoints))

    def test_convert_flags_a_filename_myth_ii_would_ignore(self):
        self.call("/api/open-plugin", {"path": str(self.plugin)})
        long_name = "x" * 40
        status, out = self.call(
            "/api/convert",
            {"pluginName": "ok", "outPath": str(self.install / "plugins" / long_name)},
        )
        self.assertEqual(200, status)
        self.assertTrue(out["filenameTooLong"])
        self.assertEqual(40, out["filenameLength"])

    def test_log_reports_absence_rather_than_failing(self):
        self.call("/api/myth2-dir", {"path": str(self.install)})
        status, out = self.call("/api/log")
        self.assertEqual(200, status)
        self.assertFalse(out["found"])

        (self.install / "myth_log.txt").write_text("Starting mesh \"Test\"...")
        status, out = self.call("/api/log")
        self.assertTrue(out["found"])
        self.assertIn("Starting mesh", out["text"])

    def test_browse_lists_a_folder(self):
        status, out = self.call(f"/api/browse?path={self.root}")
        self.assertEqual(200, status)
        names = {e["name"] for e in out["entries"]}
        self.assertIn("test.gor", names)
        self.assertIn("Myth II", names)
        self.assertTrue(any(e["dir"] for e in out["entries"]))


class TestDecisionCoercion(unittest.TestCase):
    def test_numbers_survive_the_form_round_trip(self):
        coerced = studio_server._coerce(
            {"a": "42", "b": "1.5", "c": "text", "d": 7}
        )
        self.assertEqual({"a": 42, "b": 1.5, "c": "text", "d": 7}, coerced)

    def test_only_filled_in_choices_become_mappings(self):
        chosen = studio_server._decisions_from(
            {
                "tags": [
                    {"type": "meli", "id": "deml", "mapTo": "gras"},
                    {"type": "medi", "id": "mawa", "mapTo": ""},
                ]
            }
        )
        self.assertEqual(1, len(chosen.tag_map))
        self.assertEqual(1, len(chosen.id_map()))


if __name__ == "__main__":
    unittest.main()
