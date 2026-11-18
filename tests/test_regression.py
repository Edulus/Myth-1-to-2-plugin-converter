"""The real-data regression check (scripts/regression.py, plan item B2).

The logic is tested on its own; the check itself runs only when your TFL tags
folder is given (``TFL_TAGS_DIR``) and the source plugin is in
``local/release/`` -- game data is never committed. Set ``MAGMA_TFL_PORT`` too
to check the similarity counts against Magma's port.
"""

import importlib.util
import os
import pathlib
import unittest
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("regression", ROOT / "scripts" / "regression.py")
regression = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(regression)


def tag(tag_type, tag_id, body):
    return SimpleNamespace(tag_type=tag_type, tag_id=tag_id, body=body)


class Keys(unittest.TestCase):
    def test_printable_and_hex(self):
        self.assertEqual(".256/ambu", regression.tag_key(tag(b".256", b"ambu", b"")))
        self.assertEqual("mons/0x00ff0102", regression.tag_key(tag(b"mons", b"\x00\xff\x01\x02", b"")))
        self.assertEqual("soun/0x612f6263", regression.tag_key(tag(b"soun", b"a/bc", b"")))

    def test_repeated_keys_are_numbered(self):
        hashes = regression.body_hashes([tag(b"mesh", b"aaaa", b"1"), tag(b"mesh", b"aaaa", b"2")])
        self.assertEqual(["mesh/aaaa", "mesh/aaaa#2"], list(hashes))


class Diff(unittest.TestCase):
    OLD = {"tags": {"mons/a": "1", "mons/b": "2", "proj/c": "3"}, "magma_identical": {"mons": 5, "proj": 2}}

    def test_no_change(self):
        self.assertEqual([], regression.diff(self.OLD, dict(self.OLD)))

    def test_changes_are_counted_by_type(self):
        new = {"tags": {"mons/a": "1", "mons/b": "X", "proj/d": "4"}, "magma_identical": {"mons": 4, "proj": 3}}
        lines = regression.diff(self.OLD, new)
        self.assertIn("  mons: 1 changed", lines)
        self.assertIn("  proj: 1 added, 1 removed", lines)
        self.assertIn("  identical to Magma, mons: 5 -> 4   <-- fewer", lines)
        self.assertIn("  identical to Magma, proj: 2 -> 3", lines)


TFL_TAGS = os.environ.get("TFL_TAGS_DIR")
MAGMA = os.environ.get("MAGMA_TFL_PORT")


@unittest.skipUnless(TFL_TAGS and regression.SOURCE.is_file(),
                     "set TFL_TAGS_DIR and put the source plugin in local/release/ to run")
class RealData(unittest.TestCase):
    def test_conversion_matches_the_manifest(self):
        lines = regression.check(pathlib.Path(TFL_TAGS), pathlib.Path(MAGMA) if MAGMA else None)
        self.assertEqual([], lines, "conversion changed; if intended, run scripts/regression.py --update:\n"
                         + "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
