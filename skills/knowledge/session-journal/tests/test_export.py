import dataclasses
import json
import unittest

from helpers import TempDirCase, git, make_repo

from session_journal import export


def vault_note(title, safe=True, angle="Cerita singkat.", lessons="- pelajaran", date="2026-10-07"):
    return (f"---\ntype: session\ntitle: {json.dumps(title)}\ndate: {date}\nagent: claude\n"
            f"project: secret-project\ncwd: /secret/path\ntags: [\"go\"]\nbrand_safe: {str(safe).lower()}\n---\n"
            f"## Done\n- did things\n\n## Lessons\n{lessons}\n\n## Post angle\n{angle}\n")


RULES = {"rules": [
    {"id": "me-employer", "kind": "regex", "category": "nda-nama", "patterns": ["\\bglobex\\b"]},
    {"id": "me-price", "kind": "regex", "category": "harga", "patterns": ["\\brp\\d"]},
]}


class ExportTest(TempDirCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.bare, self.brand = make_repo(self.tmp, "brand", {"rules.json": json.dumps(RULES)})
        self.cfg = dataclasses.replace(self.cfg, export_repo=self.brand)

    def put(self, name, text):
        p = self.vault / "sessions" / "2026" / "10" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def test_only_brand_safe_clean_notes_are_exported_without_private_fields(self):
        self.put("2026-10-07-claude-aaaa1111.md", vault_note("Safe one"))
        self.put("2026-10-07-claude-bbbb2222.md", vault_note("Unsafe", safe=False))
        self.put("2026-10-07-claude-cccc3333.md", vault_note("Leak", angle="Kerja di Acme Corp dulu."))
        self.put("2026-10-07-claude-dddd4444.md", vault_note("Leak2", lessons="- client Globex asked"))
        result = export.run(self.cfg)
        self.assertEqual(result.exported, ["2026-10-07-claude-aaaa1111.md"])
        self.assertEqual(sorted(result.blocked), ["2026-10-07-claude-cccc3333.md", "2026-10-07-claude-dddd4444.md"])
        files = git(self.bare, "ls-tree", "-r", "--name-only", "main").split()
        self.assertIn("knowledge/2026-10-07-claude-aaaa1111.md", files)
        self.assertIn("knowledge/INDEX.md", files)
        self.assertEqual(len([f for f in files if f.startswith("knowledge/")]), 2)
        text = (self.brand / "knowledge" / "2026-10-07-claude-aaaa1111.md").read_text()
        self.assertIn("Cerita singkat.", text)
        for private in ("secret-project", "/secret/path", "did things"):
            self.assertNotIn(private, text)
        index = (self.brand / "knowledge" / "INDEX.md").read_text()
        self.assertIn("Safe one", index)
        self.assertNotIn("Unsafe", index)

    def test_unflagged_note_is_removed_on_next_export(self):
        self.put("2026-10-07-claude-aaaa1111.md", vault_note("Safe one"))
        export.run(self.cfg)
        self.put("2026-10-07-claude-aaaa1111.md", vault_note("Safe one", safe=False))
        export.run(self.cfg)
        self.assertNotIn("aaaa1111", git(self.bare, "ls-tree", "-r", "--name-only", "main"))

    def test_note_without_post_angle_is_skipped(self):
        self.put("2026-10-07-claude-aaaa1111.md", vault_note("No angle", angle=""))
        self.assertEqual(export.run(self.cfg).exported, [])

    def test_no_export_repo_is_a_noop(self):
        cfg = dataclasses.replace(self.cfg, export_repo=None)
        self.assertIsNone(export.run(cfg))

    def test_bad_denylist_regex_fails_closed(self):
        self.cfg.denylist.write_text("([unclosed\n", encoding="utf-8")
        self.put("2026-10-07-claude-aaaa1111.md", vault_note("Safe one"))
        with self.assertRaises(export.ExportError):
            export.run(self.cfg)


if __name__ == "__main__":
    unittest.main()
