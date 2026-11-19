"""Reusable before/after screen-video recorder (Playwright + ffmpeg).

Headless Playwright video has no mouse pointer, no key feedback and no native
dialogs, so ``overlay.js`` draws them into the page itself: a pointer arrow
with a ring on each click, a "Keys pressed" box, a caption bar, a BEFORE/AFTER
badge and a "Browser alert" box. Every interaction goes through real input
events (mouse.move / mouse.click / keyboard.type), never ``element.value = ...``,
so the video shows what a human would get, including bugs that only real key
presses trigger.

Capture: on Playwright >= 1.59 frames come from ``page.screencast`` and are
encoded by ffmpeg at a chosen quality (``encoder.py``). Older Playwright, or
``native=False``, falls back to the built-in ``record_video_dir`` (VP8 at a
fixed ~1 Mbit/s, visibly blurry; no cuts and no late start).
"""
from __future__ import annotations

import contextlib
import json
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

from playwright.sync_api import Dialog, Locator, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from encoder import FrameEncoder
from media import EVEN_DIMS, report_size, require_ffmpeg, run_ffmpeg, video_name
from options import context_kwargs, launch_kwargs

_FrameEncoder = FrameEncoder  # old name, kept for flow scripts that import it
OVERLAY_JS = (Path(__file__).with_name("overlay.js")).read_text(encoding="utf-8")
BADGE_COLORS = {"before": "#b91c1c", "after": "#15803d"}  # red = old, green = new
DIALOG_ACTIONS = ("dismiss", "accept", None)
MAX_EVIDENCE_MATCHES = 50  # show() looks at this many matches for one the app itself drew

# True when the element at (x, y) is the target or inside it.
_HIT_TEST_JS = "(e, [x, y]) => { const t = document.elementFromPoint(x, y); return !!t && (t === e || e.contains(t)); }"
# The app drew it: not the recorder's own key box, caption or badge (its dialog box counts as evidence).
_APP_ELEMENT_JS = "e => e.id === '__rec_dialog' || !e.closest('#__rec_root')"
_IN_TOP_PAGE_JS = "e => window.top === window"


@dataclass
class DialogMessage:
    """Filled in by ``Recorder.expect_dialog`` when its block ends."""
    message: str = ""


def _flow_answers_dialogs(dialog: Dialog, ctx) -> bool:
    """True when the flow has its own ``page.on("dialog")`` or ``ctx.on("dialog")``
    handler. The recorder's handler runs first, so answering would override it."""
    try:
        page = dialog.page
        if page and page._impl_obj.listeners("dialog"):
            return True
        return len(ctx._impl_obj.listeners("dialog")) > 1  # the recorder's own handler is one
    except Exception:  # private Playwright API: if it moves, answer as before
        return False


class Recorder:
    """One recording = one browser context = one video file.

    ``name`` is the take (``before``/``after``); ``topic`` names the files
    ``<topic>_BEFORE.mp4``. 1440×810 is 16:9 and fits a laptop screen at 1:1.
    """

    def __init__(self, name: str, out_dir: str | Path, *, topic: str | None = None, width: int = 1440,
                 height: int = 810, channel: str | None = "chrome", glide_steps: int = 25, slow: float = 1.0,
                 fps: int = 30, crf: int = 20, timeout_ms: int = 10_000, badge: bool = True,
                 popups: bool = False, native: bool | None = None, dialogs: str | None = "dismiss",
                 blur: Iterable[str] = (), context_options: dict | None = None,
                 launch_options: dict | None = None, stills: bool = True):
        if dialogs not in DIALOG_ACTIONS:
            raise ValueError(f"dialogs must be one of {DIALOG_ACTIONS}, not {dialogs!r}")
        self.name = name
        self.out_dir = Path(out_dir)
        self.topic = topic
        self.size = {"width": width, "height": height}
        self.channel = channel          # "chrome" = installed Google Chrome; None = Playwright's own build
        self.glide_steps = glide_steps  # pointer moves in 25 steps ≈ a smooth 0.4 s glide
        self.slow = slow                # multiply every pause (1.5 = calmer video)
        self.fps = fps
        self.crf = crf                  # 18 = near-lossless, 20 = sharp UI text, 28 = small file
        self.timeout_ms = timeout_ms    # a missing element fails fast instead of Playwright's 30 s
        self.badge = badge
        self.popups = popups            # the flow opens a new tab or window
        self.native = hasattr(Page, "screencast") if native is None else native
        self.dialog_action = dialogs    # how native alert/confirm/prompt are answered; None = leave to the flow
        self.dialogs: list[str] = []    # every dialog message, in order
        self.blur_selectors = [blur] if isinstance(blur, str) else list(blur)
        self.context_options = context_options or {}
        self.launch_options = launch_options or {}
        self.mp4_path: Path | None = None
        stem = video_name(name, topic)[:-len(".mp4")]
        self.stills_dir: Path | None = self.out_dir / f"{stem}_stills" if stills else None
        self._pos = (width / 2, height / 2)
        self._encoder: FrameEncoder | None = None
        self._caption = ""               # the caption whose still is still to be saved
        self._on_screen = ("", False)    # the caption bar as shown: (text, top), restored after reloads
        self._cutting = False
        self._start_after_cut = False
        self._in_frame = False           # the pointer's last target sits inside a frame
        self._stills: list[tuple[str, str]] = []  # (file name, caption)

    # ── lifecycle ────────────────────────────────────────────────
    def __enter__(self) -> "Recorder":
        require_ffmpeg()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / video_name(self.name, self.topic)).unlink(missing_ok=True)  # never leave an old take
        if self.stills_dir:
            shutil.rmtree(self.stills_dir, ignore_errors=True)
            self.stills_dir.mkdir()
        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.launch(
                **launch_kwargs(self.channel, popups=self.popups, launch_options=self.launch_options))
            raw = None
            if not self.native:
                self._raw = raw = self.out_dir / f"_{self.name}_raw"
                shutil.rmtree(raw, ignore_errors=True)
            self.ctx = self.browser.new_context(
                **context_kwargs(self.size, raw_dir=raw, context_options=self.context_options))
            self.ctx.set_default_timeout(self.timeout_ms)
            if self.dialog_action:
                self.ctx.on("dialog", self._on_dialog)
            self.ctx.expose_binding("__recCaptionNow", lambda _source: list(self._on_screen))
            if self.badge:
                color = BADGE_COLORS.get(self.name.lower(), "#1f2937")
                self.ctx.add_init_script(f"window.__recBadgeInit = {json.dumps([self.name.upper(), color])};")
            self.ctx.add_init_script(f"window.__recBlurInit = {json.dumps(self.blur_selectors)};")
            self.ctx.add_init_script(OVERLAY_JS)
            self.page: Page = self.ctx.new_page()
        except Exception:
            self._pw.stop()
            raise
        return self

    def __exit__(self, exc_type, *_exc) -> None:
        failed = exc_type is not None
        still_error: Exception | None = None
        if not failed:
            try:
                self._save_still()
            except Exception as e:  # close the browser first, then report it
                still_error = e
        try:
            raw = self._close(quiet=failed or still_error is not None)
        except BaseException:
            self._abort_encoder()
            raise
        if failed or still_error is not None:
            self._abort_encoder()
            if still_error is not None:
                raise still_error
            return
        if self.native and self._encoder is None:
            raise RuntimeError("the take recorded nothing: call r.start_capture() after r.goto(url, capture=False)")
        dst = self.out_dir / video_name(self.name, self.topic)
        if self._encoder is not None:
            self.mp4_path = self._encoder.finish()
        elif raw:
            self.mp4_path = to_mp4(raw, dst, crf=self.crf)
            shutil.rmtree(self._raw, ignore_errors=True)
        if self.mp4_path:
            report_size(self.mp4_path)
        self._write_captions()

    def _close(self, *, quiet: bool) -> Path | None:
        """Stop capture and close the browser; return the fallback WebM, if any.
        ``quiet`` swallows teardown errors, so a failed flow's own error surfaces."""
        video = None if self.native else self.page.video
        raw: Path | None = None
        try:
            with (contextlib.suppress(Exception) if quiet else contextlib.nullcontext()):
                if self._encoder is not None:
                    self.page.screencast.stop()
                self.ctx.close()  # flushes the fallback .webm
                raw = Path(video.path()) if video else None  # must be read before stop()
                self.browser.close()
        finally:
            self._pw.stop()
        return raw

    def _abort_encoder(self) -> None:
        if self._encoder is not None:
            self._encoder.abort()

    # ── capture ──────────────────────────────────────────────────
    def start_capture(self) -> None:
        """Start the video now. ``goto`` does this on its own unless ``capture=False``."""
        if not self.native or self._encoder is not None:
            return
        if self._cutting:  # inside cut(): start when the block ends, so its wait stays out
            self._start_after_cut = True
            return
        self._encoder = FrameEncoder(self.out_dir / video_name(self.name, self.topic), self.fps, self.crf)
        self.page.screencast.start(on_frame=self._encoder.on_frame, size=self.size, quality=90)

    _start_capture = start_capture  # old name, kept for flow scripts that call it

    @contextmanager
    def cut(self) -> Iterator[None]:
        """Leave the block's time out of the video: a slow load, a long wait.
        Caption it, e.g. "(loading time cut from the video)"."""
        if not self.native:
            raise RuntimeError("cut() needs screencast capture (Playwright >= 1.59, native=True); "
                               "this take records with the video fallback")
        if self._cutting:
            raise RuntimeError("cut() blocks cannot be nested")
        if self._encoder is None:  # nothing recorded yet: a goto() inside starts capture after the block
            self._cutting = True
            try:
                yield
            finally:
                self._cutting = False
            if self._start_after_cut:
                self._start_after_cut = False
                self.start_capture()
            return
        self._cutting = True
        self.page.screencast.stop()
        started = time.time()
        done = False
        try:
            yield
            done = True
        finally:
            self._cutting = False
            self._encoder.skip((time.time() - started) * 1000)
            # if the block failed, its error matters more than a failed restart
            with (contextlib.nullcontext() if done else contextlib.suppress(Exception)):
                self.page.screencast.start(on_frame=self._encoder.on_frame, size=self.size, quality=90)

    # ── narration ────────────────────────────────────────────────
    def caption(self, text: str, *, top: bool = False) -> None:
        """Narration bar. Use ``top=True`` when the thing you point at sits at
        the bottom of the screen, so the bar does not cover it. Each new caption
        saves a still of the previous one's last frame for the frame check."""
        self._save_still()
        self._caption = text
        self._on_screen = (text, top)
        self.page.evaluate("([t, top]) => window.__recCaption && window.__recCaption(t, top)", [text, top])

    def show(self, target: str | Locator, caption: str, *, hold: float = 4.0, value: str | None = None,
             top: bool = False) -> None:
        """Check the evidence, then claim it: wait until ``target`` is visible
        (and, with ``value``, until the field holds exactly that), point at it,
        caption it and hold. Missing evidence fails the take instead of
        recording a caption that lies. Text in the recorder's own key box or
        caption bar never counts as evidence."""
        loc = self._evidence(target, caption)
        if value is not None:
            self._wait_for_value(loc, value, caption)
        self._end_caption()  # its still must show the pointer where that caption left it
        self.move_to(loc)
        self.caption(caption, top=top)
        self.pause(hold)

    def keys_reset(self) -> None:
        self.page.evaluate("() => window.__recKeysReset && window.__recKeysReset()")

    def pause(self, seconds: float) -> None:
        # wait_for_timeout keeps Playwright pumping events; time.sleep would drop screencast frames
        self.page.wait_for_timeout(seconds * self.slow * 1000)

    @property
    def dialog_box(self) -> Locator:
        """The on-page box that shows the last native dialog's message, until the next click or key."""
        return self.page.locator("#__rec_dialog")

    @contextmanager
    def expect_dialog(self) -> Iterator[DialogMessage]:
        """Wait, after the block, for a native dialog the block triggered:
        ``with r.expect_dialog() as alert: r.click(save)``, then use ``alert.message``."""
        start = len(self.dialogs)
        found = DialogMessage()
        yield found
        deadline = time.time() + self.timeout_ms / 1000
        while len(self.dialogs) == start:
            if time.time() >= deadline:
                raise RuntimeError(f"no browser dialog appeared within {self.timeout_ms} ms"
                                   + (" (dialogs=None records none)" if self.dialog_action is None else ""))
            self.page.wait_for_timeout(100)
        found.message = self.dialogs[start]

    def blur(self, selector: str) -> None:
        """Blur every element matching a CSS selector, in every frame, now and after reloads."""
        self.blur_selectors = [*self.blur_selectors, selector]
        sel = json.dumps(selector)
        self.ctx.add_init_script(f"window.__recBlurInit = (window.__recBlurInit || []).concat([{sel}]);"
                                 f"if (window.__recAddBlur) window.__recAddBlur({sel});")
        for frame in self.page.frames:
            with contextlib.suppress(PlaywrightError):  # a frame that is gone needs no blur
                frame.evaluate("s => window.__recAddBlur && window.__recAddBlur(s)", selector)

    # ── input (always real events) ───────────────────────────────
    def goto(self, url: str, *, capture: bool = True) -> None:
        """Open ``url``. ``capture=False`` keeps the camera off (log in, wait for
        data), then call ``start_capture()`` on a ready screen."""
        if not capture and not self.native:
            raise RuntimeError("goto(capture=False) needs screencast capture (Playwright >= 1.59, native=True); "
                               "the video fallback records from the first page on")
        self.page.goto(url)
        self.page.mouse.move(*self._pos)
        if capture:
            self.start_capture()

    def _target(self, target: str | Locator) -> Locator:
        # A video only needs *a* visible match; strict mode would abort the take.
        loc = self.page.locator(target) if isinstance(target, str) else target
        return loc.first

    def move_to(self, target: str | Locator) -> tuple[float, float]:
        loc = self._target(target)
        try:
            loc.scroll_into_view_if_needed()
            box = loc.bounding_box()
        except PlaywrightTimeoutError as e:
            raise RuntimeError(f"not visible after {self.timeout_ms} ms: {target}") from e
        if box is None:
            raise RuntimeError(f"not visible: {target}")
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        in_top_page = loc.evaluate(_IN_TOP_PAGE_JS)
        # scroll_into_view_if_needed leaves a target alone when it counts as in
        # view, even if a sticky header covers it: the click then lands on the
        # header and typing goes nowhere, silently. Re-centre when the point is
        # not the target (the recorder's own overlays are pointer-events:none).
        # Inside a frame the page coordinates do not fit the frame's document.
        if in_top_page and not loc.evaluate(_HIT_TEST_JS, [x, y]):
            loc.evaluate("e => e.scrollIntoView({block: 'center', inline: 'center'})")
            box = loc.bounding_box() or box
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        if in_top_page and not self._in_frame:
            self.page.mouse.move(x, y, steps=self.glide_steps)  # the page's own mouse events move the pointer
        else:
            self._glide_drawn(x, y)
        self._in_frame = not in_top_page
        self._pos = (x, y)
        return x, y

    def _glide_drawn(self, x: float, y: float) -> None:
        """Glide while drawing the pointer from here: a frame's mouse events never reach the top page."""
        x0, y0 = self._pos
        for i in range(1, self.glide_steps + 1):
            xi, yi = x0 + (x - x0) * i / self.glide_steps, y0 + (y - y0) * i / self.glide_steps
            self.page.mouse.move(xi, yi)
            self._draw_pointer(xi, yi)

    def _draw_pointer(self, x: float, y: float, *, down: bool = False) -> None:
        self.page.evaluate("([x, y, d]) => window.__recPointerAt && window.__recPointerAt(x, y, d)", [x, y, down])

    def click(self, target: str | Locator, *, hover: float = 0.4) -> None:
        self.move_to(target)
        self.pause(hover)  # a short hover lets the viewer see where the click lands
        if self._in_frame:
            self._draw_pointer(*self._pos, down=True)  # the click ring; the frame's mousedown never reaches the top page
        self.page.mouse.click(*self._pos)

    def type(self, text: str, *, delay_ms: int = 180, secret: bool = False) -> None:
        """180 ms per key reads as human typing. ``secret=True`` shows dots in
        the key box (for OTPs, tokens, API keys; password fields are automatic)."""
        if secret:
            self.page.evaluate("() => { window.__recSecret = true; }")
        try:
            self.page.keyboard.type(text, delay=delay_ms)
        finally:
            if secret:
                self.page.evaluate("() => { window.__recSecret = false; }")

    def press(self, key: str) -> None:
        self.page.keyboard.press(key)

    def select_all(self) -> None:
        self.press("ControlOrMeta+A")  # Cmd on macOS, Ctrl elsewhere

    def scroll(self, dy: int = 0, dx: int = 0, *, over: str | Locator | None = None) -> None:
        """Wheel-scroll like a user; ``over`` first glides the pointer onto the
        element to scroll (needed for horizontally scrolling tables)."""
        if over is not None:
            self.move_to(over)
        self.page.mouse.wheel(dx, dy)

    # ── internals ────────────────────────────────────────────────
    def _on_dialog(self, dialog: Dialog) -> None:
        leaving = dialog.type == "beforeunload"  # "leave this page?": always leave, or the flow hangs
        if not leaving:
            self.dialogs.append(dialog.message)
        if _flow_answers_dialogs(dialog, self.ctx):  # the flow's own dialog handler decides
            return
        try:
            dialog.accept() if leaving or self.dialog_action == "accept" else dialog.dismiss()
        except Exception as e:  # a flow's own page.on("dialog") handler got there first
            if "already handled" not in str(e):
                raise

    def _evidence(self, target: str | Locator, caption: str) -> Locator:
        """The first visible match the app drew; waits up to the timeout."""
        loc = self.page.locator(target) if isinstance(target, str) else target
        deadline = time.time() + self.timeout_ms / 1000
        while True:
            for i in range(min(loc.count(), MAX_EVIDENCE_MATCHES)):
                match = loc.nth(i)
                with contextlib.suppress(PlaywrightError):  # it went away between count() and now
                    if match.is_visible() and match.evaluate(_APP_ELEMENT_JS):
                        return match
            if time.time() >= deadline:
                raise RuntimeError(f"evidence not visible after {self.timeout_ms} ms: {target} (caption: {caption!r})")
            self.page.wait_for_timeout(100)

    def _wait_for_value(self, loc: Locator, value: str, caption: str) -> None:
        deadline = time.time() + self.timeout_ms / 1000
        actual = loc.input_value()
        while actual != value and time.time() < deadline:
            self.page.wait_for_timeout(100)
            actual = loc.input_value()
        if actual != value:
            raise RuntimeError(f"evidence shows {actual!r}, expected {value!r}: {loc} (caption: {caption!r})")

    def _end_caption(self) -> None:
        """Save the still of the showing caption now; the bar stays on screen until the next one."""
        self._save_still()
        self._caption = ""

    def _save_still(self) -> None:
        """Keep the last frame of the caption that is ending, for the frame check."""
        if not self.stills_dir or not self._caption:
            return
        path = self.stills_dir / f"{len(self._stills) + 1:02d}.jpg"
        if self._encoder is not None:
            saved = self._encoder.snapshot(path)
        elif not self.native:
            self.page.screenshot(path=str(path), type="jpeg", quality=85)
            saved = path
        else:
            saved = None  # the camera is not on yet
        if saved:
            self._stills.append((path.name, self._caption))

    def _write_captions(self) -> None:
        if not self.stills_dir:
            return
        lines = "".join(f"{name}\t{text}\n" for name, text in self._stills)
        (self.stills_dir / "captions.txt").write_text(lines, encoding="utf-8")
        if self._stills:
            print(f"{self.stills_dir}  {len(self._stills)} caption stills", file=sys.stderr)


def to_mp4(src: Path, dst: Path, *, crf: int = 20) -> Path:
    """WebM → H.264 MP4 (plays inline in ClickUp, Slack, GitHub, QuickTime)."""
    run_ffmpeg(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", EVEN_DIMS, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", str(crf), "-preset", "medium", "-movflags", "+faststart", "-an", str(dst)])
    return dst
