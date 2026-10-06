import unittest

from helpers import TempDirCase, memory_note, write

from vault_memory import notes


class FrontmatterTest(unittest.TestCase):
    def test_split_flat_and_nested(self):
        text = ('---\nname: a\ndescription: "Has: colon and \\"quotes\\""\nmetadata:\n'
                '  type: feedback\n  modified: 2026-10-02T02:23:36.875Z\n---\n\nBody\n')
        meta, body = notes.split(text)
        self.assertEqual(meta["description"], 'Has: colon and "quotes"')
        self.assertEqual(meta["metadata"], {"type": "feedback", "modified": "2026-10-02T02:23:36.875Z"})
        self.assertEqual(body, "Body\n")

    def test_split_without_frontmatter(self):
        self.assertEqual(notes.split("just text\n"), ({}, "just text\n"))

    def test_crlf(self):
        meta, body = notes.split("---\r\ntype: memory\r\nkind: user\r\n---\r\n\r\nBody\r\n")
        self.assertEqual(meta, {"type": "memory", "kind": "user"})
        self.assertEqual(body, "Body\n")

    def test_render_quotes_yaml_ambiguous_scalars(self):
        for value in ("yes", "No", "null", "~", "true", "off", "42", "3.5"):
            text = notes.render({"description": value}, "")
            self.assertIn(f'description: "{value}"', text)
            self.assertEqual(notes.split(text)[0]["description"], value)

    def test_render_roundtrip(self):
        meta = {"type": "memory", "kind": "user", "description": 'a: "b"', "project": "_global",
                "updated": "2026-10-07"}
        text = notes.render(meta, "Fact.\n")
        self.assertEqual(notes.split(text), (meta, "Fact.\n"))
        self.assertTrue(text.startswith("---\ntype: memory\nkind: user\n"))


class ProjectNameTest(TempDirCase, unittest.TestCase):
    def test_git_toplevel_with_hyphens(self):
        repo = self.tmp / "Developer" / "be-mic-project"
        (repo / ".git").mkdir(parents=True)
        (repo / "cmd" / "app").mkdir(parents=True)
        self.assertEqual(notes.project_name(str(repo / "cmd" / "app")), "be-mic-project")

    def test_no_git_uses_last_folder(self):
        d = self.tmp / "example" / "adyan-personal"
        d.mkdir(parents=True)
        self.assertEqual(notes.project_name(str(d)), "adyan-personal")

    def test_empty(self):
        self.assertEqual(notes.project_name(""), "")


class IndexTest(TempDirCase, unittest.TestCase):
    def _note(self, project, name, kind="project", desc="d", updated="2026-10-01"):
        write(self.vault / "memory" / project / f"{name}.md",
              memory_note(kind, desc, "body", updated=updated, project=project))

    def test_global_first_then_project_newest_first(self):
        self._note("_global", "tz", "user", "Timezone WIB", "2026-08-01")
        self._note("app", "old", desc="Old fact", updated="2026-09-01")
        self._note("app", "new", "feedback", "New fact", "2026-10-05")
        self._note("other", "x", desc="Other project")
        lines = notes.index_lines(self.vault, "app")
        self.assertEqual(lines, [
            "Global (memory/_global/):",
            "- [[tz]] (user) Timezone WIB",
            "Project app (memory/app/):",
            "- [[new]] (feedback) New fact",
            "- [[old]] (project) Old fact",
        ])

    def test_ignores_non_memory_files(self):
        write(self.vault / "memory" / "app" / "scratch.md", "no frontmatter\n")
        self._note("app", "real")
        self.assertEqual(notes.index_lines(self.vault, "app")[-1], "- [[real]] (project) d")
        self.assertNotIn("scratch", "\n".join(notes.index_lines(self.vault, "app")))

    def test_non_string_description(self):
        write(self.vault / "memory" / "app" / "odd.md",
              "---\ntype: memory\nkind: project\ndescription: >\n  a: b\nupdated: 2026-10-01\n---\n\nx\n")
        self.assertEqual(notes.index_lines(self.vault, "app")[-1], "- [[odd]] (project) ")

    def test_missing_folders(self):
        self.assertEqual(notes.index_lines(self.vault, "app"), [])

    def test_cap_lines_and_bytes(self):
        for i in range(30):
            self._note("app", f"n{i:02d}", desc="x" * 50, updated=f"2026-09-{i + 1:02d}")
        lines = notes.cap(notes.index_lines(self.vault, "app"), max_lines=10, max_bytes=10_000)
        self.assertEqual(len(lines), 10)
        self.assertIn("more", lines[-1])
        small = notes.cap(notes.index_lines(self.vault, "app"), max_lines=200, max_bytes=300)
        self.assertLessEqual(len("\n".join(small).encode()), 300)
        self.assertIn("more", small[-1])


if __name__ == "__main__":
    unittest.main()
