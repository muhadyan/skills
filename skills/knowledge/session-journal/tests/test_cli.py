import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import TempDirCase

from session_journal import config

JOURNAL = Path(__file__).resolve().parents[1] / "scripts" / "journal.py"


class ConfigTest(TempDirCase, unittest.TestCase):
    def test_load_reads_values_and_defaults(self):
        f = self.tmp / "config.env"
        f.write_text(f'# comment\nVAULT="{self.vault}"\nBRAND_SAFE_ROOTS=/a:/b\nMIN_PROMPTS=3\n', encoding="utf-8")
        cfg = config.load(f)
        self.assertEqual(cfg.vault, self.vault)
        self.assertEqual(cfg.brand_safe_roots, (Path("/a"), Path("/b")))
        self.assertEqual(cfg.min_prompts, 3)
        self.assertEqual(cfg.model, config.DEFAULT_MODEL)
        self.assertIsNone(cfg.export_repo)
        self.assertEqual(cfg.denylist, self.vault / "_meta" / "nda-denylist.txt")

    def test_inline_comments_are_stripped(self):
        f = self.tmp / "config.env"
        f.write_text(f"VAULT={self.vault}   # a git clone\nMODEL=m # c\n", encoding="utf-8")
        cfg = config.load(f)
        self.assertEqual((cfg.vault, cfg.model), (self.vault, "m"))

    def test_missing_file_or_vault_is_an_error(self):
        with self.assertRaises(config.ConfigError):
            config.load(self.tmp / "nope.env")
        f = self.tmp / "config.env"
        f.write_text("MODEL=x\n", encoding="utf-8")
        with self.assertRaises(config.ConfigError):
            config.load(f)


class StateTest(TempDirCase, unittest.TestCase):
    def test_concurrent_writers_lose_no_updates(self):
        import threading
        from session_journal import state
        paths = [self.tmp / f"t{i}.jsonl" for i in range(40)]
        threads = [threading.Thread(target=state.mark_done, args=(self.cfg, p, 1.0)) for p in paths]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(state.load(self.cfg)), 40)


class CliTest(TempDirCase, unittest.TestCase):
    def run_cli(self, *args, stdin="", **env):
        f = self.tmp / "config.env"
        f.write_text(f"VAULT={self.vault}\nSTATE_DIR={self.tmp / 'state'}\n"
                     f"CLAUDE_PROJECTS={self.tmp / 'none'}\nCODEX_SESSIONS={self.tmp / 'none'}\n", encoding="utf-8")
        full_env = {**os.environ, "SESSION_JOURNAL_CONFIG": str(f), **env}
        return subprocess.run([sys.executable, str(JOURNAL), *args], input=stdin, capture_output=True,
                              text=True, env=full_env, timeout=30)

    def test_hook_with_guard_is_silent_and_exits_zero(self):
        proc = self.run_cli("hook", "end", "--agent", "claude", stdin="{}", SESSION_JOURNAL="1")
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))

    def test_hook_never_fails_even_without_config(self):
        proc = self.run_cli("hook", "start", "--agent", "codex", stdin="{}",
                            SESSION_JOURNAL_CONFIG=str(self.tmp / "missing.env"))
        self.assertEqual(proc.returncode, 0)

    def test_start_hook_prints_context_json(self):
        proc = self.run_cli("hook", "start", "--agent", "claude", stdin=json.dumps({"cwd": str(self.tmp)}))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(str(self.vault), ctx)

    def test_context_and_sweep_and_export_commands(self):
        self.assertIn("Session journal is on", self.run_cli("context", str(self.tmp)).stdout)
        self.assertIn("sweep: 0 summarized", self.run_cli("sweep", "--max", "1").stdout)
        self.assertIn("export: not configured", self.run_cli("export").stdout)


if __name__ == "__main__":
    unittest.main()
