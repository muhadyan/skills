import io
import json
import os
import unittest
from unittest import mock

from helpers import TempDirCase, memory_note, write

from vault_memory import hooks


class HookTest(TempDirCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.proj = self.tmp / "Developer" / "app"
        (self.proj / ".git").mkdir(parents=True)
        write(self.vault / "memory" / "_global" / "tz.md", memory_note("user", "Timezone WIB", "b",
                                                                       project="_global"))
        write(self.vault / "memory" / "app" / "x.md", memory_note("project", "App fact", "b"))

    def call(self, event, payload, env=None):
        out = io.StringIO()
        with mock.patch.dict(os.environ, env or {}), mock.patch.object(hooks, "spawn") as spawn:
            hooks.handle(event, io.StringIO(json.dumps(payload)), self.cfg, out=out)
        return out.getvalue(), spawn

    def test_start_injects_index(self):
        out, spawn = self.call("start", {"cwd": str(self.proj)})
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn(str(self.vault / "memory"), ctx)
        self.assertIn("memory/app/", ctx)
        self.assertIn("- [[tz]] (user) Timezone WIB", ctx)
        self.assertIn("- [[x]] (project) App fact", ctx)
        spawn.assert_not_called()

    def test_start_stays_inline_and_keeps_feedback_when_capped(self):
        """Claude Code inlines hook context only under ~10,000 characters; a
        larger block is saved to a file and only a 2 KB preview reaches the
        agent, which then misses every note past it."""
        for i in range(150):
            write(self.vault / "memory" / "app" / f"p{i:03d}.md",
                  memory_note("project", "日本語の説明" * 12, "b", updated="2026-10-07"))
        write(self.vault / "memory" / "app" / "no-docker.md",
              memory_note("feedback", "Never use Docker", "b", updated="2020-01-01"))
        out, _ = self.call("start", {"cwd": str(self.proj)})
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertLess(len(ctx), 10_000)
        self.assertIn("- [[no-docker]] (feedback) Never use Docker", ctx)
        self.assertIn("more not shown", ctx)

    def test_start_for_new_project_still_says_where_to_write(self):
        new = self.tmp / "Developer" / "fresh"
        new.mkdir()
        out, _ = self.call("start", {"cwd": str(new)})
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("memory/fresh/", ctx)
        self.assertIn("(no notes yet)", ctx)

    def test_end_spawns_commit(self):
        _, spawn = self.call("end", {"cwd": str(self.proj)})
        spawn.assert_called_once_with(self.cfg, ["commit"])

    def test_skips_subagents_and_children(self):
        for payload, env in (({"cwd": str(self.proj), "agent_id": "a1"}, {}),
                             ({"cwd": str(self.proj)}, {"VAULT_MEMORY": "1"}),
                             ({"cwd": str(self.proj)}, {"SESSION_JOURNAL": "1"})):
            out, spawn = self.call("end", payload, env)
            spawn.assert_not_called()
            out, _ = self.call("start", payload, env)
            self.assertEqual(out, "")

    def test_bad_stdin_is_ignored(self):
        out = io.StringIO()
        hooks.handle("start", io.StringIO("not json"), self.cfg, out=out)
        self.assertEqual(out.getvalue(), "")

    def test_safe_handle_never_raises(self):
        def boom():
            raise RuntimeError("no config")
        with mock.patch("sys.stdin", io.StringIO("{}")), \
                mock.patch.object(hooks, "LOG_FALLBACK", self.tmp / "log.txt"):
            self.assertEqual(hooks.safe_handle("start", boom), 0)
        self.assertIn("no config", (self.tmp / "log.txt").read_text())


if __name__ == "__main__":
    unittest.main()
