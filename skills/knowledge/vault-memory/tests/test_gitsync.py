import threading
import unittest

from helpers import TempDirCase, git, make_repo, write

from vault_memory import gitsync


class CommitTest(TempDirCase, unittest.TestCase):
    def test_commits_and_pushes_only_memory(self):
        bare, clone = make_repo(self.tmp, "vault")
        write(clone / "memory" / "app" / "a.md", "a\n")
        write(clone / "sessions" / "s.md", "journal owns this\n")
        self.assertEqual(gitsync.commit_memory(clone, self.cfg.lock_dir), 1)
        tracked = git(bare, "ls-tree", "-r", "--name-only", "main")
        self.assertIn("memory/app/a.md", tracked)
        self.assertNotIn("sessions/s.md", tracked)
        self.assertIn("vault: memory (1 file)", git(bare, "log", "--oneline", "-1"))
        self.assertIn("sessions/s.md", git(clone, "status", "--porcelain", "-uall"))

    def test_deletes_are_committed(self):
        bare, clone = make_repo(self.tmp, "vault", {"memory/app/old.md": "x\n"})
        (clone / "memory" / "app" / "old.md").unlink()
        self.assertEqual(gitsync.commit_memory(clone, self.cfg.lock_dir), 1)
        self.assertNotIn("old.md", git(bare, "ls-tree", "-r", "--name-only", "main"))

    def test_nothing_to_commit(self):
        _, clone = make_repo(self.tmp, "vault")
        self.assertEqual(gitsync.commit_memory(clone, self.cfg.lock_dir), 0)
        write(clone / "memory" / "app" / "a.md", "a\n")
        gitsync.commit_memory(clone, self.cfg.lock_dir)
        self.assertEqual(gitsync.commit_memory(clone, self.cfg.lock_dir), 0)

    def test_pulls_remote_first_with_dirty_tree(self):
        bare, clone = make_repo(self.tmp, "vault")
        other = self.tmp / "other"
        git(self.tmp, "clone", "-q", str(bare), str(other))
        git(other, "config", "user.email", "o@example.com")
        git(other, "config", "user.name", "o")
        write(other / "sessions" / "remote.md", "r\n")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "journal note")
        git(other, "push", "-q")
        write(clone / "README.md", "user is editing this in Obsidian\n")
        write(clone / "memory" / "app" / "a.md", "a\n")
        gitsync.commit_memory(clone, self.cfg.lock_dir)
        files = git(bare, "ls-tree", "-r", "--name-only", "main")
        self.assertIn("sessions/remote.md", files)
        self.assertIn("memory/app/a.md", files)
        self.assertEqual((clone / "README.md").read_text(), "user is editing this in Obsidian\n")

    def test_lock_file_matches_session_journal(self):
        _, clone = make_repo(self.tmp, "vault")
        import hashlib
        key = hashlib.sha1(str(clone.resolve()).encode()).hexdigest()[:12]
        self.assertEqual(gitsync.lock_path(clone, self.cfg.lock_dir), self.cfg.lock_dir / f"repo-{key}.lock")

    def test_waits_for_lock(self):
        bare, clone = make_repo(self.tmp, "vault")
        write(clone / "memory" / "app" / "a.md", "a\n")
        done = []
        with gitsync.repo_lock(clone, self.cfg.lock_dir):
            t = threading.Thread(target=lambda: done.append(gitsync.commit_memory(clone, self.cfg.lock_dir)))
            t.start()
            t.join(0.5)
            self.assertEqual(done, [])
        t.join(30)
        self.assertEqual(done, [1])

    def test_no_remote(self):
        clone = self.tmp / "local"
        clone.mkdir()
        git(clone, "init", "-q", "-b", "main")
        git(clone, "config", "user.email", "t@example.com")
        git(clone, "config", "user.name", "t")
        write(clone / "memory" / "a.md", "a\n")
        self.assertEqual(gitsync.commit_memory(clone, self.cfg.lock_dir), 1)


if __name__ == "__main__":
    unittest.main()
