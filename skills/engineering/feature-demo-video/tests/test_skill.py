"""The skill's links to before-after-video, and real takes of the example flow.

The browser tests skip without Playwright (CI has none). Run them locally:
  uv run --with "playwright>=1.59" python -m unittest -q
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
BAV = SKILL.parent / "before-after-video"  # the sibling skill that holds the recorder
REPO = SKILL.parents[2]
sys.path.insert(0, str(BAV / "scripts"))

try:
    import playwright.sync_api  # noqa: F401
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
LINK = re.compile(r"\]\(([^)#\s]+)")
FENCE = re.compile(r"^ *```.*?^ *```", re.S | re.M)  # templates in code blocks are not links


def probe(path: Path, entries: str) -> str:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", entries,
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return out.stdout.strip()


class LinksTest(unittest.TestCase):
    def test_every_relative_link_in_the_docs_resolves(self):
        for doc in SKILL.rglob("*.md"):
            for target in LINK.findall(FENCE.sub("", doc.read_text(encoding="utf-8"))):
                if "://" in target:
                    continue
                with self.subTest(doc=doc.name, target=target):
                    self.assertTrue((doc.parent / target).exists(), f"{doc.name} links to a missing {target}")

    def test_the_sibling_scripts_it_runs_exist(self):
        for name in ("recorder.py", "join.py"):
            self.assertTrue((BAV / "scripts" / name).exists(), name)

    def test_the_plugin_lists_the_skill(self):
        plugin = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertIn("./skills/engineering/feature-demo-video", plugin["skills"])

    def test_the_skill_name_matches_its_folder(self):
        head = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        self.assertIn(f"name: {SKILL.name}\n", head)


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass


@unittest.skipUnless(HAS_PLAYWRIGHT and HAS_FFMPEG, "needs Playwright and ffmpeg")
class TakesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        handler = functools.partial(_QuietHandler, directory=str(BAV / "examples" / "demo-app"))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def join(self, *argv: str) -> None:
        subprocess.run([sys.executable, str(BAV / "scripts" / "join.py"), str(self.tmp), *argv],
                       check=True, capture_output=True)

    def test_example_flow_claims_every_on_screen_ac(self):
        env = {**os.environ, "PYTHONPATH": str(BAV / "scripts")}
        subprocess.run([sys.executable, str(SKILL / "examples" / "demo_flow.py"), str(self.tmp), "--base", self.base,
                        "--delay", "1000"], env=env, check=True, capture_output=True)
        self.join("--topic", "DEMO-12", "--parts", "demo")
        self.assertTrue((self.tmp / "DEMO-12_DEMO_sheet.png").exists())
        captions = (self.tmp / "DEMO-12_DEMO_stills" / "captions.txt").read_text(encoding="utf-8")
        labels = {line.split("\t")[1].split(":")[0] for line in captions.splitlines()}
        self.assertLessEqual({"AC1", "AC2", "AC3"}, labels)

    def test_a_phone_take_and_a_pc_take_join_into_one_video(self):
        from recorder import Recorder
        for name, size in (("phone", (390, 844)), ("pc", (1440, 810))):
            with Recorder(name, self.tmp, topic="t", width=size[0], height=size[1]) as r:
                r.goto(f"{self.base}/index.html?v=after&delay=0")
                r.show(r.page.get_by_role("heading", name="Orders"), f"{name} take", hold=1)
        self.join("--topic", "t", "--parts", "phone", "pc")
        demo = self.tmp / "t_DEMO.mp4"
        self.assertEqual(probe(demo, "stream=width,height"), "1440,810")
        parts = sum(float(probe(self.tmp / f"t_{n}.mp4", "format=duration")) for n in ("PHONE", "PC"))
        self.assertAlmostEqual(float(probe(demo, "format=duration")), parts, delta=0.3)


if __name__ == "__main__":
    unittest.main()
