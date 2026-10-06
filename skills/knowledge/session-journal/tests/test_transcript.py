import unittest

from helpers import TempDirCase, claude_rows, codex_rows, write_jsonl

from session_journal import transcript


class ClaudeParseTest(TempDirCase, unittest.TestCase):
    def test_keeps_prompts_and_replies_drops_tools_meta_and_sidechain(self):
        p = write_jsonl(self.tmp / "s.jsonl", claude_rows())
        t = transcript.parse(p)
        self.assertEqual(t.agent, "claude")
        self.assertEqual(t.session_id, "abcdef12-0000")
        self.assertEqual(t.cwd, "/home/me/Developer/example/app")
        self.assertEqual(t.date, "2026-10-07")
        self.assertEqual(t.prompts, ["Fix the login bug", "Now add a test"])
        text = transcript.condense(t)
        self.assertIn("Done step 1", text)
        for noise in ("TOOL OUTPUT NOISE", "secret thoughts", "meta prompt", "subagent task", "system-reminder"):
            self.assertNotIn(noise, text)
        self.assertTrue(t.interactive)

    def test_sdk_entrypoint_is_not_interactive(self):
        p = write_jsonl(self.tmp / "s.jsonl", claude_rows(entrypoint="sdk-cli"))
        self.assertFalse(transcript.parse(p).interactive)

    def test_slash_command_args_count_as_prompt(self):
        rows = claude_rows(prompts=("<command-name>/goal</command-name>\n<command-args>Ship the vault</command-args>",
                                    "go on"))
        t = transcript.parse(write_jsonl(self.tmp / "s.jsonl", rows))
        self.assertEqual(t.prompts[0], "/goal Ship the vault")

    def test_bad_lines_are_skipped(self):
        p = write_jsonl(self.tmp / "s.jsonl", claude_rows())
        p.write_text("not json\n" + p.read_text(), encoding="utf-8")
        self.assertEqual(len(transcript.parse(p).prompts), 2)


class CodexParseTest(TempDirCase, unittest.TestCase):
    def test_keeps_user_and_assistant_text_only(self):
        p = write_jsonl(self.tmp / ".codex" / "sessions" / "rollout-x.jsonl", codex_rows())
        t = transcript.parse(p)
        self.assertEqual(t.agent, "codex")
        self.assertEqual(t.session_id, "01a11323-6e57")
        self.assertEqual(t.prompts, ["Refactor the parser", "Run the tests"])
        text = transcript.condense(t)
        self.assertIn("ok 1", text)
        for noise in ("dev rules", "environment_context", "NOISE"):
            self.assertNotIn(noise, text)
        self.assertTrue(t.interactive)

    def test_exec_source_is_not_interactive(self):
        p = write_jsonl(self.tmp / "rollout-x.jsonl", codex_rows(source="exec"))
        self.assertFalse(transcript.parse(p).interactive)


class CondenseTest(TempDirCase, unittest.TestCase):
    def test_caps_long_transcripts_keeping_head_and_tail(self):
        prompts = [f"prompt {i} " + "x" * 3000 for i in range(60)]
        t = transcript.parse(write_jsonl(self.tmp / "s.jsonl", claude_rows(prompts=prompts)))
        text = transcript.condense(t, cap=20000)
        self.assertLessEqual(len(text), 20200)
        self.assertIn("prompt 0 ", text)
        self.assertIn("prompt 59 ", text)
        self.assertIn("[... middle of session cut ...]", text)


if __name__ == "__main__":
    unittest.main()
