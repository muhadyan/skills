import dataclasses
import json
import unittest

from helpers import TempDirCase, git, make_repo

from session_journal import export


def vault_note(title, safe=True, angle="Cerita singkat.", lessons="- pelajaran", date="2026-10-07",
               tags='["go"]', cwd=None):
    cwd = cwd or "/secret/path"
    return (f"---\ntype: session\ntitle: {json.dumps(title)}\ndate: {date}\nagent: claude\n"
            f"project: secret-project\ncwd: {json.dumps(cwd)}\ntags: {tags}\nbrand_safe: {str(safe).lower()}\n---\n"
            f"## Done\n- did things\n\n## Lessons\n{lessons}\n\n## Post angle\n{angle}\n")


RULES = {"rules": [
    {"id": "me-employer", "kind": "regex", "category": "nda-nama", "patterns": ["\\bglobex\\b"]},
    {"id": "me-literal", "kind": "regex", "category": "nda-nama", "literal": True, "patterns": ["a.b (corp)"]},
    {"id": "me-metric", "kind": "regex", "category": "nda-angka", "pattern": "\\d+\\s*pengguna"},
    {"id": "me-price", "kind": "regex", "category": "harga", "patterns": ["\\brp\\d"]},
]}


class ExportTest(TempDirCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.bare, self.brand = make_repo(self.tmp, "brand", {"rules.json": json.dumps(RULES)})
        self.cfg = dataclasses.replace(self.cfg, export_repo=self.brand)
        self.safe_cwd = str(self.tmp / "personal" / "app")
        (self.vault / "sessions").mkdir()

    def put(self, name, text):
        if "/secret/path" in text:
            text = text.replace('"/secret/path"', json.dumps(self.safe_cwd))
        p = self.vault / "sessions" / "2026" / "10" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def test_only_brand_safe_clean_notes_are_exported_without_private_fields(self):
        self.put("2026-10-07-claude-aaaa1111.md", vault_note("Safe one"))
        self.put("2026-10-07-claude-bbbb2222.md", vault_note("Unsafe", safe=False))
        self.put("2026-10-07-claude-cccc3333.md", vault_note("Leak", angle="Kerja di Acme Corp dulu."))
        self.put("2026-10-07-claude-dddd4444.md", vault_note("Leak2 for Globex"))
        result = export.run(self.cfg)
        self.assertEqual(result.exported, ["2026-10-07-claude-aaaa1111.md"])
        self.assertEqual(sorted(result.blocked), ["2026-10-07-claude-cccc3333.md", "2026-10-07-claude-dddd4444.md"])
        files = git(self.bare, "ls-tree", "-r", "--name-only", "main").split()
        self.assertIn("knowledge/2026-10-07-claude-aaaa1111.md", files)
        self.assertIn("knowledge/INDEX.md", files)
        self.assertEqual(len([f for f in files if f.startswith("knowledge/")]), 2)
        text = (self.brand / "knowledge" / "2026-10-07-claude-aaaa1111.md").read_text()
        self.assertIn("Cerita singkat.", text)
        for private in ("secret-project", self.safe_cwd, "did things", "pelajaran"):
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

    def test_tags_are_gate_checked(self):
        self.put("2026-10-07-claude-aaaa1111.md", vault_note("Safe", tags='["globex-etl"]'))
        self.assertEqual(export.run(self.cfg).blocked, ["2026-10-07-claude-aaaa1111.md"])

    def test_work_cwd_is_rechecked_even_if_flag_is_true(self):
        self.put("2026-10-07-claude-aaaa1111.md", vault_note("Safe", cwd=str(self.tmp / "work" / "x")))
        self.assertEqual(export.run(self.cfg).exported, [])

    def test_missing_or_empty_denylist_fails_closed(self):
        self.put("2026-10-07-claude-aaaa1111.md", vault_note("Safe one"))
        self.cfg.denylist.write_text("# only comments\n", encoding="utf-8")
        with self.assertRaises(export.ExportError):
            export.run(self.cfg)
        self.cfg.denylist.unlink()
        with self.assertRaises(export.ExportError):
            export.run(self.cfg)

    def test_hand_written_knowledge_files_are_kept(self):
        (self.brand / "knowledge").mkdir()
        (self.brand / "knowledge" / "mine.md").write_text("# my own note\n", encoding="utf-8")
        self.put("2026-10-07-claude-aaaa1111.md", vault_note("Safe one"))
        export.run(self.cfg)
        self.assertTrue((self.brand / "knowledge" / "mine.md").exists())

    def test_mass_delete_needs_force(self):
        for i in range(6):
            self.put(f"2026-10-07-claude-{i}aaa1111.md", vault_note(f"Safe {i}"))
        export.run(self.cfg)
        for f in (self.vault / "sessions").rglob("*.md"):
            f.write_text(f.read_text().replace("brand_safe: true", "brand_safe: false"))
        with self.assertRaises(export.ExportError):
            export.run(self.cfg)
        self.assertEqual(export.run(self.cfg, force=True).exported, [])

    def test_missing_sessions_folder_fails_closed(self):
        (self.vault / "sessions").rmdir()
        with self.assertRaises(export.ExportError):
            export.run(self.cfg)

    def test_singular_pattern_and_literal_rules_are_enforced(self):
        self.put("2026-10-07-claude-aaaa1111.md", vault_note("Safe", angle="Ada tujuh pengguna baru, lumayan."))
        self.put("2026-10-07-claude-bbbb2222.md", vault_note("Kerja bareng a.b (corp)"))
        self.put("2026-10-07-claude-cccc3333.md", vault_note("Kerja bareng axb (corp)"))
        result = export.run(self.cfg)
        self.assertEqual(result.blocked, ["2026-10-07-claude-bbbb2222.md"])  # literal: axb is not a.b
        self.put("2026-10-07-claude-aaaa1111.md", vault_note("Safe", angle="Ada 7 pengguna baru, lumayan."))
        self.assertIn("2026-10-07-claude-aaaa1111.md", export.run(self.cfg).blocked)

    def test_nda_rule_without_patterns_fails_closed(self):
        (self.brand / "rules.json").write_text(json.dumps({"rules": [
            {"id": "x", "kind": "regex", "category": "nda-x"}]}), encoding="utf-8")
        self.put("2026-10-07-claude-aaaa1111.md", vault_note("Safe one"))
        with self.assertRaises(export.ExportError):
            export.run(self.cfg)

    def test_post_angle_content_checks(self):
        bad = {"b1": "Cek https://evil.example ya.", "b2": "Hemat 25 jam sebulan.", "b3": "Follow @someone dulu.",
               "b4": "Harganya Rp5 aja.", "b5": "x" * 600, "b6": "Token sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAA bocor."}
        for i, angle in enumerate(bad.values()):
            self.put(f"2026-10-07-claude-{i}bad0000.md", vault_note(f"T{i}", angle=angle))
        self.put("2026-10-07-claude-good0000.md", vault_note("Good", angle="Aku pindahin 3 fitur jadi satu chat."))
        result = export.run(self.cfg)
        self.assertEqual(result.exported, ["2026-10-07-claude-good0000.md"])
        self.assertEqual(len(result.blocked), len(bad))

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
