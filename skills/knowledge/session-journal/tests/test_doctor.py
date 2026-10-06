import dataclasses
import json
import unittest

from helpers import TempDirCase, git, make_repo

from session_journal import doctor, state

J = "python3 ~/.claude/skills/session-journal/scripts/journal.py"


class DoctorTest(TempDirCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.bare, vault = make_repo(self.tmp, "vault2", {"_meta/nda-denylist.txt": "acme\n"})
        self.cfg = dataclasses.replace(self.cfg, vault=vault, denylist=vault / "_meta" / "nda-denylist.txt",
                                       claude_settings=self.tmp / "settings.json",
                                       codex_hooks=self.tmp / "hooks.json", codex_config=self.tmp / "config.toml")
        hooks = {"hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "orca"}]},
                             {"hooks": [{"type": "command", "command": f"{J} hook start --agent X"}]}],
            "SessionEnd": [{"hooks": [{"type": "command", "command": f"{J} hook end --agent X"}]}]}}
        self.cfg.claude_settings.write_text(json.dumps(hooks).replace("X", "claude"))
        self.cfg.codex_hooks.write_text(json.dumps(hooks).replace("X", "codex"))
        self.cfg.codex_config.write_text(
            f'[hooks.state."{self.cfg.codex_hooks}:session_start:1:0"]\ntrusted_hash = "sha256:a"\n'
            f'[hooks.state."{self.cfg.codex_hooks}:session_end:0:0"]\ntrusted_hash = "sha256:b"\n')

    def levels(self):
        return {name: level for level, name, _ in doctor.checks(self.cfg)}

    def test_healthy_setup_is_all_ok(self):
        self.assertEqual(set(self.levels().values()), {"OK"}, doctor.checks(self.cfg))

    def test_untrusted_codex_hook_fails(self):
        self.cfg.codex_config.write_text("")
        self.assertEqual(self.levels()["codex hooks"], "FAIL")

    def test_missing_claude_hook_fails(self):
        self.cfg.claude_settings.write_text(json.dumps({"hooks": {}}))
        self.assertEqual(self.levels()["claude hooks"], "FAIL")

    def test_unpushed_notes_and_wrong_branch(self):
        git(self.cfg.vault, "remote", "set-url", "origin", str(self.tmp / "gone.git"))
        (self.cfg.vault / "n.md").write_text("x\n")
        git(self.cfg.vault, "add", "n.md")
        git(self.cfg.vault, "commit", "-qm", "n")
        self.assertEqual(self.levels()["vault sync"], "WARN")
        self.assertIn("1 unpushed", doctor.sync_problem(self.cfg))
        git(self.cfg.vault, "checkout", "-q", "-b", "feature")
        self.assertEqual(self.levels()["vault"], "FAIL")

    def test_empty_denylist_fails(self):
        self.cfg.denylist.write_text("# nothing\n")
        self.assertEqual(self.levels()["denylist"], "FAIL")

    def test_given_up_transcripts_warn(self):
        p = self.tmp / "t.jsonl"
        for _ in range(state.MAX_FAILS):
            state.mark_failed(self.cfg, p, 1.0)
        self.assertEqual(self.levels()["failures"], "WARN")

    def test_report_exit_code(self):
        self.assertEqual(doctor.run(self.cfg, out=open("/dev/null", "w")), 0)
        self.cfg.codex_config.write_text("")
        self.assertEqual(doctor.run(self.cfg, out=open("/dev/null", "w")), 1)


if __name__ == "__main__":
    unittest.main()
