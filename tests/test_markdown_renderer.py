import json
import shutil
import subprocess
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "webapp" / "js" / "markdown.js"
GUIDE = Path(__file__).resolve().parents[1] / "docs" / "VOCABULARY_GUIDE.md"


def render(markdown):
    script = "import(process.argv[1]).then(m => process.stdout.write(m.renderMarkdown(JSON.parse(process.argv[2]))))"
    done = subprocess.run(["node", "-e", script, MODULE.as_uri(), json.dumps(markdown)],
                          capture_output=True, text=True, timeout=20)
    return done


@unittest.skipUnless(shutil.which("node"), "node is required to exercise the browser module")
class MarkdownRendererTests(unittest.TestCase):
    def test_indented_blockquote_marker_terminates(self):
        done = render("  > quoted")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("<blockquote", done.stdout)

    def test_html_is_escaped_and_unsafe_links_are_plain_text(self):
        done = render("<img src=x onerror=1> [bad](javascript:alert(1)) [rel](./x.md) [ok](https://example.com)")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("<img", done.stdout)
        self.assertNotIn("javascript:", done.stdout)
        self.assertNotIn('href="./x.md"', done.stdout)
        self.assertIn('href="https://example.com" target="_blank" rel="noopener noreferrer"', done.stdout)

    def test_heading_ids_cannot_collide_with_page_ids(self):
        done = render("## Version")
        self.assertIn('id="md-version"', done.stdout)

    def test_shipped_guide_renders(self):
        done = render(GUIDE.read_text(encoding="utf-8"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("<table", done.stdout)
