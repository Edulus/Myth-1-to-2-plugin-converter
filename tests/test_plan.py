"""Tests for the plan model and its views.

The point of `src/plan.py` is that the model can be inspected *before* anything
is written, so these mostly check that a plan answers questions truthfully
without touching the filesystem.
"""

import json
import pathlib
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import decisions, formats, mesh, plan as plan_module, reader  # noqa: E402
from src.views import html as html_view, text as text_view  # noqa: E402

from . import fixtures  # noqa: E402


def write_container(tags):
    handle = tempfile.NamedTemporaryFile("wb", suffix=".gor", delete=False)
    handle.write(fixtures.build_tfl_mono(tags))
    handle.close()
    return pathlib.Path(handle.name)


class TestPlanModel(unittest.TestCase):
    def setUp(self):
        self.path = write_container(fixtures.MESH_TAGS)
        self.plan = plan_module.build(self.path)

    def test_building_a_plan_writes_nothing(self):
        """The whole reason the model exists: look before you commit."""
        with tempfile.TemporaryDirectory() as tmp:
            before = set(pathlib.Path(tmp).iterdir())
            plan_module.build(self.path)
            self.assertEqual(before, set(pathlib.Path(tmp).iterdir()))

    def test_summary_matches_the_outcomes(self):
        summary = self.plan.summary()
        self.assertEqual(len(fixtures.MESH_TAGS), summary["source tags"])
        self.assertEqual(len(self.plan.converted()), summary["converted"])
        self.assertEqual(len(self.plan.passed_through()), summary["passed through"])
        self.assertEqual(1, summary["entrypoints"], "one per mesh")

    def test_by_tag_type_partitions_every_tag(self):
        by_type = self.plan.by_tag_type()
        total = sum(c["converted"] + c["passed-through"] for c in by_type.values())
        self.assertEqual(len(self.plan.outcomes), total)

    def test_synthesised_fields_carry_their_evidence(self):
        fields = {f.name: f for f in self.plan.synthesised}
        self.assertEqual("unanimous", fields["ceiling_height"].confidence)
        self.assertEqual(40, fields["ceiling_height"].agreed)
        self.assertEqual("check", fields["transition_point"].confidence)
        self.assertIn(fields["transition_point"], self.plan.needs_review())

    def test_a_plan_with_guesses_left_is_not_ready(self):
        self.assertFalse(self.plan.is_ready())
        self.assertTrue(self.plan.needs_review())

    def test_decisions_change_the_plan(self):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".toml", delete=False, encoding="utf-8"
        )
        handle.write(
            "[options]\nuse_vtfl = true\n\n"
            "[mesh_defaults]\ntransition_point = 60000\nreverb_environment = 0\n"
            "dark_fraction = 229\nlight_fraction = 25\n"
        )
        handle.close()

        decided = plan_module.build(self.path, decisions=decisions.load(handle.name))
        fields = {f.name: f for f in decided.synthesised}

        self.assertTrue(fields["transition_point"].overridden)
        self.assertEqual(60000, fields["transition_point"].value)
        self.assertTrue(decided.options["use_vtfl"])
        self.assertEqual([], decided.needs_review(), "all shaky fields now decided")

    def test_unresolved_references_are_listed_with_candidates(self):
        tags = [t for t in fixtures.MESH_TAGS if t[1] != b"stli"]
        path = write_container(tags)
        candidates = {b"stli": [("abcd", "a string list", 3)]}
        plan = plan_module.build(path, candidates=candidates)

        self.assertEqual(1, len(plan.unresolved))
        ref = plan.unresolved[0]
        self.assertEqual("stli.30cc", ref.label)
        self.assertEqual([("abcd", "a string list", 3)], ref.candidates)
        self.assertIn(ref, plan.undecided())

    def test_a_decision_resolves_a_reference(self):
        tags = [t for t in fixtures.MESH_TAGS if t[1] != b"stli"]
        tags.append((b"sub", b"stli", b"9999", b"Substitute\0"))
        path = write_container(tags)

        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".toml", delete=False, encoding="utf-8"
        )
        handle.write('[[tag]]\ntype = "stli"\nid = "30cc"\nmap_to = "9999"\n')
        handle.close()

        plan = plan_module.build(path, decisions=decisions.load(handle.name))
        self.assertEqual([], plan.unresolved, "the reference now resolves")

    def test_execute_writes_what_the_plan_described(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out.plugin"
            written = plan_module.execute(self.plan, out)

            self.assertEqual(written, out.stat().st_size)
            result = reader.read(out)
            self.assertTrue(result.is_sb)
            self.assertEqual(self.plan.source_tags, len(result.tags))
            self.assertEqual(len(self.plan.entrypoints), len(result.entrypoints))


class TestTextView(unittest.TestCase):
    def test_renders_and_reports_readiness(self):
        plan = plan_module.build(write_container(fixtures.MESH_TAGS))
        lines = text_view.render(plan)
        joined = "\n".join(lines)

        self.assertTrue(all(isinstance(line, str) for line in lines))
        self.assertIn("NOT READY", joined)
        self.assertIn("Levels the game will list", joined)


class TestHtmlView(unittest.TestCase):
    def setUp(self):
        self.plan = plan_module.build(write_container(fixtures.MESH_TAGS))
        self.page = html_view.render(self.plan, title="Test plan")

    def test_is_self_contained(self):
        """A strict CSP blocks external hosts, and the file has to work offline."""
        self.assertEqual(
            [], re.findall(r'(?:src|href)\s*=\s*"https?://', self.page)
        )
        self.assertNotIn("@import", self.page)

    def test_embeds_the_plan_as_valid_json(self):
        match = re.search(r"const PLAN = (\{.*?\});\n", self.page, re.S)
        self.assertIsNotNone(match, "plan data must be embedded")
        data = json.loads(match.group(1))

        self.assertEqual(len(self.plan.outcomes), len(data["tags"]))
        self.assertEqual(len(self.plan.entrypoints), len(data["levels"]))
        self.assertEqual(self.plan.is_ready(), data["ready"])

    def test_carries_the_title_and_both_themes(self):
        self.assertIn("<title>Test plan", self.page)
        self.assertIn("prefers-color-scheme: dark", self.page)
        self.assertIn('data-theme="dark"', self.page)
        self.assertIn('data-theme="light"', self.page)

    def test_escapes_content_that_could_break_the_page(self):
        tags = [
            (b"<script>x</script>", b"mesh", b"evil", fixtures.mesh_body()),
        ]
        plan = plan_module.build(write_container(tags))
        page = html_view.render(plan)

        # The tag name must not appear as a live script element.
        self.assertNotIn("<script>x</script>", page)

    def test_page_is_ascii_only(self):
        """No charset is guaranteed when the file is opened from disk, so the
        template avoids raw non-ASCII and uses entities instead."""
        non_ascii = sorted({hex(ord(c)) for c in self.page if ord(c) > 127})
        self.assertEqual([], non_ascii, "use HTML entities, not raw characters")

    def test_offers_the_decisions_file_as_output(self):
        """The control half of the loop: the page's output is convert's input."""
        self.assertIn("decisions.toml", self.page)
        self.assertIn("convert --decisions", self.page)
        self.assertIn("download", self.page)


if __name__ == "__main__":
    unittest.main()
