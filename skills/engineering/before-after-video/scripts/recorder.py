"""Reusable before/after screen-video recorder (Playwright + ffmpeg).

Headless Playwright video has no mouse pointer and no key feedback, so this
module draws them into the page itself:

* a pointer arrow that follows every real mouse event, with a ripple on click
* a yellow "Keys pressed: ..." box fed by real keydown events
* a caption bar for narration, and a BEFORE/AFTER badge in the corner

All of it is installed with ``add_init_script`` so it survives reloads.
Every interaction goes through real input events (mouse.move / mouse.click /
keyboard.type), never ``element.value = ...``, so the video shows what a
human would get, including bugs that only real key presses trigger.

Capture: on Playwright >= 1.59 frames come from ``page.screencast`` and are
encoded by ffmpeg at a chosen quality. Older Playwright falls back to the
built-in ``record_video_dir`` (VP8 at a fixed ~1 Mbit/s, visibly blurry).
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from media import EVEN_DIMS, report_size, require_ffmpeg, run_ffmpeg, video_name

OVERLAY_JS = r"""
(() => {
  if (window.__recOverlay) return; window.__recOverlay = true;
  window.__recSecret = false;
  const install = () => {
    const ptr = document.createElement('div');
    ptr.id = '__rec_ptr';
    ptr.innerHTML = '<svg width="28" height="28" viewBox="0 0 28 28"><path d="M3 2 L3 22 L8.5 16.8 L12.2 25 L15.6 23.5 L11.9 15.4 L19 15.4 Z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    ptr.style.cssText = 'position:fixed;left:0;top:0;width:28px;height:28px;z-index:2147483647;'
      + 'pointer-events:none;transform:translate(-100px,-100px);filter:drop-shadow(0 1px 2px rgba(0,0,0,.4))';
    const keys = document.createElement('div');
    keys.id = '__rec_keys';
    keys.style.cssText = 'position:fixed;right:24px;top:70px;z-index:2147483646;background:#facc15;color:#111;'
      + 'font:700 22px/1.3 ui-monospace,Menlo,monospace;padding:8px 16px;border-radius:8px;'
      + 'box-shadow:0 4px 16px rgba(0,0,0,.25);display:none;pointer-events:none';
    const cap = document.createElement('div');
    cap.id = '__rec_cap';
    cap.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:2147483646;'
      + 'background:rgba(17,24,39,.92);color:#fff;font:600 20px/1.4 system-ui;padding:12px 22px;'
      + 'border-radius:10px;max-width:1100px;text-align:center;box-shadow:0 6px 24px rgba(0,0,0,.3);'
      + 'display:none;pointer-events:none';
    const badge = document.createElement('div');
    badge.id = '__rec_badge';
    badge.style.cssText = 'position:fixed;left:16px;bottom:16px;z-index:2147483646;color:#fff;'
      + 'font:800 15px/1 system-ui;letter-spacing:.06em;padding:6px 10px;border-radius:6px;'
      + 'display:none;pointer-events:none;box-shadow:0 2px 8px rgba(0,0,0,.25)';
    document.body.append(ptr, keys, cap, badge);
    document.addEventListener('mousemove', e => {
      ptr.style.transform = `translate(${e.clientX - 3}px, ${e.clientY - 2}px)`;
    }, true);
    document.addEventListener('mousedown', e => {
      const r = document.createElement('div');
      r.style.cssText = `position:fixed;left:${e.clientX - 18}px;top:${e.clientY - 18}px;width:36px;height:36px;`
        + 'border-radius:50%;border:3px solid #ef4444;z-index:2147483646;pointer-events:none;'
        + 'transition:transform .45s ease-out,opacity .45s ease-out;transform:scale(.4);opacity:1';
      document.body.appendChild(r);
      requestAnimationFrame(() => { r.style.transform = 'scale(1.4)'; r.style.opacity = '0'; });
      setTimeout(() => r.remove(), 500);
    }, true);
    let typed = '', hideTimer = 0;
    document.addEventListener('keydown', e => {
      // never show passwords or fields typed with secret=True on video
      const secret = window.__recSecret || (e.target && e.target.type === 'password');
      if (e.metaKey || e.ctrlKey) {
        typed = '';
        keys.textContent = 'Keys pressed: ' + (e.metaKey ? '⌘' : 'Ctrl+') + e.key.toUpperCase();
      } else if (e.key === 'Backspace') {
        typed = typed.slice(0, -1); keys.textContent = 'Keys pressed: ' + typed + ' ⌫';
      } else if (e.key.length === 1) {
        typed += secret ? '•' : e.key; keys.textContent = 'Keys pressed: ' + typed;
      } else { return; }
      keys.style.display = 'block';
      clearTimeout(hideTimer);  // 6 s after the last key the box fades, so old keys don't linger
      hideTimer = setTimeout(() => { keys.style.display = 'none'; typed = ''; }, 6000);
    }, true);
    window.__recCaption = (t, top) => {
      cap.textContent = t; cap.style.display = t ? 'block' : 'none';
      cap.style.top = top ? '64px' : ''; cap.style.bottom = top ? '' : '28px';
    };
    window.__recKeysReset = () => { typed = ''; keys.style.display = 'none'; };
    window.__recBadge = (t, color) => {
      badge.textContent = t; badge.style.background = color; badge.style.display = t ? 'block' : 'none';
    };
    if (window.__recBadgeInit) window.__recBadge(...window.__recBadgeInit);
  };
  if (document.body) install(); else document.addEventListener('DOMContentLoaded', install);
})();
"""

BADGE_COLORS = {"before": "#b91c1c", "after": "#15803d"}  # red = old, green = new


class _FrameEncoder:
    """Turns screencast JPEG frames into a constant-frame-rate H.264 MP4.

    The browser only sends a frame when the screen changes, so each frame is
    repeated until the next one's timestamp; that keeps pauses their real length.
    """

    def __init__(self, dst: Path, fps: int, crf: int):
        self.fps, self.dst = fps, dst
        self.t0: float | None = None   # browser timestamp (ms) of the first frame
        self.wall0 = 0.0               # wall clock (ms) at the first frame
        self.slots = 0                 # frames written so far
        self.last: bytes | None = None
        self.proc = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(fps), "-i", "-",
             "-vf", EVEN_DIMS, "-c:v", "libx264", "-preset", "medium", "-tune", "animation", "-crf", str(crf),
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(dst)],
            stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def _fill_to(self, slot: int) -> None:
        while self.slots < slot and self.last is not None:
            self.proc.stdin.write(self.last)
            self.slots += 1

    def on_frame(self, frame) -> None:
        ts = frame["timestamp"]
        if self.t0 is None:
            self.t0, self.wall0 = ts, time.time() * 1000
        self._fill_to(int((ts - self.t0) * self.fps / 1000))
        self.last = frame["data"]
        self.proc.stdin.write(self.last)
        self.slots += 1

    def finish(self) -> Path:
        if self.t0 is not None:  # hold the last frame up to "now"
            self._fill_to(int((time.time() * 1000 - self.wall0) * self.fps / 1000))
        self.proc.stdin.close()
        err = self.proc.stderr.read().decode()
        if self.proc.wait() != 0 or self.last is None:
            raise RuntimeError(f"ffmpeg failed for {self.dst}: {err.strip() or 'no frames captured'}")
        return self.dst

    def abort(self) -> None:
        self.proc.kill()
        self.dst.unlink(missing_ok=True)


class Recorder:
    """One recording = one browser context = one video file.

    ``name`` is the take (``before``/``after``); ``topic`` names the files
    ``<topic>_BEFORE.mp4``. 1440×810 is 16:9 and fits a laptop screen at 1:1.
    """

    def __init__(self, name: str, out_dir: str | Path, *, topic: str | None = None, width: int = 1440,
                 height: int = 810, channel: str | None = "chrome", glide_steps: int = 25, slow: float = 1.0,
                 fps: int = 30, crf: int = 20, timeout_ms: int = 10_000, badge: bool = True):
        self.name = name
        self.out_dir = Path(out_dir)
        self.topic = topic
        self.size = {"width": width, "height": height}
        self.channel = channel          # "chrome" = installed Google Chrome; None = bundled Chromium
        self.glide_steps = glide_steps  # pointer moves in 25 steps ≈ a smooth 0.4 s glide
        self.slow = slow                # multiply every pause (1.5 = calmer video)
        self.fps = fps
        self.crf = crf                  # 18 = near-lossless, 20 = sharp UI text, 28 = small file
        self.timeout_ms = timeout_ms    # a missing element fails fast instead of Playwright's 30 s
        self.badge = badge
        self.mp4_path: Path | None = None
        self.native = hasattr(Page, "screencast")  # Playwright >= 1.59
        self._pos = (width / 2, height / 2)
        self._encoder: _FrameEncoder | None = None

    # ── lifecycle ────────────────────────────────────────────────
    def __enter__(self) -> "Recorder":
        require_ffmpeg()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        try:
            kwargs = {"channel": self.channel} if self.channel else {}
            self.browser = self._pw.chromium.launch(**kwargs)
            ctx_kwargs: dict = {"viewport": self.size}
            if not self.native:
                self._raw = self.out_dir / f"_{self.name}_raw"
                shutil.rmtree(self._raw, ignore_errors=True)
                ctx_kwargs.update(record_video_dir=str(self._raw), record_video_size=self.size)
            self.ctx = self.browser.new_context(**ctx_kwargs)
            self.ctx.set_default_timeout(self.timeout_ms)
            if self.badge:
                color = BADGE_COLORS.get(self.name.lower(), "#1f2937")
                self.ctx.add_init_script(f"window.__recBadgeInit = [{self.name.upper()!r}, {color!r}];")
            self.ctx.add_init_script(OVERLAY_JS)
            self.page: Page = self.ctx.new_page()
        except Exception:
            self._pw.stop()
            raise
        return self

    def __exit__(self, exc_type, *_exc) -> None:
        dst = self.out_dir / video_name(self.name, self.topic)
        video = None if self.native else self.page.video
        raw: Path | None = None
        try:
            if self._encoder is not None:
                self.page.screencast.stop()
            self.ctx.close()  # flushes the fallback .webm
            raw = Path(video.path()) if video else None  # must be read before stop()
            self.browser.close()
        finally:
            self._pw.stop()
        if exc_type is not None:
            if self._encoder is not None:
                self._encoder.abort()
            return
        if self._encoder is not None:
            self.mp4_path = self._encoder.finish()
        elif raw:
            self.mp4_path = to_mp4(raw, dst, crf=self.crf)
            shutil.rmtree(self._raw, ignore_errors=True)
        if self.mp4_path:
            report_size(self.mp4_path)

    def _start_capture(self) -> None:
        """Start after the first page has loaded, so the video has no blank start."""
        if not self.native or self._encoder is not None:
            return
        self._encoder = _FrameEncoder(self.out_dir / video_name(self.name, self.topic), self.fps, self.crf)
        self.page.screencast.start(on_frame=self._encoder.on_frame, size=self.size, quality=90)

    # ── narration ────────────────────────────────────────────────
    def caption(self, text: str, *, top: bool = False) -> None:
        """Narration bar. Use ``top=True`` when the thing you point at sits at
        the bottom of the screen, so the bar does not cover it."""
        self.page.evaluate("([t, top]) => window.__recCaption && window.__recCaption(t, top)", [text, top])

    def keys_reset(self) -> None:
        self.page.evaluate("() => window.__recKeysReset && window.__recKeysReset()")

    def pause(self, seconds: float) -> None:
        # wait_for_timeout keeps Playwright pumping events; time.sleep would drop screencast frames
        self.page.wait_for_timeout(seconds * self.slow * 1000)

    # ── input (always real events) ───────────────────────────────
    def goto(self, url: str) -> None:
        self.page.goto(url)
        self.page.mouse.move(*self._pos)
        self._start_capture()

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
        self.page.mouse.move(x, y, steps=self.glide_steps)
        self._pos = (x, y)
        return x, y

    def click(self, target: str | Locator, *, hover: float = 0.4) -> None:
        self.move_to(target)
        self.pause(hover)  # a short hover lets the viewer see where the click lands
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


def to_mp4(src: Path, dst: Path, *, crf: int = 20) -> Path:
    """WebM → H.264 MP4 (plays inline in ClickUp, Slack, GitHub, QuickTime)."""
    run_ffmpeg(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", EVEN_DIMS, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", str(crf), "-preset", "medium", "-movflags", "+faststart", "-an", str(dst)])
    return dst
