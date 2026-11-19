"""Browser tests for the PR #11 review findings. Skips without Playwright (CI has none)."""
from __future__ import annotations

import time
import unittest

from helpers import HAS_FFMPEG, TempDirCase, duration
import test_e2e as base  # module import, so unittest does not collect E2ETest twice

FRAME_HTML = '<button id="b" style="margin:60px">in frame</button><span class="email">kai@example.com</span>'
ADD_FRAME = """([src, top]) => { const f = document.createElement('iframe'); f.id = 'inner';
  f.style.cssText = `position:absolute;left:300px;top:${top}px;width:400px;height:200px`;
  if (src) f.src = src; else f.srcdoc = %r; document.body.append(f); }""" % FRAME_HTML


@unittest.skipUnless(base.HAS_PLAYWRIGHT and HAS_FFMPEG, "needs Playwright and ffmpeg")
class ReviewFindingsTest(TempDirCase):
    setUpClass = base.E2ETest.__dict__["setUpClass"]  # the raw classmethods, bound to this class
    tearDownClass = base.E2ETest.__dict__["tearDownClass"]
    url = base.E2ETest.url

    def rec(self, topic, **kw):
        from recorder import Recorder
        return Recorder("after", self.tmp, topic=topic, **kw)

    def open_edit(self, r, version="after"):
        r.goto(self.url(version))
        r.click(r.page.locator("tbody tr").first.get_by_role("button", name="Edit"))

    def test_show_ignores_the_recorders_own_text(self):
        with self.assertRaisesRegex(RuntimeError, "evidence"):
            with self.rec("own", timeout_ms=1500) as r:
                self.open_edit(r, "before")
                r.click(r.page.get_by_label("Discount"))
                r.select_all()
                r.type("150", delay_ms=0)
                r.click(r.page.get_by_role("button", name="Save"))  # the app clears the field
                r.show(r.page.get_by_text("150"), "claims 150", hold=0)  # only the key box says 150

    def test_blur_reaches_frames(self):
        with self.rec("fblur", blur=[".email"]) as r:
            p = r.page
            r.goto(self.url("after"))
            p.evaluate(ADD_FRAME, [None, 400])
            p.frame_locator("#inner").locator(".email").wait_for()
            inner = p.frame(url="about:srcdoc")
            self.assertIn("blur", inner.evaluate("getComputedStyle(document.querySelector('.email')).filter"))
            r.blur("#b")
            self.assertIn("blur", inner.evaluate("getComputedStyle(document.getElementById('b')).filter"))

    def test_blur_is_on_before_scripts_finish_loading(self):
        pending = []
        with self.rec("early", blur=[".email"]) as r:
            p = r.page
            p.route("**/early.html", lambda route: route.fulfill(content_type="text/html", body=(
                '<table><tr><td class="email">kai@example.com</td></tr></table>'
                '<script src="/slow.js" defer></script>')))
            p.route("**/slow.js", lambda route: pending.append(route))  # held until the check is done
            p.goto(f"{self.base}/early.html", wait_until="commit")  # load waits for slow.js
            p.wait_for_function("document.readyState === 'interactive' && !!document.querySelector('.email')")
            self.assertIn("blur", p.evaluate("getComputedStyle(document.querySelector('.email')).filter"))
            for route in pending:
                route.fulfill(body="")
            r.start_capture()
            r.pause(0.5)

    def test_dialog_box_stays_through_a_long_hold(self):
        with self.rec("hold", timeout_ms=3000) as r:
            self.open_edit(r, "before")
            r.click(r.page.get_by_label("Discount"))
            r.select_all()
            r.type("150", delay_ms=0)
            r.click(r.page.get_by_role("button", name="Save"))
            r.show(r.dialog_box, "the alert", hold=6.5)
            self.assertTrue(r.dialog_box.is_visible())
            r.click(r.page.get_by_role("button", name="Cancel"))  # the next action clears it
            r.pause(0.2)
            self.assertFalse(r.dialog_box.is_visible())

    def test_expect_dialog_waits_for_a_late_alert(self):
        with self.rec("late") as r:
            p = r.page
            r.goto(self.url("after"))
            p.evaluate("""() => { const b = document.createElement('button'); b.id = 'late'; b.textContent = 'Late';
              b.onclick = () => setTimeout(() => alert('late one'), 600); document.querySelector('header').append(b); }""")
            with r.expect_dialog() as alert:
                r.click("#late")
            self.assertEqual(alert.message, "late one")

    def test_expect_dialog_fails_when_none_appears(self):
        with self.assertRaisesRegex(RuntimeError, "no browser dialog"):
            with self.rec("nodlg", timeout_ms=800) as r:
                r.goto(self.url("after"))
                with r.expect_dialog():
                    pass

    def test_caption_comes_back_after_a_reload(self):
        with self.rec("recap") as r:
            p = r.page
            r.goto(self.url("after"))
            r.caption("still here")
            p.reload()
            p.wait_for_function("document.getElementById('__rec_cap')?.textContent === 'still here'")
            self.assertTrue(p.locator("#__rec_cap").is_visible())

    def test_a_take_that_never_starts_capture_fails(self):
        with self.assertRaisesRegex(RuntimeError, "start_capture"):
            with self.rec("never") as r:
                r.goto(self.url("after"), capture=False)
                r.caption("hello")

    def test_an_old_video_does_not_survive_a_failed_take(self):
        old = self.tmp / "stale_AFTER.mp4"
        old.write_bytes(b"old take")
        with self.assertRaises(ValueError):
            with self.rec("stale") as r:
                r.goto(self.url("after"), capture=False)
                raise ValueError("login failed")
        self.assertFalse(old.exists())

    def test_pointer_follows_into_a_cross_origin_frame(self):
        frame_url = self.base.replace("127.0.0.1", "localhost") + "/frame.html"
        with self.rec("xorigin") as r:
            p = r.page
            p.context.route("**/frame.html", lambda route: route.fulfill(content_type="text/html", body=FRAME_HTML))
            r.goto(self.url("after"))
            p.evaluate(ADD_FRAME, [frame_url, 400])
            button = p.frame_locator("#inner").locator("#b")
            button.wait_for()
            x, y = r.move_to(button)
            transform = p.evaluate("document.getElementById('__rec_ptr').style.transform")
            px, py = (float(v) for v in transform[len("translate("):-1].replace("px", "").split(","))
            self.assertAlmostEqual(px, x - 3, delta=2)
            self.assertAlmostEqual(py, y - 2, delta=2)

    def test_moving_into_a_frame_does_not_scroll_the_page(self):
        with self.rec("noscroll") as r:
            p = r.page
            r.goto(self.url("after"))
            p.evaluate("document.body.style.minHeight = '3000px'")
            p.evaluate(ADD_FRAME, [None, 500])
            p.frame_locator("#inner").locator("#b").wait_for()
            p.evaluate("window.scrollTo(0, 200)")
            r.move_to(p.frame_locator("#inner").locator("#b"))
            self.assertEqual(p.evaluate("window.scrollY"), 200)

    def test_a_flows_context_dialog_handler_keeps_its_answer(self):
        with self.rec("ctxdlg") as r:
            r.ctx.on("dialog", lambda d: d.accept())
            r.goto(self.url("after"))
            r.page.evaluate(base.ASK_BUTTON)
            r.click("#ask")
            r.pause(0.3)
            self.assertEqual(r.page.evaluate("document.body.dataset.answer"), "true")

    def test_cut_around_the_first_load_records_no_wait(self):
        start = time.time()
        with self.rec("firstcut") as r:
            with r.cut():
                r.goto(self.url("after", delay=2500))
                r.page.locator("tbody tr").first.wait_for()
            r.caption("ready")
            r.pause(1)
        self.assertLess(duration(self.tmp / "firstcut_AFTER.mp4"), time.time() - start - 2)

    def test_pointer_lands_on_the_target_on_a_smooth_scrolling_page(self):
        with self.rec("smooth") as r:
            p = r.page
            r.goto(self.url("after"))
            p.evaluate("document.documentElement.style.scrollBehavior = 'smooth'; document.body.style.minHeight = '3000px'")
            row = p.locator("tbody tr").first
            # the row's top 4 px above the screen: Playwright scrolls it to the top edge, under the sticky header
            row.evaluate("e => window.scrollTo({top: e.getBoundingClientRect().top + scrollY + 4, behavior: 'instant'})")
            r.move_to(row)
            r.pause(1)  # any smooth scroll has ended by now
            box = row.bounding_box()
            transform = p.evaluate("document.getElementById('__rec_ptr').style.transform")
            px, py = (float(v) for v in transform[len("translate("):-1].replace("px", "").split(","))
            self.assertAlmostEqual(px + 3, box["x"] + box["width"] / 2, delta=3)
            self.assertAlmostEqual(py + 2, box["y"] + box["height"] / 2, delta=3)

    def test_show_saves_its_still_at_the_evidence(self):
        with self.rec("evid") as r:
            p = r.page
            r.goto(self.url("after"))
            r.show(p.get_by_role("button", name="Print list"), "the print button", hold=0.3)
            x, y = r._pos
            r.click(p.locator("tbody tr").last.get_by_role("button", name="Edit"))  # still under the first caption
            r.show(p.get_by_label("Discount"), "the discount field", hold=0.3)
        still = self.tmp / "evid_AFTER_stills" / "01.jpg"
        self.assertTrue(base.near(base.pixel(still, int(x) + 4, int(y) + 10), (17, 17, 17), tol=60),
                        "the first still was saved after the next click, not at its evidence")

    def test_password_in_a_web_component_stays_hidden(self):
        with self.rec("shadow") as r:
            p = r.page
            r.goto(self.url("after"))
            p.evaluate("""() => { const host = document.createElement('x-pw');
              host.attachShadow({mode: 'open'}).innerHTML = '<input type="password" id="pw">';
              document.querySelector('main').prepend(host); }""")
            r.click(p.locator("x-pw").locator("#pw"))
            r.type("hunter2", delay_ms=0)
            self.assertNotIn("hunter2", p.evaluate("document.getElementById('__rec_keys').textContent"))


if __name__ == "__main__":
    unittest.main()
