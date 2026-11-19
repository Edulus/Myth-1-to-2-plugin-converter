"""site/content/: every content file loads and has the shape scripts/keep_site.py needs."""

import importlib.util
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("keep_site", ROOT / "scripts" / "keep_site.py")
keep_site = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(keep_site)  # loading it reads and validates every content file


class ContentShape(unittest.TestCase):
    def test_every_toml_file_is_used_and_parses(self):
        for path in (ROOT / "site" / "content").rglob("*.toml"):
            keep_site._content(path.relative_to(keep_site.CONTENT).as_posix())

    def test_updates(self):
        slugs = [u["slug"] for u in keep_site.UPDATES]
        self.assertEqual(slugs, sorted(slugs, reverse=True))
        self.assertEqual(len(set(slugs)), len(slugs))
        terms = [u["term"] for u in keep_site.UPDATES]
        self.assertEqual(len(set(terms)), len(terms))

    def test_questions_numbered_and_glossed(self):
        ns = [q["n"] for q in keep_site.QUESTIONS]
        self.assertEqual(ns, list(range(1, len(ns) + 1)))
        self.assertEqual(set(keep_site.QUESTION_GISTS), set(ns))
        terms = [q["term"] for q in keep_site.QUESTIONS] + [u["term"] for u in keep_site.UPDATES]
        self.assertEqual(len(set(terms)), len(terms))

    def test_unanswered_is_a_flag(self):
        # Which questions are unanswered is content and changes; check only the shape:
        # a boolean, never on a closed question, and at least one is set.
        flagged = [q for q in keep_site.QUESTIONS if "unanswered" in q]
        self.assertTrue(flagged)
        for q in flagged:
            self.assertIsInstance(q["unanswered"], bool, q["n"])
            self.assertFalse(q["unanswered"] and q.get("closed"), q["n"])

    def test_poems(self):
        for title, poem in (
            (keep_site.POEM_TITLE, keep_site.POEM),
            (keep_site.WALTER_TITLE, keep_site.WALTER_POEM),
            (keep_site.FABLE_TITLE, keep_site.FABLE_POEM),
        ):
            self.assertTrue(title)
            self.assertTrue(poem)
            for image, alt, lines in poem:
                self.assertEqual(bool(image), bool(alt))
                self.assertTrue(lines)

    def test_units_docket_keep(self):
        self.assertTrue(keep_site.UNIT_FIELDS)
        for row in keep_site.UNIT_FIELDS:
            self.assertEqual(len(row), 4)
        self.assertRegex(keep_site.DOCKET_UPDATED, r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(keep_site.GISTS_UPDATED, r"^\d{4}-\d{2}-\d{2}$")
        self.assertTrue(keep_site.DOCKET)
        self.assertRegex(keep_site.KEEP_PAGE["hash"], r"^[0-9a-f]{64}$")
        self.assertIn("<p>", keep_site.KEEP_BODY)


class BadContent(unittest.TestCase):
    """A missing or malformed file stops the build with a message naming it."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        shutil.copytree(ROOT / "site" / "content", self.tmp / "content")
        self._orig = keep_site.CONTENT
        keep_site.CONTENT = self.tmp / "content"
        self.addCleanup(setattr, keep_site, "CONTENT", self._orig)

    def fails(self, call, *needles):
        with self.assertRaises(keep_site.ContentError) as ctx:
            call()
        for needle in needles:
            self.assertIn(needle, str(ctx.exception))

    def test_missing_file(self):
        (self.tmp / "content" / "docket.toml").unlink()
        self.fails(keep_site._load_docket, "docket.toml", "cannot read")

    def test_malformed_toml(self):
        (self.tmp / "content" / "units.toml").write_text("title = \n", encoding="utf-8")
        self.fails(keep_site._load_units, "units.toml", "not valid TOML")

    def test_missing_key(self):
        path = self.tmp / "content" / "questions" / "1.toml"
        path.write_text(path.read_text(encoding="utf-8").replace("gist =", "gisx ="), encoding="utf-8")
        self.fails(keep_site._load_questions, "questions/1.toml", "missing key 'gist'")

    def test_unanswered_must_be_true_or_false(self):
        path = self.tmp / "content" / "questions" / "1.toml"
        path.write_text(path.read_text(encoding="utf-8").replace("unanswered = true", 'unanswered = "yes"'),
                        encoding="utf-8")
        self.fails(keep_site._load_questions, "questions/1.toml", "'unanswered' must be true or false")

    def test_file_name_must_match(self):
        (self.tmp / "content" / "questions" / "1.toml").rename(self.tmp / "content" / "questions" / "01.toml")
        self.fails(keep_site._load_questions, "01.toml", "file name")

    def test_crlf_reads_the_same(self):
        path = self.tmp / "content" / "docket.toml"
        before = keep_site._load_docket()
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(keep_site._load_docket(), before)


if __name__ == "__main__":
    unittest.main()
