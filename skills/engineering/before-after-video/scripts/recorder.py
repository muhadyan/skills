"""Reusable before/after screen-video recorder (Playwright + ffmpeg).

Headless Playwright video has no mouse pointer and no key feedback, so this
module draws them into the page itself:

* a pointer arrow that follows every real mouse event, with a ripple on click
* a yellow "Keys pressed: ..." box fed by real keydown events
* a caption bar at the bottom for narration

All three are installed with ``add_init_script`` so they survive reloads.
Every interaction goes through real input events (mouse.move / mouse.click /
keyboard.type) — never ``element.value = ...`` — so the video shows what a
human would get, including bugs that only real key presses trigger.

Usage (from a flow script)::

    import sys; sys.path.insert(0, "<this dir>")
    from recorder import Recorder

    with Recorder("before", out_dir="/tmp/videos") as r:
        r.goto("http://localhost:5173/login")
        r.click("input[type=email]"); r.type("admin@example.com")
        r.caption("BEFORE: typing '-' turns into 0")
        r.pause(3)
    print(r.mp4_path)   # H.264 MP4, ready to upload
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

OVERLAY_JS = r"""
(() => {
  if (window.__recOverlay) return; window.__recOverlay = true;
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
    document.body.append(ptr, keys, cap);
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
      const secret = e.target && e.target.type === 'password';  // never show passwords on video
      if (e.metaKey || e.ctrlKey) {
        typed = '';
        keys.textContent = 'Keys pressed: ' + (e.metaKey ? '⌘' : 'Ctrl+') + e.key.toUpperCase();
      } else if (e.key === 'Backspace') {
        typed = typed.slice(0, -1); keys.textContent = 'Keys pressed: ' + typed + ' ⌫';
      } else if (e.key.length === 1) {
        typed += secret ? '•' : e.key; keys.textContent = 'Keys pressed: ' + typed;
      } else { return; }
      keys.style.display = 'block';
      clearTimeout(hideTimer);  // fade out once typing stops, so old keys don't linger
      hideTimer = setTimeout(() => { keys.style.display = 'none'; typed = ''; }, 6000);
    }, true);
    window.__recCaption = (t, top) => {
      cap.textContent = t; cap.style.display = t ? 'block' : 'none';
      cap.style.top = top ? '64px' : ''; cap.style.bottom = top ? '' : '28px';
    };
    window.__recKeysReset = () => { typed = ''; keys.style.display = 'none'; };
  };
  if (document.body) install(); else document.addEventListener('DOMContentLoaded', install);
})();
"""


class Recorder:
    """One recording = one browser context = one video file."""

    def __init__(self, name: str, out_dir: str | Path, *, width: int = 1440, height: int = 810,
                 channel: str | None = "chrome", glide_steps: int = 25, slow: float = 1.0):
        self.name = name
        self.out_dir = Path(out_dir)
        self.size = {"width": width, "height": height}
        self.channel = channel          # "chrome" = installed Google Chrome; None = bundled Chromium
        self.glide_steps = glide_steps  # pointer animation smoothness
        self.slow = slow                # multiply every pause (1.5 = calmer video)
        self.mp4_path: Path | None = None
        self._pos = (width / 2, height / 2)

    # ── lifecycle ────────────────────────────────────────────────
    def __enter__(self) -> "Recorder":
        self._pw = sync_playwright().start()
        kwargs = {"channel": self.channel} if self.channel else {}
        self.browser = self._pw.chromium.launch(**kwargs)
        raw = self.out_dir / f"_{self.name}_raw"
        shutil.rmtree(raw, ignore_errors=True)
        self.ctx = self.browser.new_context(viewport=self.size, record_video_dir=str(raw),
                                            record_video_size=self.size)
        self.ctx.add_init_script(OVERLAY_JS)
        self.page: Page = self.ctx.new_page()
        return self

    def __exit__(self, *exc) -> None:
        video = self.page.video
        raw: Path | None = None
        try:
            self.ctx.close()  # flushes the .webm
            raw = Path(video.path()) if video else None  # must be read before stop()
            self.browser.close()
        finally:
            self._pw.stop()
        if exc[0] is None and raw:
            self.mp4_path = to_mp4(raw, self.out_dir / f"{self.name}.mp4")

    # ── narration ────────────────────────────────────────────────
    def caption(self, text: str, *, top: bool = False) -> None:
        """Narration bar. Use ``top=True`` when the thing you point at sits at
        the bottom of the screen, so the bar does not cover it."""
        self.page.evaluate("([t, top]) => window.__recCaption && window.__recCaption(t, top)", [text, top])

    def keys_reset(self) -> None:
        self.page.evaluate("() => window.__recKeysReset && window.__recKeysReset()")

    def pause(self, seconds: float) -> None:
        time.sleep(seconds * self.slow)

    # ── input (always real events) ───────────────────────────────
    def goto(self, url: str) -> None:
        self.page.goto(url)
        self.page.mouse.move(*self._pos)

    def _target(self, target: str | Locator) -> Locator:
        # A video only needs *a* visible match; strict mode would abort the take.
        loc = self.page.locator(target) if isinstance(target, str) else target
        return loc.first

    def move_to(self, target: str | Locator) -> tuple[float, float]:
        loc = self._target(target)
        loc.scroll_into_view_if_needed()
        box = loc.bounding_box()
        if box is None:
            raise RuntimeError(f"not visible: {target}")
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        self.page.mouse.move(x, y, steps=self.glide_steps)
        self._pos = (x, y)
        return x, y

    def click(self, target: str | Locator, *, hover: float = 0.4) -> None:
        self.move_to(target)
        self.pause(hover)
        self.page.mouse.click(*self._pos)

    def type(self, text: str, *, delay_ms: int = 180) -> None:
        self.page.keyboard.type(text, delay=delay_ms)

    def press(self, key: str) -> None:
        self.page.keyboard.press(key)

    def select_all(self) -> None:
        self.press("Meta+A")

    def scroll(self, dy: int = 0, dx: int = 0, *, over: str | Locator | None = None) -> None:
        """Wheel-scroll like a user; ``over`` first glides the pointer onto the
        element to scroll (needed for horizontally scrolling tables)."""
        if over is not None:
            self.move_to(over)
        self.page.mouse.wheel(dx, dy)


def to_mp4(src: Path, dst: Path) -> Path:
    """WebM → H.264 MP4 (plays inline in ClickUp, Slack, GitHub, QuickTime)."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "23", "-preset", "medium", "-movflags", "+faststart", "-an", str(dst)], check=True)
    return dst
