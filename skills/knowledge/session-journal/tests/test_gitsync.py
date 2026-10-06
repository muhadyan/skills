import unittest

from helpers import TempDirCase, git, make_repo

from session_journal import gitsync


class GitSyncTest(TempDirCase, unittest.TestCase):
    def test_writes_commits_and_pushes(self):
        bare, clone = make_repo(self.tmp, "repo")
        changed = gitsync.sync_write(clone, {"a/b.md": "hello\n"}, "add b", self.cfg.state_dir)
        self.assertTrue(changed)
        self.assertEqual((clone / "a/b.md").read_text(), "hello\n")
        self.assertIn("add b", git(bare, "log", "--oneline", "-1"))

    def test_no_change_means_no_commit(self):
        _, clone = make_repo(self.tmp, "repo", {"a.md": "same\n"})
        before = git(clone, "rev-parse", "HEAD")
        self.assertFalse(gitsync.sync_write(clone, {"a.md": "same\n"}, "noop", self.cfg.state_dir))
        self.assertEqual(before, git(clone, "rev-parse", "HEAD"))

    def test_deletes_files(self):
        bare, clone = make_repo(self.tmp, "repo", {"k/old.md": "x\n"})
        self.assertTrue(gitsync.sync_write(clone, {}, "rm old", self.cfg.state_dir, deletes=["k/old.md"]))
        self.assertFalse((clone / "k/old.md").exists())
        self.assertNotIn("k/old.md", git(bare, "ls-tree", "-r", "--name-only", "main"))

    def test_pulls_remote_changes_first(self):
        bare, clone = make_repo(self.tmp, "repo")
        other = self.tmp / "other"
        git(self.tmp, "clone", "-q", str(bare), str(other))
        git(other, "config", "user.email", "o@example.com")
        git(other, "config", "user.name", "o")
        (other / "remote.md").write_text("r\n")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "remote")
        git(other, "push", "-q")
        gitsync.sync_write(clone, {"local.md": "l\n"}, "local", self.cfg.state_dir)
        files = git(bare, "ls-tree", "-r", "--name-only", "main")
        self.assertIn("remote.md", files)
        self.assertIn("local.md", files)

    def test_unreachable_remote_keeps_local_commit(self):
        bare, clone = make_repo(self.tmp, "repo")
        git(clone, "remote", "set-url", "origin", str(self.tmp / "gone.git"))
        self.assertTrue(gitsync.sync_write(clone, {"a.md": "x\n"}, "offline", self.cfg.state_dir))
        self.assertIn("offline", git(clone, "log", "--oneline", "-1"))
        self.assertFalse((clone / ".git" / "rebase-merge").exists())

    def test_refuses_to_write_on_another_branch_or_detached_head(self):
        _, clone = make_repo(self.tmp, "repo")
        git(clone, "checkout", "-q", "-b", "feature")
        with self.assertRaises(gitsync.GitError):
            gitsync.sync_write(clone, {"a.md": "x\n"}, "nope", self.cfg.state_dir)
        self.assertFalse((clone / "a.md").exists())
        git(clone, "checkout", "-q", "--detach")
        with self.assertRaises(gitsync.GitError):
            gitsync.sync_write(clone, {"a.md": "x\n"}, "nope", self.cfg.state_dir)

    def test_user_edits_are_never_stashed_or_overwritten(self):
        bare, clone = make_repo(self.tmp, "repo", {"mine.md": "v1\n"})
        other = self.tmp / "other"
        git(self.tmp, "clone", "-q", str(bare), str(other))
        git(other, "config", "user.email", "o@example.com")
        git(other, "config", "user.name", "o")
        (other / "mine.md").write_text("remote v2\n")
        git(other, "commit", "-qam", "remote edit")
        git(other, "push", "-q")
        (clone / "mine.md").write_text("local unsaved edit\n")
        self.assertTrue(gitsync.sync_write(clone, {"note.md": "n\n"}, "note", self.cfg.state_dir))
        self.assertEqual((clone / "mine.md").read_text(), "local unsaved edit\n")
        self.assertEqual(git(clone, "stash", "list"), "")
        self.assertFalse((clone / ".git" / "rebase-merge").exists())

    def test_never_touches_a_rebase_someone_else_started(self):
        _, clone = make_repo(self.tmp, "repo")
        (clone / ".git" / "rebase-merge").mkdir()
        self.assertTrue(gitsync.sync_write(clone, {"a.md": "x\n"}, "m", self.cfg.state_dir))
        self.assertTrue((clone / ".git" / "rebase-merge").exists())

    def test_precheck_runs_under_the_lock_and_can_cancel(self):
        _, clone = make_repo(self.tmp, "repo")
        self.assertFalse(gitsync.sync_write(clone, {"a.md": "x\n"}, "m", self.cfg.state_dir, precheck=lambda: False))
        self.assertFalse((clone / "a.md").exists())

    def test_refuses_paths_outside_repo(self):
        _, clone = make_repo(self.tmp, "repo")
        with self.assertRaises(ValueError):
            gitsync.sync_write(clone, {"../escape.md": "x"}, "bad", self.cfg.state_dir)

    def test_works_without_remote(self):
        clone = self.tmp / "plain"
        clone.mkdir()
        git(clone, "init", "-q", "-b", "main")
        git(clone, "config", "user.email", "t@example.com")
        git(clone, "config", "user.name", "t")
        self.assertTrue(gitsync.sync_write(clone, {"a.md": "x\n"}, "first", self.cfg.state_dir))
        self.assertIn("first", git(clone, "log", "--oneline"))


if __name__ == "__main__":
    unittest.main()
