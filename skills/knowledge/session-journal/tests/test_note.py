import unittest

from helpers import TempDirCase, claude_rows, write_jsonl

from session_journal import note, transcript


def sample_data(**over):
    data = {"skip": False, "title": "Fix login bug", "tags": ["go", "auth"],
            "done": ["Fixed the token check"], "lessons": ["Check expiry before signature"],
            "brand_safe": True, "post_angle": "Pernah login error gara-gara token kadaluarsa."}
    data.update(over)
    return data


class NoteTest(TempDirCase, unittest.TestCase):
    def transcript(self, cwd):
        return transcript.parse(write_jsonl(self.tmp / "s.jsonl", claude_rows(cwd=str(cwd))))

    def test_under_roots_is_path_based_and_ignores_prefix_tricks(self):
        roots = (self.tmp / "personal",)
        self.assertTrue(note.under_roots(str(self.tmp / "personal" / "app"), roots))
        self.assertTrue(note.under_roots(str(self.tmp / "personal"), roots))
        self.assertFalse(note.under_roots(str(self.tmp / "personal2" / "app"), roots))
        self.assertFalse(note.under_roots(str(self.tmp / "work"), roots))
        self.assertFalse(note.under_roots("", roots))

    def test_render_brand_safe_note(self):
        t = self.transcript(self.tmp / "personal" / "app")
        md = note.render(t, sample_data(), eligible=True)
        meta, body = note.split(md)
        self.assertEqual(meta["type"], "session")
        self.assertIs(meta["brand_safe"], True)
        self.assertEqual(meta["project"], "app")
        self.assertEqual(meta["tags"], ["go", "auth"])
        self.assertIn("## Post angle", body)
        self.assertIn("token kadaluarsa", body)
        self.assertIn("- Check expiry before signature", body)

    def test_work_path_is_never_brand_safe_and_has_no_post_angle(self):
        t = self.transcript(self.tmp / "work" / "app")
        md = note.render(t, sample_data(brand_safe=True), eligible=False)
        meta, body = note.split(md)
        self.assertIs(meta["brand_safe"], False)
        self.assertNotIn("Post angle", body)
        self.assertNotIn("kadaluarsa", body)

    def test_model_can_downgrade_brand_safe(self):
        t = self.transcript(self.tmp / "personal" / "app")
        meta, body = note.split(note.render(t, sample_data(brand_safe=False), eligible=True))
        self.assertIs(meta["brand_safe"], False)
        self.assertNotIn("Post angle", body)

    def test_secrets_are_redacted(self):
        t = self.transcript(self.tmp / "personal" / "app")
        data = sample_data(done=["Set key sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAA and ghp_0123456789abcdefABCDEF0123456789abcd",
                                 "password=hunter2xyz"])
        md = note.render(t, data, eligible=True)
        self.assertNotIn("sk-ant-api03-AAAA", md)
        self.assertNotIn("ghp_0123", md)
        self.assertNotIn("hunter2xyz", md)
        self.assertIn("[REDACTED]", md)

    def test_path_uses_date_agent_and_short_id(self):
        t = self.transcript(self.tmp / "personal" / "app")
        self.assertEqual(note.rel_path(t), "sessions/2026/10/2026-10-07-claude-abcdef12.md")

    def test_split_reads_obsidian_yaml_lists_and_bools(self):
        md = "---\ntitle: Hello\nbrand_safe: true\nlocked: false\ntags:\n  - a\n  - b\n---\nbody\n"
        meta, body = note.split(md)
        self.assertEqual(meta, {"title": "Hello", "brand_safe": True, "locked": False, "tags": ["a", "b"]})
        self.assertEqual(body, "body\n")

    def test_sections(self):
        body = "## Done\n- a\n\n## Lessons\n- l1\n- l2\n\n## Post angle\nCerita.\n"
        self.assertEqual(note.section(body, "Lessons"), "- l1\n- l2")
        self.assertEqual(note.section(body, "Post angle"), "Cerita.")
        self.assertEqual(note.section(body, "Missing"), "")


if __name__ == "__main__":
    unittest.main()
