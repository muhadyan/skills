import os
import re
import unittest

from helpers import TempDirCase, write, write_jsonl

from vault_memory import migrate, notes, scrub


def slug(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def claude_memory(name, kind, desc, body, modified="2026-10-02T02:23:36.875Z"):
    return (f'---\nname: {name}\ndescription: "{desc}"\nmetadata:\n  node_type: memory\n  type: {kind}\n'
            f"  originSessionId: abc\n  modified: {modified}\n---\n\n{body}\n")


class ClaudeMigrateTest(TempDirCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.projects = self.tmp / "claude-projects"
        # real repo path has hyphens that the slug cannot tell apart from slashes
        self.repo = self.tmp / "Developer" / "be-mic-project"
        (self.repo / ".git").mkdir(parents=True)
        self.slug_dir = self.projects / slug(self.repo)
        write_jsonl(self.slug_dir / "s1.jsonl", [{"type": "permission-mode"},
                                                 {"type": "user", "cwd": str(self.repo / "cmd")}])
        mem = self.slug_dir / "memory"
        write(mem / "MEMORY.md", "# Memory Index\n\n- [Arch](arch.md) — layers\n")
        write(mem / "arch.md", claude_memory("arch", "project", "Clean architecture", "Handler -> UseCase"))
        write(mem / "role.md", claude_memory("role", "user", "Adyan is a backend dev", "Go + TS"))
        write(mem / "db.md", claude_memory("db", "reference", "Dev DB", "PGPASSWORD=s3cr3tPass psql"))

    def run_migrate(self, apply=True, codex=None):
        return migrate.run(self.vault, claude_projects=self.projects, codex_memories=codex,
                           apply=apply)

    def test_maps_project_from_transcript_cwd_and_converts(self):
        report = self.run_migrate()
        arch = self.vault / "memory" / "be-mic-project" / "arch.md"
        meta, body = notes.split(arch.read_text())
        self.assertEqual(meta, {"type": "memory", "kind": "project", "description": "Clean architecture",
                                "project": "be-mic-project", "updated": "2026-10-02"})
        self.assertEqual(body.strip(), "Handler -> UseCase")
        self.assertEqual(report.written, 3)

    def test_user_kind_goes_global(self):
        self.run_migrate()
        meta, _ = notes.split((self.vault / "memory" / "_global" / "role.md").read_text())
        self.assertEqual(meta["project"], "_global")
        self.assertFalse((self.vault / "memory" / "be-mic-project" / "role.md").exists())

    def test_secrets_scrubbed_and_reported(self):
        report = self.run_migrate()
        text = (self.vault / "memory" / "be-mic-project" / "db.md").read_text()
        self.assertNotIn("s3cr3tPass", text)
        self.assertIn(scrub.MARKER, text)
        self.assertEqual([(r.dest, len(r.hits)) for r in report.redactions],
                         [("memory/be-mic-project/db.md", 1)])

    def test_also_redact_literals(self):
        write(self.slug_dir / "memory" / "pg.md", claude_memory("pg", "project", "Local DB", "user `pg`/`hunter42`"))
        migrate.run(self.vault, claude_projects=self.projects, codex_memories=None, apply=True,
                    literals=("hunter42",))
        self.assertNotIn("hunter42", (self.vault / "memory" / "be-mic-project" / "pg.md").read_text())

    def test_dry_run_writes_nothing(self):
        report = self.run_migrate(apply=False)
        self.assertFalse((self.vault / "memory").exists())
        self.assertEqual(report.written, 3)

    def test_pointer_only_index_is_dropped_real_content_kept(self):
        self.run_migrate()
        self.assertFalse((self.vault / "memory" / "be-mic-project" / "project-notes.md").exists())
        write(self.slug_dir / "memory" / "MEMORY.md",
              "# Project Memory\n\n## Patterns\n- Domain entities have JSON tags\n- [Arch](arch.md) — x\n")
        self.run_migrate()
        meta, body = notes.split((self.vault / "memory" / "be-mic-project" / "project-notes.md").read_text())
        self.assertEqual(meta["kind"], "project")
        self.assertIn("Domain entities have JSON tags", body)

    def test_global_dedupe_keeps_newest(self):
        other = self.projects / slug(self.tmp / "Developer" / "other")
        (self.tmp / "Developer" / "other").mkdir()
        write_jsonl(other / "s.jsonl", [{"type": "user", "cwd": str(self.tmp / "Developer" / "other")}])
        write(other / "memory" / "role.md",
              claude_memory("role", "user", "Newer role", "TS", modified="2026-10-05T00:00:00Z"))
        report = self.run_migrate()
        meta, _ = notes.split((self.vault / "memory" / "_global" / "role.md").read_text())
        self.assertEqual(meta["description"], "Newer role")
        self.assertEqual(len(report.collisions), 1)

    def test_project_collision_keeps_both(self):
        # a second Claude folder (a subdirectory session) that maps to the same project
        sub = self.projects / slug(self.repo / "cmd")
        write_jsonl(sub / "s.jsonl", [{"type": "user", "cwd": str(self.repo / "cmd")}])
        write(sub / "memory" / "arch.md", claude_memory("arch", "project", "Different arch", "Other"))
        self.run_migrate()
        names = sorted(p.name for p in (self.vault / "memory" / "be-mic-project").glob("arch*.md"))
        self.assertEqual(len(names), 2)

    def test_identical_duplicate_written_once(self):
        sub = self.projects / slug(self.repo / "cmd")
        write_jsonl(sub / "s.jsonl", [{"type": "user", "cwd": str(self.repo / "cmd")}])
        write(sub / "memory" / "arch.md", (self.slug_dir / "memory" / "arch.md").read_text())
        self.run_migrate()
        self.assertEqual(len(list((self.vault / "memory" / "be-mic-project").glob("arch*.md"))), 1)

    def test_no_transcript_resolves_slug_on_disk(self):
        for f in self.slug_dir.glob("*.jsonl"):
            f.unlink()
        self.assertEqual(migrate.resolve_cwd(self.slug_dir), str(self.repo))

    def test_unresolvable_slug_falls_back_to_last_part(self):
        d = self.projects / "-nowhere-at-all-thing"
        write(d / "memory" / "x.md", claude_memory("x", "project", "d", "b"))
        self.assertEqual(migrate.resolve_cwd(d), "")
        report = self.run_migrate()
        self.assertTrue((self.vault / "memory" / "thing" / "x.md").exists())
        self.assertIn("-nowhere-at-all-thing", report.unresolved)


CODEX = """# Task Group: Admos Accounting production deployment topology

scope: Map how prod is deployed.
applies_to: cwd=/X/Developer/example/admos-accounting; reuse_rule=Reuse it.

## Task 1: Map topology, completed

- Uses PGPASSWORD=s3cr3tPass for the DB.

# Task Group: Google Sheets environment-variable setup

scope: Env vars in Sheets.
applies_to: cwd=/X/Documents/Codex/2026-07-28/if with BE cwd=be; reuse_rule=x

Body two.
"""


class CodexMigrateTest(TempDirCase, unittest.TestCase):
    def test_task_groups_become_notes(self):
        codex = self.tmp / "codex-memories"
        write(codex / "MEMORY.md", CODEX)
        os.utime(codex / "MEMORY.md", (1755900000, 1755900000))  # 2025-08-22/23
        report = migrate.run(self.vault, claude_projects=self.tmp / "none", codex_memories=codex,
                             apply=True)
        path = self.vault / "memory" / "admos-accounting" / \
            "codex-admos-accounting-production-deployment-topology.md"
        meta, body = notes.split(path.read_text())
        self.assertEqual(meta["description"], "Map how prod is deployed.")
        self.assertEqual(meta["kind"], "project")
        self.assertTrue(meta["updated"].startswith("2025-08-2"))
        self.assertIn("Map topology", body)
        self.assertNotIn("s3cr3tPass", body)
        self.assertTrue((self.vault / "memory" / "if" /
                         "codex-google-sheets-environment-variable-setup.md").exists())
        self.assertEqual(report.written, 2)


if __name__ == "__main__":
    unittest.main()
