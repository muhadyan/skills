"""Records real takes of the demo app. Skips without Playwright (CI has none).

Run locally: uv run --with "playwright>=1.59" python -m unittest -q test_e2e
"""
from __future__ import annotations

import functools
import http.server
import os
import subprocess
import sys
import threading
import time
import unittest

from helpers import HAS_FFMPEG, SKILL, TempDirCase, duration

try:
    import playwright.sync_api  # noqa: F401
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

APP = SKILL / "examples" / "demo-app"
GREEN = (21, 128, 61)  # the AFTER badge, #15803d


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass


def pixel(jpg, x: int, y: int) -> tuple:
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(jpg), "-vf", f"format=rgb24,crop=1:1:{x}:{y}", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    return tuple(out.stdout[:3])


def near(a: tuple, b: tuple, tol: int = 40) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


@unittest.skipUnless(HAS_PLAYWRIGHT and HAS_FFMPEG, "needs Playwright and ffmpeg")
class E2ETest(TempDirCase):
    @classmethod
    def setUpClass(cls) -> None:
        handler = functools.partial(_QuietHandler, directory=str(APP))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def url(self, version: str, delay: int = 0) -> str:
        return f"{self.base}/index.html?v={version}&delay={delay}"

    def run_flow(self, mode: str) -> None:
        env = {**os.environ, "PYTHONPATH": str(SKILL / "scripts")}
        subprocess.run([sys.executable, str(SKILL / "examples" / "demo_flow.py"), mode, str(self.tmp),
                        "--base", self.base, "--delay", "1500"], env=env, check=True, capture_output=True)

    def test_demo_flow_records_both_takes_and_composes(self):
        for mode in ("before", "after"):
            self.run_flow(mode)
        for mode in ("BEFORE", "AFTER"):
            self.assertGreater(duration(self.tmp / f"discount_{mode}.mp4"), 5)
            stills = self.tmp / f"discount_{mode}_stills"
            lines = (stills / "captions.txt").read_text().splitlines()
            self.assertEqual(len(lines), len(list(stills.glob("*.jpg"))))
            self.assertTrue(all("\t" in line for line in lines))
        subprocess.run([sys.executable, str(SKILL / "scripts" / "compose.py"), str(self.tmp), "--topic", "discount"],
                       check=True, capture_output=True)
        self.assertTrue((self.tmp / "discount_SIDE_BY_SIDE.mp4").exists())
        self.assertTrue((self.tmp / "discount_BEFORE_sheet.png").exists())
        self.assertTrue((self.tmp / "discount_AFTER_sheet.png").exists())

    def test_cut_removes_the_wait_from_the_video(self):
        from recorder import Recorder
        start = time.time()
        with Recorder("after", self.tmp, topic="cut") as r:
            r.goto(self.url("after"))
            r.page.locator("tbody tr").first.wait_for()
            r.pause(1)
            with r.cut():
                r.page.goto(self.url("after", delay=3000))
                r.page.locator("tbody tr").first.wait_for()
            r.pause(1)
        wall = time.time() - start
        self.assertLess(duration(self.tmp / "cut_AFTER.mp4"), wall - 2.5)

    def test_dialogs_are_recorded_and_drawn(self):
        from recorder import Recorder
        with Recorder("before", self.tmp, topic="dlg") as r:
            p = r.page
            r.goto(self.url("before"))
            r.click(p.locator("tbody tr").first.get_by_role("button", name="Edit"))
            r.click(p.get_by_label("Discount"))
            r.select_all()
            r.type("150", delay_ms=0)
            r.click(p.get_by_role("button", name="Save"))
            r.show(r.dialog_box, "alert shown", hold=0.2)
            self.assertEqual(r.dialogs, ["Invalid discount"])
            self.assertIn("Invalid discount", r.dialog_box.inner_text())

    def test_overlay_draws_above_modal_dialogs(self):
        from recorder import Recorder
        with Recorder("after", self.tmp, topic="top") as r:
            p = r.page
            r.goto(self.url("after"))
            r.click(p.locator("tbody tr").first.get_by_role("button", name="Edit"))
            x, y = r.move_to(p.get_by_label("Discount"))  # a white input inside a modal <dialog>
            r.caption("pointer on the input")
            r.pause(0.5)
        still = self.tmp / "top_AFTER_stills" / "01.jpg"
        self.assertTrue(near(pixel(still, int(x) + 4, int(y) + 10), (17, 17, 17), tol=60),
                        "the pointer is hidden under the modal dialog")

    def test_each_still_shows_the_pointer_on_its_own_evidence(self):
        from recorder import Recorder
        with Recorder("after", self.tmp, topic="seq") as r:
            p = r.page
            r.goto(self.url("after"))
            button = p.get_by_role("button", name="Print list")
            r.show(button, "first claim", hold=0.5)
            x, y = r._pos
            r.show(p.locator("tbody tr").last.get_by_role("button", name="Edit"), "second claim", hold=0.5)
        still = self.tmp / "seq_AFTER_stills" / "01.jpg"
        self.assertTrue(near(pixel(still, int(x) + 4, int(y) + 10), (17, 17, 17), tol=60),
                        "the first still shows the pointer somewhere else")

    def test_show_fails_loudly_when_evidence_is_missing(self):
        from recorder import Recorder
        with self.assertRaisesRegex(RuntimeError, "expected '999'"):
            with Recorder("after", self.tmp, topic="miss", timeout_ms=1500) as r:
                r.goto(self.url("after"))
                r.click(r.page.locator("tbody tr").first.get_by_role("button", name="Edit"))
                r.show(r.page.get_by_label("Discount"), "claims 999", value="999", hold=0)
        self.assertFalse((self.tmp / "miss_AFTER.mp4").exists())

    def test_blur_survives_reloads(self):
        from recorder import Recorder
        with Recorder("after", self.tmp, topic="blur", blur=[".email"]) as r:
            r.goto(self.url("after"))
            email = r.page.locator(".email").first
            self.assertIn("blur", email.evaluate("e => getComputedStyle(e).filter"))
            r.blur("td:nth-child(2)")
            r.page.reload()
            self.assertIn("blur", r.page.locator("td:nth-child(2)").first.evaluate("e => getComputedStyle(e).filter"))

    def test_popups_keep_frames_whole(self):
        from recorder import Recorder
        with Recorder("after", self.tmp, topic="pop", popups=True) as r:
            p = r.page
            r.goto(self.url("after"))
            p.evaluate("""() => { const a = document.createElement('a'); a.id = 'tab'; a.target = '_blank';
                                  a.href = location.href; a.textContent = 'tab'; document.body.prepend(a); }""")
            with p.context.expect_page() as new:
                r.click("#tab")
            new.value.close()
            p.bring_to_front()
            r.caption("back on the first page")
            r.pause(1)
        still = self.tmp / "pop_AFTER_stills" / "01.jpg"
        self.assertTrue(near(pixel(still, 30, 810 - 24), GREEN), "badge cropped away after the popup")

    def test_fallback_path_records_but_refuses_cut_and_late_start(self):
        from recorder import Recorder
        with Recorder("after", self.tmp, topic="fb", native=False) as r:
            with self.assertRaisesRegex(RuntimeError, "screencast"):
                r.goto(self.url("after"), capture=False)
            r.goto(self.url("after"))
            with self.assertRaisesRegex(RuntimeError, "screencast"):
                with r.cut():
                    pass
            r.show(r.page.locator("tbody tr").first, "fallback still", hold=0.5)
        self.assertGreater(duration(self.tmp / "fb_AFTER.mp4"), 0.5)
        self.assertEqual((self.tmp / "fb_AFTER_stills" / "captions.txt").read_text(), "01.jpg\tfallback still\n")
        self.assertFalse((self.tmp / "_after_raw").exists())

    def test_cut_before_capture_starts_is_harmless(self):
        from recorder import Recorder
        with Recorder("after", self.tmp, topic="early") as r:
            with r.cut():
                r.goto(self.url("after"), capture=False)
            r.start_capture()
            r.caption("ready")
            r.pause(0.5)
        self.assertTrue((self.tmp / "early_AFTER.mp4").exists())

    def test_show_fails_when_evidence_never_appears(self):
        from recorder import Recorder
        with self.assertRaisesRegex(RuntimeError, "evidence not visible"):
            with Recorder("after", self.tmp, topic="gone", timeout_ms=800) as r:
                r.goto(self.url("after"))
                r.show("#no-such-element", "claims something", hold=0)

    def test_one_blur_selector_string_stays_whole(self):
        from recorder import Recorder
        self.assertEqual(Recorder("after", self.tmp, blur=".email").blur_selectors, [".email"])

    def test_nested_cut_is_refused(self):
        from recorder import Recorder
        with Recorder("after", self.tmp, topic="nest") as r:
            r.goto(self.url("after"))
            with r.cut():
                with self.assertRaisesRegex(RuntimeError, "nested"):
                    with r.cut():
                        pass
            r.caption("still recording")
            r.pause(0.5)
        self.assertTrue((self.tmp / "nest_AFTER.mp4").exists())

    def test_leaving_a_page_with_unsaved_changes_does_not_hang(self):
        from recorder import Recorder
        with Recorder("after", self.tmp, topic="leave", timeout_ms=5000) as r:
            r.goto(self.url("after"))
            r.page.evaluate("() => addEventListener('beforeunload', e => { e.preventDefault(); e.returnValue = ''; })")
            r.click("h1")  # a real click gives the page the user activation beforeunload needs
            r.page.goto(self.url("before"))
            self.assertIn("v=before", r.page.url)
            self.assertEqual(r.dialogs, [])

    def test_teardown_error_keeps_the_flow_error_and_leaves_no_video(self):
        from recorder import Recorder
        with self.assertRaisesRegex(ValueError, "flow broke"):
            with Recorder("after", self.tmp, topic="crash") as r:
                r.goto(self.url("after"))
                r.page.close()  # screencast.stop() will fail during teardown
                raise ValueError("flow broke")
        self.assertFalse((self.tmp / "crash_AFTER.mp4").exists())

    def test_unknown_dialog_action_is_rejected(self):
        from recorder import Recorder
        with self.assertRaises(ValueError):
            Recorder("after", self.tmp, dialogs="maybe")


if __name__ == "__main__":
    unittest.main()
