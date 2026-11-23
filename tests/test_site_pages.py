"""docs/: the built site is consistent -- links and anchors resolve, redirects
point at real targets, pages carry their dates, the Google verification file is
untouched. (CI separately checks docs/ is exactly what scripts/keep_site.py builds.)"""

import hashlib
import html.parser
import pathlib
import re
import unittest
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
GOOGLE = DOCS / "google5781bd5b5c2cd529.html"
GOOGLE_SHA256 = "022027952f2c808ec140c7878587854720c17743a21c50e18c1424ecaf39e3f2"


def pages():
    return sorted(p for p in DOCS.rglob("*.html") if "stock" not in p.relative_to(DOCS).parts and p != GOOGLE)


class Scan(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links, self.refresh = set(), [], None
        self.open = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        for key in ("href", "src"):
            if a.get(key):
                self.links.append(a[key])
        if tag == "meta" and (a.get("http-equiv") or "").lower() == "refresh":
            self.refresh = re.search(r"url=(\S+)", a.get("content", "")).group(1)
        if tag in ("details", "ul", "ol", "section"):
            self.open.append(tag)

    def handle_endtag(self, tag):
        if tag in ("details", "ul", "ol", "section"):
            assert self.open and self.open.pop() == tag, f"unbalanced </{tag}>"


def scan(path):
    s = Scan()
    s.feed(path.read_text(encoding="utf-8"))
    assert not s.open, f"{path}: unclosed {s.open}"
    return s


def resolve(page, link):
    """The file and fragment a relative link points at, or None for an outside link."""
    if re.match(r"^[a-z][a-z0-9+.-]*:", link, re.I) or link.startswith("//"):
        return None
    parts = urllib.parse.urlsplit(link)
    target = page if not parts.path else (page.parent / urllib.parse.unquote(parts.path)).resolve()
    if target.is_dir():
        target = target / "index.html"
    return target, parts.fragment


class Links(unittest.TestCase):
    def test_every_internal_link_and_anchor_resolves(self):
        cache = {}
        for page in pages():
            for link in scan(page).links:
                found = resolve(page, link)
                if found is None:
                    continue
                target, fragment = found
                self.assertTrue(target.is_file(), f"{page.relative_to(DOCS)}: {link} -> missing {target}")
                if fragment and target.suffix == ".html":
                    ids = cache.setdefault(target, scan(target).ids)
                    self.assertIn(fragment, ids, f"{page.relative_to(DOCS)}: {link} -> no #{fragment}")

    def test_redirect_pages_point_at_existing_targets(self):
        moved = {"keep/poem.html": "poems.html#keep", "keep/walter.html": "poems.html#walter",
                 "q/2.html": "closed.html#q2", "q/6.html": "closed.html#q6"}
        for rel, target in moved.items():
            page = DOCS / rel
            s = scan(page)
            self.assertEqual(s.refresh, target, rel)
            self.assertIn(target, s.links, f"{rel}: no visible link to its target")
            file, fragment = resolve(page, target)
            self.assertIn(fragment, scan(file).ids)


class Dates(unittest.TestCase):
    def read(self, rel):
        return (DOCS / rel).read_text(encoding="utf-8")

    def test_pages_say_when_they_were_last_checked(self):
        for rel in ("index.html", "convert/index.html", "swap/index.html", "keep/units.html", "keep/index.html"):
            self.assertRegex(re.sub(r"<[^>]+>", "", self.read(rel)), r"Updated \d{1,2} [A-Z][a-z]+ 20\d\d", rel)

    def test_questions_say_as_of(self):
        for rel in [f"q/{n}.html" for n in (1, 3, 4, 5, 7, 8, 9)] + ["q/closed.html"]:
            self.assertRegex(self.read(rel), r"\(as of \d{1,2} [A-Z][a-z]+ 20\d\d\)", rel)

    def test_update_pages_are_dated(self):
        for page in sorted((DOCS / "updates").glob("*.html")):
            self.assertRegex(page.read_text(encoding="utf-8"), r"Update &middot; \d{1,2} [A-Z][a-z]+ 20\d\d", page.name)


class Structure(unittest.TestCase):
    def test_closed_page_carries_both_original_threads(self):
        text = (DOCS / "q" / "closed.html").read_text(encoding="utf-8")
        self.assertIn('data-term="Q2: Terrain - faithful or smooth?"', text)
        self.assertIn('data-term="Q6: What does done look like?"', text)

    def test_home_folds_the_long_lists(self):
        text = (DOCS / "index.html").read_text(encoding="utf-8")
        self.assertLess(text.index("Please test now"), text.index("Working on now"))
        for needle in ("Up next (", "Later (", "The command-line steps", "Before you test ("):
            self.assertRegex(text, r"<details class=\"fold\"><summary>[^<]*" + re.escape(needle))
        self.assertIn("no replies yet", text)

    def test_google_verification_file_is_untouched(self):
        self.assertTrue(GOOGLE.is_file())
        self.assertEqual(hashlib.sha256(GOOGLE.read_bytes()).hexdigest(), GOOGLE_SHA256)


if __name__ == "__main__":
    unittest.main()
